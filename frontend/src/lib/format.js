export const PRIORITY = {
  P0: { name: "Most urgent", rank: 0 },
  P1: { name: "Urgent", rank: 1 },
  P2: { name: "Serious", rank: 2 },
  P3: { name: "Stable", rank: 3 },
};

export const LANGUAGE = { "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu", "en-IN": "English",
  "kn-IN": "Kannada", "ml-IN": "Malayalam", "bn-IN": "Bengali", "mr-IN": "Marathi" };

export const VULNERABLE = { elderly: "elderly", child: "child", infant: "baby", pregnant: "pregnant",
  sick: "sick", disabled: "disabled", unspecified: "someone vulnerable" };

// Heights on the depth gauge, as a fraction of the post: an adult standing in water, up to the neck.
export const WATER_LEVELS = [
  { key: "ankle", label: "Ankle", at: 0.14 },
  { key: "knee", label: "Knee", at: 0.34 },
  { key: "waist", label: "Waist", at: 0.56 },
  { key: "chest", label: "Chest", at: 0.78 },
  { key: "neck", label: "Neck", at: 1 },
];

/** Gauge reading for a ticket's water_level. "roof" (over their head) fills the gauge. */
export function waterMark(level) {
  if (level === "roof") return { key: "neck", label: "Above neck", at: 1, over: true };
  return WATER_LEVELS.find((l) => l.key === level) || null;
}

/** 0 = none/unknown ... 5 = neck or above. */
export function waterRank(level) {
  const i = ["ankle", "knee", "waist", "chest", "neck", "roof"].indexOf(level);
  return i === -1 ? 0 : Math.min(i + 1, 5);
}

export const WATER_TEXT = { ankle: "Ankle deep", knee: "Knee deep", waist: "Waist deep",
  chest: "Chest deep", neck: "Neck deep", roof: "Above their heads" };

export const FIELD_STATUS = {
  assigned: "Team assigned",
  on_the_way: "Team on the way",
  rescued: "Rescued",
  not_found: "Not found",
};

export const LOCATION_CERTAINTY = {
  exact: "House-level address.",
  street: "Street known, house not exact.",
  area: "Area only. The team will need to search.",
  unknown: "Location not known. Call back to locate.",
};

export function priorityRank(p) {
  return PRIORITY[p]?.rank ?? 9;
}

export function elapsed(fromSec, nowSec) {
  if (!fromSec || !nowSec) return "";
  const m = Math.max(0, Math.floor((nowSec - fromSec) / 60));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function clock(sec) {
  return new Date(sec * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function placeLine(t) {
  const loc = t.location || {};
  const parts = [loc.locality, loc.street].filter(Boolean);
  return parts.length ? parts.join(", ") : "Location not known yet";
}

export function addressLine(t) {
  const loc = t.location || {};
  return [loc.door_no && `Door ${loc.door_no}`, loc.building, loc.street, loc.locality].filter(Boolean).join(", ");
}

export function floorLabel(floor) {
  if (!floor) return null;
  const f = String(floor).toLowerCase();
  if (["ground", "0", "g"].includes(f)) return "Ground floor";
  if (["terrace", "roof"].includes(f)) return "On the terrace";
  const n = parseInt(f, 10);
  if (Number.isNaN(n)) return `${floor} floor`;
  const suffix = n === 1 ? "st" : n === 2 ? "nd" : n === 3 ? "rd" : "th";
  return `${n}${suffix} floor`;
}

export function peopleLine(t) {
  const n = t.people_count;
  const who = (t.vulnerable || []).map((v) => VULNERABLE[v] || v);
  const count = n ? (n === 1 ? "1 person" : `${n} people`) : "People not known";
  return who.length ? `${count}, incl. ${who.join(", ")}` : count;
}

/** Where a ticket sits in the control room's workflow. */
export function stage(t) {
  const fs = t.dispatch?.field_status;
  if (fs === "rescued" || fs === "not_found") return "closed";
  if (fs === "assigned" || fs === "on_the_way") return "dispatched";
  if (t.live) return "live";
  return "waiting";
}

export function lastCallerWords(t) {
  const turns = (t.transcript || []).filter((x) => x.role === "caller");
  return turns.length ? turns[turns.length - 1].text : null;
}
