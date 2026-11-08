import Dashboard from "./Dashboard.jsx";
import Phone from "./Phone.jsx";
import { LatestTeamPhone } from "./Rescuer.jsx";

/** Everything on one screen for the demo video: caller, control room, rescue team. */
export default function Demo() {
  return (
    <div className="demo">
      <section className="demo-side" aria-label="Caller">
        <p className="demo-label">Caller</p>
        <Phone framed={false} />
      </section>
      <section className="demo-main" aria-label="Control room">
        <Dashboard compact />
      </section>
      <section className="demo-side" aria-label="Rescue team">
        <p className="demo-label">Rescue team</p>
        <LatestTeamPhone />
      </section>
    </div>
  );
}
