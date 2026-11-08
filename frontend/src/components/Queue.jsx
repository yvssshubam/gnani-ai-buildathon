import { useState } from "react";
import DepthGauge from "./DepthGauge.jsx";
import PriorityTag from "./PriorityTag.jsx";
import { FIELD_STATUS, LANGUAGE, PRIORITY, elapsed, lastCallerWords, peopleLine, placeLine, priorityRank, stage } from "../lib/format.js";

const oldestFirst = (a, b) => (a.created_at || 0) - (b.created_at || 0);

export default function Queue({ tickets, now, selectedId, onSelect, flashing }) {
  const [showClosed, setShowClosed] = useState(false);
  const live = tickets.filter((t) => stage(t) === "live").sort(oldestFirst);
  const waiting = tickets.filter((t) => stage(t) === "waiting");
  const out = tickets.filter((t) => stage(t) === "dispatched")
    .sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority) || oldestFirst(a, b));
  const closed = tickets.filter((t) => stage(t) === "closed").sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
  const groups = ["P0", "P1", "P2", "P3"]
    .map((p) => ({ p, items: waiting.filter((t) => (t.priority || "P3") === p).sort(oldestFirst) }))
    .filter((g) => g.items.length);

  const row = (t) => (
    <QueueRow key={t.id} t={t} now={now} selected={t.id === selectedId}
      flash={flashing.has(t.id)} onSelect={() => onSelect(t.id)} />
  );

  return (
    <nav className="queue" aria-label="Tickets">
      <section className={`live-block${live.length ? "" : " empty"}`} aria-label="On the line now">
        <h2 className="live-title"><span className="live-dot" />On the line now<span className="queue-count">{live.length}</span></h2>
        {live.length === 0 && <p className="queue-empty">No calls right now.</p>}
        {live.map((t) => {
          const words = lastCallerWords(t);
          return (
            <button key={t.id} type="button" className={`live-row${t.id === selectedId ? " selected" : ""}`} onClick={() => onSelect(t.id)}>
              <span className="live-head">#{t.id}{t.language ? `, ${LANGUAGE[t.language] || t.language}` : ""}</span>
              <span className="live-words" lang={t.language || undefined}>{words ? `“${words}”` : "Listening to the caller"}</span>
            </button>
          );
        })}
      </section>

      <div className="queue-heading-row">
        <h2 className="queue-heading">Waiting for a team</h2>
        <span className="queue-count">{waiting.length}</span>
      </div>
      {waiting.length === 0 && <p className="queue-empty">Every ticket has a team.</p>}
      {groups.map((g) => (
        <div key={g.p} className="queue-group">
          <h3 className="group-heading">{PRIORITY[g.p].name}<span className="queue-count">{g.items.length}</span></h3>
          <ul className="queue-list">{g.items.map(row)}</ul>
        </div>
      ))}

      <div className="queue-heading-row ruled">
        <h2 className="queue-heading">Team assigned</h2>
        <span className="queue-count">{out.length}</span>
      </div>
      {out.length === 0 ? <p className="queue-empty">No teams out yet.</p> : <ul className="queue-list">{out.map(row)}</ul>}

      {closed.length > 0 && (
        <div className="queue-closed">
          <button className="queue-toggle" type="button" onClick={() => setShowClosed((s) => !s)} aria-expanded={showClosed}>
            {showClosed ? "Hide" : "Show"} closed tickets ({closed.length})
          </button>
          {showClosed && <ul className="queue-list">{closed.map(row)}</ul>}
        </div>
      )}
    </nav>
  );
}

function QueueRow({ t, now, selected, flash, onSelect }) {
  const s = stage(t);
  let note = peopleLine(t);
  let noteClass = "";
  if (s === "dispatched" || s === "closed") note = `${t.dispatch?.team?.name || ""}, ${(FIELD_STATUS[t.dispatch?.field_status] || "").toLowerCase()}`;
  else if (t.needs_operator) { note = "Needs an operator"; noteClass = " alert"; }
  else if (t.location?.confidence === "area" || t.location?.confidence === "unknown") note = `${peopleLine(t)}. Location not exact`;

  return (
    <li>
      <button type="button" className={`qrow${selected ? " selected" : ""}${flash ? " flash" : ""}${s === "closed" ? " closed" : ""}`}
        onClick={onSelect} aria-current={selected ? "true" : undefined}>
        <PriorityTag priority={t.priority} />
        <span className="qrow-main">
          <span className="qrow-place">{placeLine(t)}</span>
          <span className={`qrow-sub${noteClass}`}>{note}</span>
        </span>
        <span className="qrow-side">
          <span className="qrow-age">{elapsed(t.created_at, now)}</span>
          <DepthGauge level={t.danger?.water_level} rising={t.danger?.water_rising} />
        </span>
      </button>
    </li>
  );
}
