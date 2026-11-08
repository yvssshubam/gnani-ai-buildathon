import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { LANGUAGE } from "../lib/format.js";
import { Recorder, playAll } from "../lib/recorder.js";

const STATUS = {
  idle: "", connecting: "Connecting", listening: "Listening. Speak now.", hearing: "Hearing you",
  thinking: "One moment", speaking: "Agent speaking", ended: "",
};

/** The simulated caller phone. The laptop mic is the caller; replies play through the speakers. */
export default function Phone({ framed = true }) {
  const [phase, setPhase] = useState("idle");
  const [lines, setLines] = useState([]);
  const [callId, setCallId] = useState(null);
  const [lang, setLang] = useState(null);
  const [level, setLevel] = useState(0);
  const [timings, setTimings] = useState(false);
  const rec = useRef(null);
  const audio = useRef(null);
  const ended = useRef(false);
  const idRef = useRef(null);
  const logRef = useRef(null);

  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [lines]);
  useEffect(() => () => rec.current?.stop(), []);

  const add = (line) => setLines((l) => [...l, line]);

  const speakThenListen = async (urls) => {
    setPhase("speaking");
    await playAll(urls, () => ended.current, (a) => { audio.current = a; });
    if (!ended.current) rec.current.listen();
  };

  const finish = (text) => {
    ended.current = true;
    rec.current?.stop();
    audio.current?.pause();
    setLevel(0);
    if (text) add({ who: "note", text });
    setPhase("ended");
  };

  const onTurn = async (wav) => {
    setPhase("thinking");
    const started = performance.now();
    let res;
    try {
      res = await api.voiceTurn(idRef.current, wav);
    } catch (e) {
      add({ who: "note", text: e.status === 502 ? "That wasn't clear. Please say it again." : `Something went wrong: ${e.message}` });
      if (!ended.current) rec.current.listen();
      return;
    }
    if (ended.current) return;
    const total = Math.round(performance.now() - started);
    if (res.heard) add({ who: "caller", text: res.heard, lang: res.heard_lang });
    add({ who: "agent", text: res.reply, lang: res.reply_lang,
      timing: `speech to text ${res.stt_ms} ms, agent ${res.turn_ms ?? 0} ms, voice ${res.tts_ms} ms, total ${total} ms` });
    setLang(res.reply_lang);
    await speakThenListen(res.audio);
    if (res.done) finish(res.action === "handoff" ? "Connected to a rescue officer." : "Call ended. The request is registered.");
  };

  const call = async () => {
    ended.current = false;
    setLines([]); setLang(null); setPhase("connecting");
    rec.current = new Recorder({
      onTurn,
      onLevel: setLevel,
      onState: (m) => { if (m === "listening" || m === "hearing") setPhase(m); },
    });
    try {
      await rec.current.start();
    } catch {
      add({ who: "note", text: "The microphone is blocked. Allow microphone access in the browser and call again." });
      setPhase("idle");
      return;
    }
    try {
      const c = await api.startVoiceCall();
      idRef.current = c.call_id;
      setCallId(c.call_id);
      add({ who: "agent", text: c.greeting });
      await speakThenListen(c.audio);
    } catch (e) {
      finish(`Couldn't start the call: ${e.message}`);
    }
  };

  const hangUp = () => {
    const id = idRef.current;
    finish("You ended the call.");
    // A call cut short keeps what was said and is flagged for a callback
    if (id) api.dropCall(id).catch(() => {});
  };

  const inCall = !["idle", "ended"].includes(phase);

  const body = (
    <div className="phone">
      <header className="phone-head">
        <p className="phone-name">Surgeline</p>
        <p className="phone-meta">
          {callId ? `Ticket ${callId}` : "Flood rescue line"}
          {lang && <span className="phone-lang">{LANGUAGE[lang] || lang}</span>}
        </p>
      </header>
      <div className="phone-log" ref={logRef}>
        {lines.length === 0 && <p className="phone-hint">Press Call, wait for the greeting, then speak. The agent replies when you pause.</p>}
        {lines.map((l, i) => (
          <div key={i} className={`bubble ${l.who}`} lang={l.lang || undefined}>
            {l.text}
            {timings && l.timing && <span className="timing">{l.timing}</span>}
          </div>
        ))}
      </div>
      <p className={`phone-status s-${phase}`} aria-live="polite">{STATUS[phase]}</p>
      <div className="meter" aria-hidden="true"><div style={{ width: `${Math.round(level * 100)}%` }} /></div>
      <div className="phone-controls">
        {!inCall && <button className="call-btn" onClick={call}>{phase === "ended" ? "Call again" : "Call"}</button>}
        {phase === "hearing" && <button className="btn" onClick={() => rec.current.finishNow()}>Done speaking</button>}
        {inCall && <button className="end-btn" onClick={hangUp}>End</button>}
      </div>
      <label className="timings-toggle">
        <input type="checkbox" checked={timings} onChange={(e) => setTimings(e.target.checked)} /> Show timings
      </label>
    </div>
  );

  return framed ? <div className="phone-page">{body}</div> : body;
}
