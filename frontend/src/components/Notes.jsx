import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";

const KIND = { hazard: "Hazard", medical: "Medical", mobility: "Mobility", access: "Access", needs: "Needs", contact: "Contact", other: "Note" };

/** Surgeline's own notes for the call: summary + details that don't fit the ticket's fields. */
export function AiNotes({ notes, live }) {
  if (!notes?.summary && !notes?.details?.length) {
    return live ? <section className="ai-notes empty"><h3>Surgeline's notes</h3><p className="muted">Notes appear after the caller's first answer.</p></section> : null;
  }
  return (
    <section className="ai-notes" aria-label="Surgeline's notes">
      <h3>Surgeline's notes</h3>
      {notes.summary && <p className="ai-summary">{notes.summary}</p>}
      {notes.details?.length > 0 && (
        <ul className="ai-details">
          {notes.details.map((d, i) => (
            <li key={i} className={`k-${d.kind}`}>
              <span className="ai-kind">{KIND[d.kind] || "Note"}</span>
              <span className="ai-text">{d.text}</span>
              {d.at && <time>{d.at}</time>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The call, line by line, with an English translation under each caller line. */
export function CallTranscript({ t, notes, operatorView = false, callerOnly = false }) {
  const ref = useRef(null);
  const turns = (t?.transcript || []).map((x, i) => ({ ...x, i })).filter((x) => !callerOnly || x.role === "caller");
  // During a live call, keep the newest line in view (the scrolling box is the list's container)
  useEffect(() => {
    const box = operatorView ? ref.current?.closest(".op-transcript") : null;
    box?.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [turns.length, operatorView]);
  if (!turns.length) return <p className="muted">Nothing said yet.</p>;
  const who = { caller: "Caller", agent: "Surgeline", operator: operatorView ? "You" : "Operator" };
  return (
    <ul className={`transcript${operatorView ? " op" : ""}`} ref={ref}>
      {turns.map((x) => {
        const en = notes?.translations?.[String(x.i)];
        return (
          <li key={x.i} className={x.role}>
            {!callerOnly && <span className="who-label">{who[x.role] || x.role}</span>}
            <span lang={x.lang || undefined}>{x.text}</span>
            {en && en !== x.text && <span className="translation">{en}</span>}
          </li>
        );
      })}
    </ul>
  );
}

const STATUS = {
  differs: { label: "Differs", cls: "differs" },
  not_heard: { label: "Not heard in the call", cls: "not-heard" },
  missing: { label: "Missing from your notes", cls: "missing" },
  match: { label: "Matches", cls: "match" },
};

/** The operator's notes box, with "Check my notes" against the call. */
export function OperatorNotes({ ticketId, notes, readOnly = false }) {
  const [text, setText] = useState(notes?.operator_notes || "");
  const [items, setItems] = useState(notes?.check || null);
  const [done, setDone] = useState({});   // index -> "used" | "kept"
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const saveTimer = useRef(null);
  const loadedFor = useRef(ticketId);

  // A different ticket: load its notes
  useEffect(() => {
    if (loadedFor.current === ticketId) return;
    loadedFor.current = ticketId;
    setText(notes?.operator_notes || ""); setItems(notes?.check || null); setDone({});
  }, [ticketId, notes]);

  const onChange = (v) => {
    setText(v);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => api.saveNotes(ticketId, v).catch(() => {}), 800);
  };

  const check = async () => {
    setBusy(true); setError(null);
    try {
      const out = await api.checkNotes(ticketId, text);
      setItems(out.check || []); setDone({});
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const applyCall = (it, i) => {
    let next = text;
    if (it.operator && next.toLowerCase().includes(String(it.operator).toLowerCase())) {
      const at = next.toLowerCase().indexOf(String(it.operator).toLowerCase());
      next = next.slice(0, at) + it.call + next.slice(at + String(it.operator).length);
    } else {
      next = `${next.trim()}${next.trim() ? "\n" : ""}${it.topic}: ${it.call}`;
    }
    onChange(next);
    setDone((d) => ({ ...d, [i]: "used" }));
  };

  const open = (items || []).filter((it, i) => it.status !== "match" && !done[i]).length;

  return (
    <section className="op-notes" aria-label="Your notes">
      <div className="block-head">
        <h3>Your notes</h3>
        {items && <span className={`check-state${open ? " open" : ""}`}>{open ? `${open} to look at` : "All checked"}</span>}
      </div>
      {readOnly ? (
        <pre className="op-notes-text">{text || "No notes written."}</pre>
      ) : (
        <textarea value={text} onChange={(e) => onChange(e.target.value)} rows={4}
          placeholder="Type as you listen: area, street, door, floor, people, water…" aria-label="Your notes" />
      )}
      {!readOnly && (
        <div className="op-notes-actions">
          <button type="button" className="btn primary small" disabled={busy} onClick={check}>
            {busy ? "Checking…" : items ? "Check again" : "Check my notes against the call"}
          </button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {items && (
        <ul className="check-list">
          {items.length === 0 && <li className="muted">Nothing to compare yet.</li>}
          {items.map((it, i) => {
            const s = STATUS[it.status];
            return (
              <li key={i} className={`check-item ${s.cls}${done[i] ? " done" : ""}`}>
                <div className="check-head"><span className="check-status">{s.label}</span><span className="check-topic">{it.topic}</span>{it.at && <time>{it.at}</time>}</div>
                {it.status !== "match" && (
                  <div className="check-body">
                    {it.operator && <p>You wrote: <strong>{it.operator}</strong></p>}
                    {it.call && <p>{it.status === "missing" ? "The caller said" : "The call says"}: <strong>{it.call}</strong></p>}
                    {it.quote && <p className="check-quote">“{it.quote}”</p>}
                    {!readOnly && !done[i] && (
                      <div className="check-actions">
                        {it.call && <button type="button" className="btn small" onClick={() => applyCall(it, i)}>Use the call's version</button>}
                        <button type="button" className="btn small" onClick={() => setDone((d) => ({ ...d, [i]: "kept" }))}>Keep mine</button>
                      </div>
                    )}
                    {done[i] && <p className="muted">{done[i] === "used" ? "Your notes were updated." : "Kept as you wrote it."}</p>}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
