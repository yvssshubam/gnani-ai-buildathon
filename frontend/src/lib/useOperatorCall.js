import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { Recorder, playAll } from "./recorder.js";
import { mmss } from "./useVoiceCall.js";

const RING_MS = 1200;
const CALLER_PAUSE_MS = 600;

/** Facts for a simulated caller when the operator takes over a ticket that had no scenario. */
export function factsFromTicket(t) {
  const loc = t.location || {}, d = t.danger || {};
  const where = [loc.door_no && `door ${loc.door_no}`, loc.street, loc.locality, loc.floor && `floor ${loc.floor}`].filter(Boolean).join(", ");
  return [
    where ? `You are at ${where}.` : "You are not sure of your exact address.",
    t.people_count ? `${t.people_count} people${t.vulnerable?.length ? `, including ${t.vulnerable.join(", ")}` : ""}.` : "",
    d.water_level ? `Water is ${d.water_level}-deep${d.water_rising ? " and rising" : ""}.` : "Water has come into the house.",
    d.injured ? "Someone is hurt." : "",
  ].filter(Boolean).join(" ");
}

/**
 * A call handled by a human operator. The laptop mic is the operator; the caller is simulated
 * (an LLM plays them from a few facts and a Gnani caller voice speaks it). Both sides go through
 * speech-to-text, so Surgeline's notes come from what was actually said.
 *
 * phase: idle ringing operator hearing thinking caller ended
 */
export function useOperatorCall({ onTurn } = {}) {
  const [phase, setPhase] = useState("idle");
  const [callId, setCallId] = useState(null);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [note, setNote] = useState(null);
  const rec = useRef(null);
  const audio = useRef(null);
  const ended = useRef(true);
  const idRef = useRef(null);
  const startedRef = useRef(null);
  const caller = useRef(null); // { facts, lang }
  const onTurnRef = useRef(onTurn);
  onTurnRef.current = onTurn;

  useEffect(() => () => { ended.current = true; rec.current?.stop(); audio.current?.pause(); }, []);
  useEffect(() => {
    if (!startedRef.current || phase === "ended" || phase === "idle") return;
    const i = setInterval(() => setSeconds((Date.now() - startedRef.current) / 1000), 500);
    return () => clearInterval(i);
  }, [phase]);

  const operatorTurn = async (wav) => {
    setPhase("thinking");
    let heard = "";
    try {
      heard = (await api.operatorTurn(idRef.current, wav, "operator")).heard;
    } catch (e) {
      setNote(e.status === 502 ? "That wasn't clear. Please say it again." : `Something went wrong: ${e.message}`);
    }
    onTurnRef.current?.();
    if (ended.current) return;
    if (!heard) { rec.current.listen(); return; }
    await callerTurn();
  };

  const callerTurn = async () => {
    const c = caller.current;
    try {
      const { text } = await api.simCallerReply(idRef.current, c.facts, c.lang);
      const line = text || c.fallback;
      await new Promise((r) => setTimeout(r, CALLER_PAUSE_MS));
      if (ended.current) return;
      const { audio: url } = await api.say(line, c.lang);
      setPhase("caller");
      await playAll([url], () => ended.current, (a) => { audio.current = a; });
      if (ended.current) return;
      setPhase("thinking");
      const clip = await (await fetch(url)).blob();
      await api.operatorTurn(idRef.current, clip, "caller");
      onTurnRef.current?.();
    } catch (e) {
      setNote(`The simulated caller couldn't answer: ${e.message}`);
    }
    if (!ended.current) rec.current.listen();
  };

  /** start({ ticketId?, facts, lang, fallback }). With ticketId, take over that call. */
  const start = async ({ ticketId, facts, lang, fallback }) => {
    ended.current = false;
    setNote(null); setSeconds(0);
    setPhase("ringing");
    caller.current = { facts, lang: lang || "hi-IN", fallback: fallback || "हाँ" };
    rec.current = new Recorder({
      onTurn: operatorTurn, onLevel: setLevel,
      onState: (s) => { if (s === "listening") setPhase("operator"); if (s === "hearing") setPhase("hearing"); },
    });
    try {
      await rec.current.start();
    } catch {
      setNote("The microphone is blocked. Allow microphone access in the browser.");
      ended.current = true; setPhase("ended");
      return null;
    }
    try {
      let id = ticketId;
      if (id) await api.takeOver(id);
      else {
        const [c] = await Promise.all([api.operatorStart(), new Promise((r) => setTimeout(r, RING_MS))]);
        id = c.call_id;
      }
      idRef.current = id;
      setCallId(id);
      startedRef.current = Date.now();
      onTurnRef.current?.();
      if (ticketId) rec.current.listen();          // taking over: the operator speaks first
      else await callerTurn();                     // a new call: the caller speaks first
      return id;
    } catch (e) {
      setNote(`Couldn't start the call: ${e.message}`);
      ended.current = true; rec.current?.stop(); setPhase("ended");
      return null;
    }
  };

  const end = async () => {
    ended.current = true;
    rec.current?.stop();
    audio.current?.pause();
    setLevel(0);
    setPhase("ended");
    if (idRef.current) await api.operatorEnd(idRef.current).catch(() => {});
    onTurnRef.current?.();
  };

  return {
    phase, callId, level, note, seconds, timer: mmss(seconds),
    active: !["idle", "ended"].includes(phase),
    start, end, finishNow: () => rec.current?.finishNow(),
  };
}
