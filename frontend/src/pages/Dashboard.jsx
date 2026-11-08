import { useEffect, useRef, useState } from "react";
import Queue from "../components/Queue.jsx";
import MapView from "../components/MapView.jsx";
import TicketDetail from "../components/TicketDetail.jsx";
import PriorityTag from "../components/PriorityTag.jsx";
import { LiveCallPanel } from "../components/LiveCall.jsx";
import OperatorCallPanel from "../components/OperatorCall.jsx";
import { factsFromTicket, useOperatorCall } from "../lib/useOperatorCall.js";
import { StartCall } from "./CallScreen.jsx";
import { api } from "../lib/api.js";
import { SCENARIOS } from "../lib/scenarios.js";
import { useVoiceCall } from "../lib/useVoiceCall.js";
import { useBoard } from "../lib/useBoard.js";
import { clock, stage } from "../lib/format.js";

function chime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [[660, 0], [880, 0.18]].forEach(([f, at]) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, ctx.currentTime + at);
      g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + at + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + at + 0.16);
      o.connect(g).connect(ctx.destination);
      o.start(ctx.currentTime + at); o.stop(ctx.currentTime + at + 0.2);
    });
    setTimeout(() => ctx.close(), 600);
  } catch { /* no audio */ }
}

export default function Dashboard() {
  const { board, error, refresh } = useBoard();
  const [selectedId, setSelectedId] = useState(null);
  const [sound, setSound] = useState(false);
  const [flashing, setFlashing] = useState(new Set());
  const [confirmShift, setConfirmShift] = useState(false);
  const [view, setView] = useState("ticket");   // right panel: "ticket" | "call" | "operator"
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const seenUrgent = useRef(null);
  const call = useVoiceCall();
  const op = useOperatorCall({ onTurn: () => refresh() });
  const scenario = SCENARIOS.find((s) => s.id === scenarioId);

  // An operator answers a new call; a simulated caller from the chosen scenario talks to them
  const answerYourself = async () => {
    setView("operator");
    setSelectedId(null);
    const id = await op.start({ facts: scenario.facts, lang: scenario.lang, fallback: scenario.lines.default });
    if (id) setSelectedId(id);
  };
  // An operator takes over a ticket's call: Surgeline stops talking (if it was) and keeps taking notes
  const takeOver = async (t) => {
    const sc = call.callId === t.id ? call.scenario : null;
    if (call.callId === t.id && call.active) call.stopForTakeover();
    setView("operator");
    setSelectedId(t.id);
    await op.start({ ticketId: t.id, facts: sc?.facts || factsFromTicket(t), lang: sc?.lang || t.language || "hi-IN",
      fallback: sc?.lines?.default });
  };
  const startCall = async (opts) => {
    setView("call");
    setSelectedId(null);
    const id = await call.start(opts);
    if (id) setSelectedId(id);
    refresh();
  };
  const select = (id) => {
    setSelectedId(id);
    setView(id && id === op.callId && op.active ? "operator"
      : id && id === call.callId && call.phase !== "idle" && call.phase !== "ended" ? "call" : "ticket");
  };
  const showCall = view === "call" && call.phase !== "idle";
  const showOperator = view === "operator" && op.phase !== "idle";

  const tickets = board?.tickets || [];
  const teams = board?.teams || [];
  const now = board?.now;

  // A ticket that newly becomes P0, or newly needs an operator, flashes once (and chimes if sound is on)
  useEffect(() => {
    if (!board) return;
    const key = (t) => `${t.id}:${t.priority}:${t.needs_operator}`;
    const urgent = new Set(tickets.filter((t) => (t.priority === "P0" || t.needs_operator) && stage(t) !== "closed").map(key));
    if (seenUrgent.current === null) { seenUrgent.current = urgent; return; }
    const fresh = tickets.filter((t) => urgent.has(key(t)) && !seenUrgent.current.has(key(t))).map((t) => t.id);
    seenUrgent.current = urgent;
    if (!fresh.length) return;
    setFlashing((f) => new Set([...f, ...fresh]));
    if (sound) chime();
    setTimeout(() => setFlashing((f) => { const n = new Set(f); fresh.forEach((i) => n.delete(i)); return n; }), 1800);
  }, [board]); // eslint-disable-line react-hooks/exhaustive-deps

  const selected = tickets.find((t) => t.id === selectedId);
  const open = tickets.filter((t) => stage(t) !== "closed");
  const count = (p) => open.filter((t) => (t.priority || "P3") === p).length;
  const desk = board?.desk;

  const startShift = async () => {
    await api.startShift();
    setConfirmShift(false);
    setSelectedId(null);
    setView("ticket");
    await refresh();
  };

  return (
    <div className="dash">
      <header className="topbar">
        <div className="brand">
          <span className="brand-name">Surgeline</span>
          <span className="brand-place">Control room</span>
        </div>
        <ul className="counts" aria-label="Open tickets by priority">
          {["P0", "P1", "P2", "P3"].map((p) => (
            <li key={p} className={`count c-${p}${count(p) ? "" : " zero"}`}>
              <PriorityTag priority={p} /><span className="count-n">{count(p)}</span>
            </li>
          ))}
        </ul>
        <div className="topbar-right">
          <button type="button" className={`btn small${!selected && !showCall && !showOperator ? " current" : ""}`} disabled={call.active || op.active}
            onClick={() => { setView("ticket"); setSelectedId(null); }}>{call.active || op.active ? "Call in progress" : "New call"}</button>
          {desk && <span className="desk" title="Surgeline answers when every human operator is on a call">Human desk: {desk.busy} of {desk.operators} on calls</span>}
          {confirmShift ? (
            <span className="confirm">
              Hide all {tickets.length} tickets from the board?
              <button className="btn primary small" type="button" onClick={startShift}>Start new shift</button>
              <button className="btn small" type="button" onClick={() => setConfirmShift(false)}>Cancel</button>
            </span>
          ) : (
            <button className="btn small" type="button" onClick={() => setConfirmShift(true)}>Start new shift</button>
          )}
          <button className={`toggle${sound ? " on" : ""}`} type="button" aria-pressed={sound}
            onClick={() => { setSound((s) => !s); if (!sound) chime(); }}>{sound ? "Alert sound on" : "Alert sound off"}</button>
          <a className="screen-link" href="#/call">Call screen</a>
          {now && <time className="clock">{clock(now)}</time>}
        </div>
      </header>

      {error && <div className="banner error-banner" role="alert">Can't reach the server. Retrying. ({error})</div>}

      <main className="dash-body">
        <Queue tickets={tickets} now={now} selectedId={selectedId} onSelect={select} flashing={flashing} />
        <div className="map-col">
          <MapView tickets={tickets} teams={teams} selectedId={selectedId} onSelect={select} />
          <ul className="team-strip" aria-label="Rescue teams">
            {teams.map((x) => (
              <li key={x.id} className={x.busy_with ? "busy" : "free"}>
                <span className="team-name">{x.name}</span>
                <span className="team-state">{x.busy_with ? <button type="button" className="link-btn" onClick={() => select(x.busy_with)}>On ticket {x.busy_with}</button> : "Free"}</span>
              </li>
            ))}
          </ul>
        </div>
        {showOperator ? (
          <OperatorCallPanel op={op} row={tickets.find((x) => x.id === op.callId)}
            onOpenTicket={() => { setView("ticket"); setSelectedId(op.callId); refresh(); }} />
        ) : showCall ? (
          <LiveCallPanel call={call} notes={tickets.find((x) => x.id === call.callId)?.notes}
            onTakeOver={() => { const row = tickets.find((x) => x.id === call.callId); if (row) takeOver(row); }}
            onEnded={() => { setView("ticket"); setSelectedId(call.callId); refresh(); }} />
        ) : selected ? (
          <TicketDetail t={selected} teams={teams} now={now} onChanged={refresh} onClose={() => setSelectedId(null)}
            onTakeOver={op.active || call.active ? null : takeOver} />
        ) : (
          <aside className="detail detail-empty">
            <section className="empty-call">
              <p className="empty-title">Take a call</p>
              <p className="muted">Every human operator is busy, so Surgeline answers. Use your microphone as the caller, or play a simulated caller.</p>
              <StartCall compact scenarioId={scenarioId} setScenarioId={setScenarioId} scenario={scenario}
                onMic={() => startCall({ mode: "mic" })} onSim={() => startCall({ mode: "sim", scenario })}
                onOperator={answerYourself} />
              <p className="muted start-note">{scenario.summary}</p>
            </section>
            <p className="muted empty-or">Or pick a ticket from the list or the map to see what the caller said and send a team.</p>
          </aside>
        )}
      </main>
    </div>
  );
}
