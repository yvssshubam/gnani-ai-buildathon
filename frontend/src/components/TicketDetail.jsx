import { useEffect, useState } from "react";
import DepthGauge from "./DepthGauge.jsx";
import PriorityTag from "./PriorityTag.jsx";
import { AiNotes, CallTranscript, OperatorNotes } from "./Notes.jsx";
import { api } from "../lib/api.js";
import { suggestTeams, teamDetail, travelText } from "../lib/teams.js";
import { FIELD_STATUS, LANGUAGE, LOCATION_CERTAINTY, VULNERABLE, WATER_TEXT, addressLine, clock, elapsed, floorLabel, stage } from "../lib/format.js";

export default function TicketDetail({ t, teams, now, onChanged, onClose, onTakeOver }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [showAllTeams, setShowAllTeams] = useState(false);
  const [sms, setSms] = useState(null);

  useEffect(() => { setError(null); setShowAll(false); setShowAllTeams(false); }, [t.id]);

  // The SMS the assigned team received
  const teamId = t.dispatch?.team_id;
  useEffect(() => {
    setSms(null);
    if (teamId) api.rescuer(t.id).then((r) => setSms(r.sms)).catch(() => {});
  }, [t.id, teamId]);

  const run = async (fn) => {
    setBusy(true); setError(null);
    try { await fn(); await onChanged(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const loc = t.location || {};
  const danger = t.danger || {};
  const s = stage(t);
  const native = [loc.building_native, loc.street_native, loc.landmark_native].filter(Boolean).join(", ");
  const suggestions = suggestTeams(t, teams);
  const visibleTeams = showAllTeams ? suggestions : suggestions.slice(0, 3);
  const assignedTeam = teams.find((x) => x.id === teamId);
  const assigned = assignedTeam ? suggestTeams({ ...t }, [{ ...assignedTeam, busy_with: null }])[0] : null;
  const assignEvent = [...(t.dispatch?.events || [])].reverse().find((e) => /ssigned to/.test(e.text));

  return (
    <aside className="detail" aria-label={`Ticket ${t.id}`}>
      <header className="detail-head">
        <div className="detail-title">
          <h2>Ticket {t.id}</h2>
          <span className="detail-time">{t.created_at ? `Called ${clock(t.created_at)}, ${elapsed(t.created_at, now)}${elapsed(t.created_at, now) === "just now" ? "" : " ago"}` : ""}</span>
          <button className="icon-btn" type="button" onClick={onClose} aria-label="Close ticket">×</button>
        </div>
        <PriorityTag priority={t.priority} long />
        {t.priority_reasons?.length > 0 && <p className="reasons">{t.priority_reasons.join(". ")}.</p>}
      </header>

      {t.needs_operator && (
        <div className="callout">
          <p><strong>This caller needs a person.</strong> Surgeline couldn't get the details it needed{t.live ? " and is keeping them on the line" : ""}.</p>
          <button className="btn primary" type="button" disabled={busy}
            onClick={() => (onTakeOver ? onTakeOver(t) : run(() => api.takeOver(t.id)))}>Take over call</button>
        </div>
      )}
      {t.dispatch?.taken_over && <p className="note-line">An operator {t.operator_live ? "is on this call now" : "handled this call"}.</p>}

      <div className="block"><AiNotes notes={t.notes} /></div>

      <section className="block where">
        <p className="address">{addressLine(t) || "Address not known yet"}</p>
        {floorLabel(loc.floor) && <p>{floorLabel(loc.floor)}{loc.landmark ? `, near ${loc.landmark}` : ""}</p>}
        {!floorLabel(loc.floor) && loc.landmark && <p>Near {loc.landmark}</p>}
        {native && <p className="native" lang={t.language || undefined}>{native}</p>}
        <p className={`certainty c-${loc.confidence || "unknown"}`}>
          {LOCATION_CERTAINTY[loc.confidence] || LOCATION_CERTAINTY.unknown}
          {loc.confirmed ? " Read back and confirmed." : " Not yet confirmed by the caller."}
        </p>
      </section>

      <section className="block two-col">
        <div className="who">
          <p className="big">{t.people_count ? `${t.people_count} ${t.people_count === 1 ? "person" : "people"}` : "People not known"}</p>
          {(t.vulnerable || []).length > 0 && <p>{t.vulnerable.map((v) => VULNERABLE[v] || v).join(", ")}</p>}
          {t.medical_need && <p>Medical: {t.medical_need}</p>}
          {danger.injured && <p className="warn">Someone is injured</p>}
          {danger.trapped && <p className="warn">Trapped</p>}
          {danger.structure_unsafe && <p className="warn">Building unsafe</p>}
          <p className="muted">{LANGUAGE[t.language] || "Language not known"}{t.needs_interpreter ? ", needs an interpreter" : ""}</p>
          <p className="water-text">{WATER_TEXT[danger.water_level] || "Water level not known"}</p>
          {danger.water_rising && <p className="warn">Rising</p>}
        </div>
        <DepthGauge level={danger.water_level} rising={danger.water_rising} size="large" />
      </section>

      <section className="block">
        <div className="block-head">
          <h3>{showAll ? "Whole call" : "In the caller's words"}</h3>
          {(t.transcript || []).length > 0 && (
            <button className="link-btn" type="button" onClick={() => setShowAll((x) => !x)}>{showAll ? "Caller only" : "Show whole call"}</button>
          )}
        </div>
        <CallTranscript t={t} notes={t.notes} callerOnly={!showAll} />
      </section>

      {(t.dispatch?.taken_over || t.notes?.operator_notes || t.notes?.check) && (
        <div className="block"><OperatorNotes ticketId={t.id} notes={t.notes} /></div>
      )}

      {t.followup_reasons?.length > 0 && (
        <section className="block">
          <h3>Follow-up</h3>
          <ul className="plain">{t.followup_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </section>
      )}

      <section className="block">
        {assignedTeam ? (
          <>
            <div className="assigned-box">
              <p className="assigned-title">{s === "closed" ? FIELD_STATUS[t.dispatch.field_status] : `Assigned to ${assignedTeam.name}`}</p>
              <p>{s === "closed" ? `By ${assignedTeam.name}.` : `${FIELD_STATUS[t.dispatch.field_status]}. ${assigned && travelText(assigned) ? `${travelText(assigned)}. ` : ""}SMS sent${assignEvent ? ` at ${clock(assignEvent.at)}` : ""}.`}</p>
            </div>
            {sms && (
              <figure className="sms-preview">
                <figcaption>The SMS {assignedTeam.name} received</figcaption>
                <pre>{sms}</pre>
              </figure>
            )}
            <a className="link-btn" href={`#/rescuer/${t.id}`} target="_blank" rel="noreferrer">Open the team's phone view</a>
          </>
        ) : s !== "closed" && (
          <>
            <h3>{suggestions.length ? "Nearest free teams" : "Rescue teams"}</h3>
            {suggestions.length === 0 && <p className="muted">Every team is out on a rescue.</p>}
            <ul className="team-list">
              {visibleTeams.map((x, i) => (
                <li key={x.id}>
                  <span className="team-info">
                    <span className="team-name">{x.name}</span>
                    <span className="team-meta">{teamDetail(x)}</span>
                    {x.warnings.map((w) => <span key={w} className="team-warn">{w}</span>)}
                  </span>
                  <button type="button" className={`btn${i === 0 && !x.fit ? " primary" : ""}`} disabled={busy}
                    onClick={() => run(() => api.assign(t.id, x.id))}>Assign</button>
                </li>
              ))}
            </ul>
            {suggestions.length > 3 && (
              <button className="link-btn" type="button" onClick={() => setShowAllTeams((v) => !v)}>
                {showAllTeams ? "Show fewer" : `Show all ${suggestions.length} free teams`}
              </button>
            )}
          </>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </section>

      {t.dispatch?.events?.length > 0 && (
        <section className="block">
          <h3>Log</h3>
          <ul className="log">
            {t.dispatch.events.map((e, i) => <li key={i}><time>{clock(e.at)}</time>{e.text}</li>)}
          </ul>
        </section>
      )}
    </aside>
  );
}
