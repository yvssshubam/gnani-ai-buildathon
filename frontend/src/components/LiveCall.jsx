import { useEffect, useRef, useState } from "react";
import DepthGauge from "./DepthGauge.jsx";
import MapView from "./MapView.jsx";
import PriorityTag from "./PriorityTag.jsx";
import { FIELDS, mmss } from "../lib/useVoiceCall.js";
import { LANGUAGE, PRIORITY } from "../lib/format.js";
import { AiNotes } from "./Notes.jsx";

/** The conversation, as captions on a phone. */
export function Conversation({ call, timings }) {
  const logRef = useRef(null);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }); }, [call.lines]);
  if (call.phase === "ringing") {
    return (
      <div className="ringing">
        <span className="ring-icon" aria-hidden="true" />
        <p className="ring-title">Incoming call</p>
        <p className="muted">All operators are busy. Surgeline is answering.</p>
      </div>
    );
  }
  return (
    <div className="phone-log" ref={logRef}>
      {call.lines.length === 0 && <p className="phone-hint">{call.phase === "idle" ? "Start a call to see the conversation here." : ""}</p>}
      {call.lines.map((l, i) => (
        <div key={i} className={`bubble ${l.who}`} lang={l.lang || undefined}>
          {l.text}
          {timings && l.timing && <span className="timing">{l.timing}</span>}
        </div>
      ))}
    </div>
  );
}

/** Who is talking right now. */
export function Speaking({ call }) {
  const { phase, level, mode } = call;
  if (phase === "speaking") return <p className="speaking agent"><Wave />Surgeline is speaking</p>;
  if (phase === "caller") return <p className="speaking caller"><Wave caller />Caller speaking{mode === "sim" ? " (simulated)" : ""}</p>;
  if (phase === "hearing" || phase === "listening") {
    const bars = Array.from({ length: 9 }, (_, i) => Math.max(0.15, Math.min(1, level * (0.6 + ((i * 37) % 10) / 10))));
    return (
      <p className={`speaking caller${phase === "listening" ? " idle" : ""}`}>
        <span className="mic" aria-hidden="true">{bars.map((h, i) => <i key={i} style={{ transform: `scaleY(${h})` }} />)}</span>
        {phase === "hearing" ? "Caller speaking" : "Listening. Speak now."}
      </p>
    );
  }
  if (phase === "thinking") return <p className="speaking muted">Understanding the caller</p>;
  return <p className="speaking" />;
}

function Wave({ caller }) {
  return <span className={`wave${caller ? " caller" : ""}`} aria-hidden="true">{Array.from({ length: 9 }, (_, i) => <i key={i} />)}</span>;
}

/** The ticket filling in as the caller talks: each field with the caller's words and when. */
export function LiveTicket({ call, showMap = true, compact = false }) {
  const t = call.ticket;
  const placed = t?.location?.lat != null;
  return (
    <div className={`live-ticket-body${compact ? " compact" : ""}`}>
      <div className="lt-progress">
        <div className="lt-progress-text"><span>Questions answered</span><span>{call.answered} of 7</span></div>
        <div className="segs" role="img" aria-label={`${call.answered} of 7 questions answered`}>
          {Array.from({ length: 7 }, (_, i) => <span key={i} className={i < call.answered ? "seg on" : "seg"} />)}
        </div>
      </div>
      <div className="lt-body">
        <ul className="lt-fields">
          {FIELDS.map((f) => {
            const v = call.fields[f.key];
            return (
              <li key={f.key} className={`${v ? "filled" : "empty"}${v?.fresh ? " fresh" : ""}`}>
                <span className="lt-label">{f.label}</span>
                <span className="lt-value">
                  <span className="lt-main">{v ? v.value : "Waiting"}</span>
                  {v?.heard && <span className="lt-heard" lang={v.lang || undefined}>{v.heard}</span>}
                </span>
                <span className="lt-at">{v?.at || ""}</span>
              </li>
            );
          })}
        </ul>
        <div className="lt-side">
          {showMap && (
            <div className="lt-map">
              {placed ? <MapView tickets={[{ ...t, live: true, dispatch: {} }]} mini showKey={false} />
                : <p className="muted">The pin drops when the caller names their area.</p>}
            </div>
          )}
          <div className="lt-water">
            <DepthGauge level={t?.danger?.water_level} rising={t?.danger?.water_rising} size="large" />
          </div>
          {t?.priority_reasons?.length > 0 && (
            <p className="lt-why">Why {t.priority}, {PRIORITY[t.priority]?.name.toLowerCase()}: {t.priority_reasons.join(", ")}.</p>
          )}
        </div>
      </div>
    </div>
  );
}

/** The live call as the dashboard's right panel: conversation on top, ticket below. */
export function LiveCallPanel({ call, onEnded, onTakeOver, notes }) {
  const [timings, setTimings] = useState(false);
  const t = call.ticket;
  return (
    <aside className="detail live-panel" aria-label="Live call">
      <header className="detail-head">
        <div className="detail-title">
          <h2>{call.callId ? `Ticket ${call.callId}` : "Incoming call"}</h2>
          <span className="live-timer small">
            {call.active && call.phase !== "ringing" ? <><span className="rec-dot" />Live {mmss(call.seconds)}</> : call.phase === "ended" ? `Ended ${mmss(call.seconds)}` : ""}
          </span>
        </div>
        <div className="live-panel-sub">
          {t?.priority ? <PriorityTag priority={t.priority} long /> : <span className="muted">Priority set as details come in</span>}
          {t?.language && <span className="phone-lang">{LANGUAGE[t.language] || t.language}</span>}
          {call.mode === "sim" && <span className="muted">Simulated caller</span>}
        </div>
      </header>
      <div className="live-panel-call">
        <Conversation call={call} timings={timings} />
        <div className="live-panel-foot">
          <Speaking call={call} />
          <div className="phone-controls">
            {call.phase === "hearing" && <button type="button" className="btn small" onClick={call.finishNow}>Done speaking</button>}
            {call.active && call.callId && onTakeOver && <button type="button" className="btn small" onClick={onTakeOver}>Take over call</button>}
            {call.active && <button type="button" className="end-btn small" onClick={call.hangUp}>End call</button>}
            {call.phase === "ended" && <button type="button" className="btn primary small" onClick={onEnded}>Open ticket to assign a team</button>}
          </div>
          <label className="timings-toggle"><input type="checkbox" checked={timings} onChange={(e) => setTimings(e.target.checked)} /> Show timings</label>
        </div>
      </div>
      <LiveTicket call={call} showMap={false} compact />
      <div className="block live-notes"><AiNotes notes={notes} live /></div>
    </aside>
  );
}
