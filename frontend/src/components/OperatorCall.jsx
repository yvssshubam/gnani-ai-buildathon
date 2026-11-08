import PriorityTag from "./PriorityTag.jsx";
import { AiNotes, CallTranscript, OperatorNotes } from "./Notes.jsx";
import { LANGUAGE, addressLine, peopleLine, WATER_TEXT } from "../lib/format.js";

function Status({ op }) {
  const { phase, level } = op;
  if (phase === "operator" || phase === "hearing") {
    const bars = Array.from({ length: 9 }, (_, i) => Math.max(0.15, Math.min(1, level * (0.6 + ((i * 37) % 10) / 10))));
    return (
      <p className={`speaking caller${phase === "operator" ? " idle" : ""}`}>
        <span className="mic" aria-hidden="true">{bars.map((h, i) => <i key={i} style={{ transform: `scaleY(${h})` }} />)}</span>
        {phase === "hearing" ? "You're speaking" : "Your turn. Speak now."}
      </p>
    );
  }
  if (phase === "caller") return <p className="speaking agent"><span className="wave" aria-hidden="true">{Array.from({ length: 9 }, (_, i) => <i key={i} />)}</span>Caller speaking (simulated)</p>;
  if (phase === "thinking") return <p className="speaking muted">Transcribing</p>;
  if (phase === "ringing") return <p className="speaking muted">Connecting</p>;
  return <p className="speaking muted">{phase === "ended" ? "Call ended" : ""}</p>;
}

/** A call a human operator is on: the conversation, Surgeline's notes, the operator's notes and the check. */
export default function OperatorCallPanel({ op, row, onOpenTicket }) {
  const t = row;
  const notes = t?.notes;
  return (
    <aside className="detail op-panel" aria-label="Operator call">
      <header className="detail-head">
        <div className="detail-title">
          <h2>{op.callId ? `Ticket ${op.callId}` : "Connecting"}</h2>
          <span className="live-timer small">{op.active && op.phase !== "ringing" ? <><span className="rec-dot" />On the line {op.timer}</> : op.phase === "ended" ? `Ended ${op.timer}` : ""}</span>
        </div>
        <div className="live-panel-sub">
          {t?.priority && t?.transcript?.some((x) => x.role === "caller") && <PriorityTag priority={t.priority} long />}
          {t?.language && <span className="phone-lang">{LANGUAGE[t.language] || t.language}</span>}
          <span className="muted">You're on the call. Surgeline is taking notes.</span>
        </div>
      </header>

      <div className="op-call">
        <div className="op-transcript">{t ? <CallTranscript t={t} notes={notes} operatorView /> : <p className="muted">Connecting the call.</p>}</div>
        <div className="live-panel-foot">
          <Status op={op} />
          {op.note && <p className="muted">{op.note}</p>}
          <div className="phone-controls">
            {op.phase === "hearing" && <button type="button" className="btn small" onClick={op.finishNow}>Done speaking</button>}
            {op.active && <button type="button" className="end-btn small" onClick={op.end}>End call</button>}
            {op.phase === "ended" && <button type="button" className="btn primary small" onClick={onOpenTicket}>Open ticket to assign a team</button>}
          </div>
        </div>
      </div>

      <div className="op-side">
        {t && (
          <section className="block op-facts">
            <h3>Ticket so far</h3>
            <p className="address">{addressLine(t) || "Address not known yet"}</p>
            <p>{peopleLine(t)}. {WATER_TEXT[t.danger?.water_level] || "Water level not known"}{t.danger?.water_rising ? ", rising" : ""}.</p>
          </section>
        )}
        <div className="block"><AiNotes notes={notes} live /></div>
        {op.callId && <div className="block"><OperatorNotes ticketId={op.callId} notes={notes} /></div>}
      </div>
    </aside>
  );
}
