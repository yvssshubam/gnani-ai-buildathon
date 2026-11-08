import { waterRank } from "./format.js";

function km(aLat, aLon, bLat, bLon) {
  const r = (d) => (d * Math.PI) / 180;
  const h = Math.sin(r(bLat - aLat) / 2) ** 2 + Math.cos(r(aLat)) * Math.cos(r(bLat)) * Math.sin(r(bLon - aLon) / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}

/** Rough travel time: boats about 12 km/h through flooded streets, trucks 20 km/h, plus 3 min to set off. */
function minutes(team, distance) {
  const speed = team.deep_water ? 12 : 20;
  return Math.round(3 + (distance / speed) * 60);
}

/**
 * Free teams for a ticket, best first: ones that can do the job (deep water, medical) before
 * ones that can't, then nearest. Each comes with distance, travel time and any warning.
 */
export function suggestTeams(t, teams) {
  const lat = t.location?.lat, lon = t.location?.lon;
  const deep = waterRank(t.danger?.water_level) >= 3; // waist or higher
  const medical = Boolean(t.medical_need || t.danger?.injured || t.danger?.medical_emergency);
  return teams
    .filter((x) => !x.busy_with || x.busy_with === t.id)
    .map((x) => {
      const d = lat != null && x.lat != null ? km(lat, lon, x.lat, x.lon) : null;
      const warnings = [];
      if (deep && !x.deep_water) warnings.push("Can't go into waist-deep water");
      if (t.people_count && t.people_count > x.seats) warnings.push(`Needs 2 trips (${x.seats} seats)`);
      // Can't do the job: last. Medical team on a non-medical case: after the others, to keep it free.
      const fit = (deep && !x.deep_water ? 2 : 0) + (medical && !x.medical ? 1 : 0) + (!medical && x.medical ? 0.5 : 0);
      return { ...x, distance: d, minutes: d == null ? null : minutes(x, d), warnings, fit };
    })
    .sort((a, b) => a.fit - b.fit || (a.distance ?? 1e9) - (b.distance ?? 1e9));
}

/** "2.1 km, about 14 min", or null if either place has no coordinates. */
export function travelText(x) {
  if (x.distance == null) return null;
  return `${Math.round(x.distance * 10) / 10} km, about ${x.minutes} min`;
}

export function teamDetail(x) {
  return [x.kind, travelText(x)].filter(Boolean).join(", ");
}
