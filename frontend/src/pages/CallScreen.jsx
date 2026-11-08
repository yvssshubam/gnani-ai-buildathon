import { useState } from "react";
import PriorityTag from "../components/PriorityTag.jsx";
import { Conversation, LiveTicket, Speaking } from "../components/LiveCall.jsx";
import { LANGUAGE } from "../lib/format.js";
import { SCENARIOS } from "../lib/scenarios.js";
import { mmss, useVoiceCall } from "../lib/useVoiceCall.js";

/** The demo call screen: the caller's phone on the left, the ticket filling in on the right. */
export default function CallScreen() {
  const call = useVoiceCall();
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [timings, setTimings] = useState(false);
  const scenario = SCENARIOS.find((s) => s.id === scenarioId);
  const t = call.ticket;

  return (
    <div className="call-page">
      <header className="call-bar">
        <span className="brand-name">Surgeline</span>
        <span className="call-bar-note">
          {call.phase === "idle" ? "Flood rescue line" : "All 3 operators are on other calls. Surgeline answered this one."}
        </span>
        {call.active && call.phase !== "ringing" && <span className="live-timer"><span className="rec-dot" />Live call {mmss(call.seconds)}</span>}
        {call.phase === "ended" && <span className="live-timer ended">Call ended {mmss(call.seconds)}</span>}
        <a className="screen-link" href="#/dashboard">Control room</a>
      </header>

      <div className="call-body">
        <section className="call-phone" aria-label="Caller's phone">
          <div className="phone-head">
            <p className="phone-name">Surgeline</p>
            <p className="phone-meta">
              {call.callId ? `Ticket ${call.callId}` : "Flood rescue line"}
              {t?.language && <span className="phone-lang">{LANGUAGE[t.language] || t.language}</span>}
            </p>
          </div>
          <Conversation call={call} timings={timings} />
          <div className="phone-foot">
            <Speaking call={call} />
            {call.active ? (
              <div className="phone-controls">
                {call.phase === "hearing" && <button type="button" className="btn" onClick={call.finishNow}>Done speaking</button>}
                <button type="button" className="end-btn" onClick={call.hangUp}>End</button>
              </div>
            ) : (
              <StartCall scenarioId={scenarioId} setScenarioId={setScenarioId} scenario={scenario}
                onMic={() => call.start({ mode: "mic" })} onSim={() => call.start({ mode: "sim", scenario })}
                again={call.phase === "ended"} />
            )}
            <label className="timings-toggle"><input type="checkbox" checked={timings} onChange={(e) => setTimings(e.target.checked)} /> Show timings</label>
          </div>
        </section>

        <section className="live-ticket" aria-label="Ticket filling in live">
          <div className="lt-head">
            <h1>{call.callId ? `Ticket ${call.callId}` : "Ticket"}</h1>
            <span className="muted">{call.phase === "ended" ? call.endNote : call.active ? "Filling in as the caller talks" : "Starts when a call comes in"}</span>
            {t?.priority && <span className="lt-priority"><PriorityTag priority={t.priority} long /></span>}
          </div>
          <LiveTicket call={call} />
          {call.phase === "ended" && call.callId && (
            <div className="lt-foot"><a className="btn primary" href="#/dashboard">Open in the control room</a></div>
          )}
        </section>
      </div>
    </div>
  );
}

/** Start a real microphone call, or a simulated caller from a script. */
export function StartCall({ scenarioId, setScenarioId, scenario, onMic, onSim, onOperator, again, compact }) {
  return (
    <div className={`start-call${compact ? " compact" : ""}`}>
      <div className="start-row">
        <button type="button" className="call-btn" onClick={onMic}>{again ? "Call again" : "Call"} with microphone</button>
      </div>
      <div className="start-row sim">
        <label className="sr-only" htmlFor="scenario">Simulated caller</label>
        <select id="scenario" value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
          {SCENARIOS.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <button type="button" className="btn" onClick={onSim}>Simulate call</button>
      </div>
      {onOperator && (
        <div className="start-row">
          <button type="button" className="btn wide" onClick={onOperator}>Answer it yourself (Surgeline takes notes)</button>
        </div>
      )}
      {!compact && <p className="muted start-note">{scenario.summary}</p>}
    </div>
  );
}
