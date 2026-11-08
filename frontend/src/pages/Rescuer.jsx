import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { FIELD_STATUS, VULNERABLE, addressLine, floorLabel } from "../lib/format.js";
import DepthGauge from "../components/DepthGauge.jsx";
import PriorityTag from "../components/PriorityTag.jsx";

const ACTIONS = [
  { status: "on_the_way", label: "On the way" },
  { status: "rescued", label: "Rescued" },
  { status: "not_found", label: "Not found" },
];

/** /rescuer/:id — the assigned team's phone, opened from the SMS link. */
export function RescuerPage() {
  const { id } = useParams();
  const [t, setT] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    try { setT(await api.rescuer(id)); setError(null); } catch (e) { setError(e.message); }
  }, [id]);
  useEffect(() => { load(); const i = setInterval(load, 2000); return () => clearInterval(i); }, [load]);
  return (
    <div className="phone-page">
      <div className="phone rescuer">
        {error && !t ? <p className="phone-hint">{error}</p> : t ? <RescuerTicket t={t} onChanged={load} /> : <p className="phone-hint">Loading</p>}
      </div>
    </div>
  );
}

function RescuerTicket({ t, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const status = t.dispatch?.field_status;
  const closed = status === "rescued" || status === "not_found";
  const loc = t.location || {};

  const press = async (s) => {
    setBusy(true); setError(null);
    try { await api.field(t.id, s); await onChanged(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <>
      <header className="phone-head">
        <p className="phone-name">{t.dispatch?.team?.name || "Rescue team"}</p>
        <p className="phone-meta">Ticket {t.id}</p>
      </header>
      <div className="rescuer-body">
        {t.sms && (
          <figure className="sms">
            <figcaption>SMS from Surgeline</figcaption>
            <pre>{t.sms}</pre>
          </figure>
        )}
        <div className="rescuer-card">
          <PriorityTag priority={t.priority} long />
          <p className="address">{addressLine(t) || "Address not known"}</p>
          {floorLabel(loc.floor) && <p>{floorLabel(loc.floor)}</p>}
          {loc.landmark && <p>Near {loc.landmark}</p>}
          <div className="rescuer-row">
            <div>
              <p className="big">{t.people_count ? `${t.people_count} people` : "People not known"}</p>
              {(t.vulnerable || []).length > 0 && <p>{t.vulnerable.map((v) => VULNERABLE[v] || v).join(", ")}</p>}
            </div>
            <DepthGauge level={t.danger?.water_level} rising={t.danger?.water_rising} />
          </div>
          {loc.lat != null && (
            <a className="btn wide" href={`https://maps.google.com/?q=${loc.lat},${loc.lon}`} target="_blank" rel="noreferrer">Open in maps</a>
          )}
        </div>
        <p className="rescuer-status">{FIELD_STATUS[status] || "Not assigned"}</p>
        {!closed && (
          <div className="rescuer-actions">
            {ACTIONS.map((a) => (
              <button key={a.status} className={`btn big-btn${status === a.status ? " current" : ""}${a.status === "rescued" ? " primary" : ""}`}
                disabled={busy || status === a.status || (a.status === "on_the_way" && status !== "assigned")}
                onClick={() => press(a.status)}>{a.label}</button>
            ))}
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    </>
  );
}
