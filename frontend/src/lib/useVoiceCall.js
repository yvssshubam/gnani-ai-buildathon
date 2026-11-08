import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { LANGUAGE, VULNERABLE, WATER_TEXT, floorLabel } from "./format.js";
import { Recorder, playAll } from "./recorder.js";
import { scriptReader } from "./scenarios.js";

const RING_MS = 1800;
const SIM_PAUSE_MS = 700;   // the simulated caller waits this long before answering
const SIM_MAX_TURNS = 16;   // safety stop for a simulated call

// What the live ticket shows, in order, and how to read each from the ticket
export const FIELDS = [
  { key: "language", label: "Language", value: (t) => LANGUAGE[t.language] || t.language },
  { key: "area", label: "Area", value: (t) => {
    const l = t.location || {};
    const pin = l.pincode ? `PIN ${l.pincode}` : null;
    return [l.locality, pin].filter(Boolean).join(", ") || null;
  } },
  { key: "address", label: "Address", value: (t) => {
    const l = t.location || {};
    const parts = [l.door_no && `Door ${l.door_no}`, l.building, l.street].filter(Boolean);
    return [...parts, floorLabel(l.floor)].filter(Boolean).join(", ") || (l.landmark ? `Near ${l.landmark}` : null);
  } },
  { key: "people", label: "People", value: (t) => {
    if (!t.people_count && !(t.vulnerable || []).length) return null;
    const who = (t.vulnerable || []).map((v) => VULNERABLE[v] || v);
    const n = t.people_count ? `${t.people_count}` : "Not known";
    return who.length ? `${n}, including ${who.join(", ")}` : n;
  } },
  { key: "danger", label: "Injuries", value: (t) => {
    const d = t.danger || {};
    if (d.injured) return "Someone is injured";
    if (d.medical_emergency) return "Medical emergency";
    if (d.trapped) return "Trapped";
    if (d.injured === false) return "Nobody hurt";
    return null;
  } },
  { key: "water", label: "Water", value: (t) => {
    const w = t.danger?.water_level;
    return w ? `${WATER_TEXT[w] || w}${t.danger?.water_rising ? ", rising" : ""}` : null;
  } },
  { key: "confirmed", label: "Confirmed", value: (t) => (t.location?.confirmed ? "Read back and confirmed" : null) },
];

export function questionsAnswered(t) {
  if (!t) return 0;
  const l = t.location || {}, d = t.danger || {};
  const dangerKnown = [d.injured, d.medical_emergency, d.water_rising, d.structure_unsafe, d.trapped].some((v) => v != null) || Boolean(d.water_level);
  return [dangerKnown, Boolean(l.locality || l.pincode), Boolean(l.street || l.door_no || l.building || l.landmark),
    Boolean(l.floor), t.people_count != null, (t.vulnerable || []).length > 0 || Boolean(d.water_level), Boolean(d.water_level)]
    .filter(Boolean).length;
}

export const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

async function playOne(url, isCancelled, onAudio) {
  await playAll([url], isCancelled, onAudio);
}

/**
 * One voice call, with the laptop mic as the caller (mode "mic") or a scripted caller spoken
 * by a second Gnani voice (mode "sim"). Either way the caller's audio goes through real
 * speech-to-text and the real call engine.
 *
 * phase: idle ringing listening hearing thinking speaking caller ended
 */
export function useVoiceCall({ onUpdate } = {}) {
  const [phase, setPhase] = useState("idle");
  const [mode, setMode] = useState(null);
  const [lines, setLines] = useState([]);
  const [ticket, setTicket] = useState(null);
  const [fields, setFields] = useState({});
  const [callId, setCallId] = useState(null);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [endNote, setEndNote] = useState(null);

  const rec = useRef(null);
  const audio = useRef(null);
  const ended = useRef(true);
  const idRef = useRef(null);
  const ticketRef = useRef(null);
  const startedRef = useRef(null);
  const sim = useRef(null);        // { read, lang, turns, lastAction }
  const scenarioRef = useRef(null);
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  useEffect(() => () => { ended.current = true; rec.current?.stop(); audio.current?.pause(); }, []);
  useEffect(() => {
    if (!startedRef.current || phase === "ended" || phase === "idle") return;
    const i = setInterval(() => setSeconds((Date.now() - startedRef.current) / 1000), 500);
    return () => clearInterval(i);
  }, [phase]);

  const add = (line) => setLines((l) => [...l, line]);
  const elapsed = () => (startedRef.current ? (Date.now() - startedRef.current) / 1000 : 0);

  /** Which fields this turn filled or changed, credited to what the caller just said. */
  const updateTicket = (next, heard, heardLang) => {
    const prev = ticketRef.current || {};
    const at = mmss(elapsed());
    setFields((f) => {
      const out = {};
      for (const field of FIELDS) {
        const before = field.value(prev), after = field.value(next);
        if (after && after !== before) {
          out[field.key] = {
            value: after, at, fresh: true,
            heard: field.key === "language" ? "Detected from what the caller said"
              : field.key === "confirmed" ? "Caller confirmed the read-back" : heard ? `“${heard}”` : "",
            lang: field.key === "language" || field.key === "confirmed" ? undefined : heardLang,
          };
        } else if (f[field.key]) out[field.key] = { ...f[field.key], fresh: false };
      }
      return out;
    });
    ticketRef.current = next;
    setTicket(next);
    onUpdateRef.current?.(next);
  };

  const finish = useCallback((note) => {
    ended.current = true;
    rec.current?.stop();
    rec.current = null;
    audio.current?.pause();
    setLevel(0);
    setEndNote(note);
    setPhase("ended");
  }, []);

  // ---- the simulated caller: say the scripted answer to the agent's last question, then send it
  const simCallerTurn = async () => {
    const s = sim.current;
    if (!s || ended.current) return;
    if (s.turns >= SIM_MAX_TURNS) { finish("Simulation stopped after too many turns"); return; }
    s.turns += 1;
    const text = s.turns === 1 ? s.read("opening") : s.read(s.lastAction);
    await new Promise((r) => setTimeout(r, SIM_PAUSE_MS));
    if (ended.current) return;
    let clip;
    try {
      const { audio: url } = await api.say(text, s.lang);
      setPhase("caller");
      await playOne(url, () => ended.current, (a) => { audio.current = a; });
      clip = await (await fetch(url)).blob();
    } catch (e) {
      add({ who: "note", text: `Couldn't make the caller's voice: ${e.message}` });
      finish("Simulation stopped");
      return;
    }
    if (!ended.current) await onTurn(clip);
  };

  const next = async () => {
    if (ended.current) return;
    if (sim.current) await simCallerTurn();
    else rec.current?.listen();
  };

  const speakThenNext = async (urls) => {
    setPhase("speaking");
    await playAll(urls, () => ended.current, (a) => { audio.current = a; });
    await next();
  };

  const onTurn = async (wav) => {
    setPhase("thinking");
    const t0 = performance.now();
    let res;
    try {
      res = await api.voiceTurn(idRef.current, wav);
    } catch (e) {
      add({ who: "note", text: e.status === 502 ? "That wasn't clear. Please say it again." : `Something went wrong: ${e.message}` });
      if (!ended.current) {
        if (sim.current) { sim.current.turns -= 1; await next(); } else rec.current?.listen();
      }
      return;
    }
    if (ended.current) return;
    const total = Math.round(performance.now() - t0);
    if (res.heard) add({ who: "caller", text: res.heard, lang: res.heard_lang });
    add({ who: "agent", text: res.reply, lang: res.reply_lang,
      timing: `speech to text ${res.stt_ms} ms, agent ${res.turn_ms ?? 0} ms, voice ${res.tts_ms} ms, total ${total} ms` });
    if (res.ticket) updateTicket(res.ticket, res.heard, res.heard_lang);
    if (sim.current) sim.current.lastAction = res.action;
    if (res.done) {
      setPhase("speaking");
      await playAll(res.audio, () => ended.current, (a) => { audio.current = a; });
      finish(res.action === "handoff" ? "Handed to a rescue officer" : "Ready for a team");
      return;
    }
    await speakThenNext(res.audio);
  };

  /** start({ mode: "mic" }) or start({ mode: "sim", scenario }) */
  const start = async ({ mode: m, scenario }) => {
    ended.current = false;
    ticketRef.current = null;
    startedRef.current = null;
    setMode(m); setLines([]); setTicket(null); setFields({}); setEndNote(null); setSeconds(0); setCallId(null);
    setPhase("ringing");
    sim.current = m === "sim" ? { read: scriptReader(scenario), lang: scenario.lang, turns: 0, lastAction: null } : null;
    scenarioRef.current = m === "sim" ? scenario : null;
    if (m === "mic") {
      rec.current = new Recorder({
        onTurn, onLevel: setLevel,
        onState: (st) => { if (st === "listening" || st === "hearing") setPhase(st); },
      });
      try {
        await rec.current.start();
      } catch {
        add({ who: "note", text: "The microphone is blocked. Allow microphone access in the browser, then call again." });
        finish(null);
        return null;
      }
    }
    const ring = new Promise((r) => setTimeout(r, RING_MS));
    try {
      const [c] = await Promise.all([api.startVoiceCall(), ring]);
      idRef.current = c.call_id;
      setCallId(c.call_id);
      startedRef.current = Date.now();
      add({ who: "agent", text: c.greeting });
      speakThenNext(c.audio);
      return c.call_id;
    } catch (e) {
      add({ who: "note", text: `Couldn't start the call: ${e.message}` });
      finish(null);
      return null;
    }
  };

  const hangUp = () => {
    const id = idRef.current;
    finish("Call cut off. Ticket kept and flagged for a callback");
    if (id) api.dropCall(id).catch(() => {});
  };

  const finishNow = () => rec.current?.finishNow();

  /** An operator takes the call: Surgeline stops talking, the call is not dropped. */
  const stopForTakeover = () => finish("An operator took over the call");

  return {
    phase, mode, lines, ticket, fields, callId, seconds, level, endNote,
    scenario: scenarioRef.current,
    active: !["idle", "ended"].includes(phase),
    answered: questionsAnswered(ticket),
    start, hangUp, finishNow, stopForTakeover,
  };
}