import { useEffect, useRef, useState } from "react";
import * as maplibreModule from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { placeLine, stage, waterRank } from "../lib/format.js";

// maplibre-gl 4 exposes a default export, version 5 only named exports: accept either.
const maplibregl = maplibreModule.default ?? maplibreModule;

// OpenFreeMap: free vector map tiles from OpenStreetMap data. No API key, no account, no limits.
const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
// If the tile server can't be reached, pins, circles and routes still draw on a plain background.
const FALLBACK_STYLE = {
  version: 8, sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#e9ece9" } }],
};
const DEFAULT_CENTER = [80.22, 12.98]; // [lon, lat]
const COLORS = { P0: "#a8322a", P1: "#a9631b", P2: "#4f6b78", P3: "#8b969a" };
// How far a team may have to search, by how precise the location is (metres)
const SEARCH_RADIUS = { street: 180, area: 900 };

let styleCheck = null;
function pickStyle() {
  // One quick check per page load: is OpenFreeMap reachable?
  styleCheck ||= Promise.race([
    fetch(STYLE_URL).then((r) => (r.ok ? STYLE_URL : FALLBACK_STYLE)),
    new Promise((resolve) => setTimeout(() => resolve(FALLBACK_STYLE), 4000)),
  ]).catch(() => FALLBACK_STYLE);
  return styleCheck;
}

function circle(lon, lat, metres, steps = 48) {
  const pts = [];
  const dLat = metres / 111320;
  const dLon = metres / (111320 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    pts.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return pts;
}

const fc = (features) => ({ type: "FeatureCollection", features });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const placed = (t) => t.location?.lat != null && t.location?.lon != null;

/**
 * The control room map. tickets: board rows. teams: board teams (with lat/lon).
 * mini: a small, non-interactive map centred on the one ticket (call screen).
 */
export default function MapView({ tickets, teams = [], selectedId, onSelect = () => {}, mini = false, showKey = true }) {
  const box = useRef(null);
  const map = useRef(null);
  const markers = useRef(new Map());
  const fitted = useRef(false);
  const [ready, setReady] = useState(false);
  const [offline, setOffline] = useState(false);

  // Create the map once
  useEffect(() => {
    let cancelled = false;
    pickStyle().then((style) => {
      if (cancelled || !box.current) return;
      setOffline(style === FALLBACK_STYLE);
      const m = new maplibregl.Map({
        container: box.current, style, center: DEFAULT_CENTER, zoom: mini ? 13 : 11.5,
        interactive: !mini, attributionControl: { compact: true },
      });
      if (!mini) m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      // Keep the map sized to its box (panels opening, window resizing)
      const ro = new ResizeObserver(() => m.resize());
      ro.observe(box.current);
      m.once("remove", () => ro.disconnect());
      m.on("load", () => {
        m.addSource("flood", { type: "geojson", data: fc([]) });
        m.addSource("search", { type: "geojson", data: fc([]) });
        m.addSource("routes", { type: "geojson", data: fc([]) });
        m.addLayer({ id: "flood-fill", type: "fill", source: "flood", paint: { "fill-color": "#3d7891", "fill-opacity": 0.13 } });
        m.addLayer({ id: "search-fill", type: "fill", source: "search", paint: { "fill-color": ["get", "color"], "fill-opacity": 0.06 } });
        m.addLayer({ id: "search-line", type: "line", source: "search",
          paint: { "line-color": ["get", "color"], "line-width": 1.2, "line-opacity": 0.7, "line-dasharray": [3, 3] } });
        m.addLayer({ id: "routes", type: "line", source: "routes",
          paint: { "line-color": "#1c2629", "line-width": 2, "line-dasharray": [3, 2.5] } });
        setReady(true);
      });
      map.current = m;
    });
    return () => {
      cancelled = true;
      markers.current.forEach((mk) => mk.remove());
      markers.current.clear();
      map.current?.remove();
      map.current = null;
    };
  }, [mini]);

  // Draw tickets, teams, circles and routes whenever the data changes
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const shown = tickets.filter(placed);
    const flood = [], search = [], routes = [];
    for (const t of shown) {
      const { lat, lon, confidence } = t.location;
      if (!mini && waterRank(t.danger?.water_level) >= 2 && stage(t) !== "closed") {
        flood.push({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [circle(lon, lat, 420)] } });
      }
      if (SEARCH_RADIUS[confidence]) {
        search.push({ type: "Feature", properties: { color: COLORS[t.priority] || COLORS.P3 },
          geometry: { type: "Polygon", coordinates: [circle(lon, lat, SEARCH_RADIUS[confidence])] } });
      }
      const team = teams.find((x) => x.id === t.dispatch?.team_id);
      if (team && stage(t) === "dispatched") {
        routes.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[team.lon, team.lat], [lon, lat]] } });
      }
    }
    m.getSource("flood")?.setData(fc(flood));
    m.getSource("search")?.setData(fc(search));
    m.getSource("routes")?.setData(fc(routes));

    // Tickets at the same spot (same area centre, same house) fan out a little so each stays clickable,
    // most urgent in the middle
    const spots = new Map();
    for (const t of [...shown].sort((x, y) => String(x.priority || "P3").localeCompare(String(y.priority || "P3")) || String(x.id).localeCompare(String(y.id)))) {
      const k = `${t.location.lat.toFixed(4)},${t.location.lon.toFixed(4)}`;
      spots.set(k, [...(spots.get(k) || []), t.id]);
    }
    const offsetOf = (t) => {
      const group = spots.get(`${t.location.lat.toFixed(4)},${t.location.lon.toFixed(4)}`) || [];
      const i = group.indexOf(t.id);
      if (group.length < 2 || i === 0) return [0, 0];
      const a = ((i - 1) / Math.max(1, group.length - 1)) * 2 * Math.PI - Math.PI / 2;
      return [Math.round(Math.cos(a) * 22), Math.round(Math.sin(a) * 22)];
    };

    // DOM markers: tickets and teams
    const want = new Map();
    for (const t of shown) {
      const s = stage(t);
      const sel = t.id === selectedId;
      const flag = sel || ((t.priority === "P0" || t.priority === "P1") && s !== "closed");
      const cls = `pin p-${t.priority || "P3"}${sel ? " sel" : ""}${s === "closed" ? " closed" : ""}${s === "dispatched" ? " out" : ""}`
        + `${t.priority === "P0" && s === "waiting" ? " pulse" : ""}`;
      const html = `<span class="pin-dot"></span>${flag ? `<span class="pin-flag">${esc(t.id)}</span>` : ""}`;
      want.set(`t${t.id}`, { lngLat: [t.location.lon, t.location.lat], cls, html,
        title: `${t.priority} #${t.id} ${placeLine(t)}`, onClick: () => onSelect(t.id), offset: offsetOf(t),
        z: (4 - (+String(t.priority || "P3")[1] || 3)) * 10 + (sel ? 5 : 0) });
    }
    if (!mini) {
      for (const team of teams) {
        if (team.lat == null) continue;
        const busy = Boolean(team.busy_with);
        const short = team.name.replace(/^(\w)\w*\s.*?(\d+)$/, "$1$2");
        want.set(`m${team.id}`, { lngLat: [team.lon, team.lat], cls: `team-pin${busy ? " busy" : ""}`,
          html: `<span class="team-box">${esc(short)}</span>${busy ? `<span class="team-label">${esc(team.name)}</span>` : ""}`,
          title: `${team.name}, ${busy ? `on ticket ${team.busy_with}` : "free"}`, onClick: null, z: 1 });
      }
    }
    for (const [key, mk] of markers.current) {
      if (!want.has(key)) { mk.remove(); markers.current.delete(key); }
    }
    for (const [key, spec] of want) {
      let mk = markers.current.get(key);
      if (!mk) {
        // MapLibre positions the outer element; we only ever restyle the button inside it
        const outer = document.createElement("div");
        const inner = document.createElement("button");
        inner.type = "button";
        outer.appendChild(inner);
        mk = new maplibregl.Marker({ element: outer }).setLngLat(spec.lngLat).addTo(m);
        markers.current.set(key, mk);
      }
      mk.getElement().style.zIndex = spec.z;
      const el = mk.getElement().firstChild;
      el.className = spec.cls;
      el.innerHTML = spec.html;
      el.title = spec.title;
      el.setAttribute("aria-label", spec.title);
      el.tabIndex = spec.onClick && !mini ? 0 : -1;
      el.onclick = spec.onClick && !mini ? (e) => { e.stopPropagation(); spec.onClick(); } : null;
      mk.setLngLat(spec.lngLat);
      mk.setOffset(spec.offset || [0, 0]);
    }

    // Frame the tickets once, when they first appear
    if (!fitted.current && shown.length) {
      fitted.current = true;
      m.resize();
      if (mini || shown.length === 1) m.jumpTo({ center: [shown[0].location.lon, shown[0].location.lat], zoom: mini ? 14 : 13.5 });
      else {
        const b = new maplibregl.LngLatBounds();
        shown.forEach((t) => b.extend([t.location.lon, t.location.lat]));
        m.fitBounds(b, { padding: 70, maxZoom: 13.5, duration: 0 });
      }
    }
  }, [tickets, teams, selectedId, ready, mini, onSelect]);

  // Fly to a newly selected ticket
  const sel = tickets.find((t) => t.id === selectedId && placed(t));
  const selKey = sel ? `${sel.id}:${sel.location.lat},${sel.location.lon}` : null;
  useEffect(() => {
    if (!ready || !sel || mini) return;
    map.current.easeTo({ center: [sel.location.lon, sel.location.lat], zoom: Math.max(map.current.getZoom(), 13), duration: 600 });
  }, [selKey, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className={`map${mini ? " mini" : ""}`}>
      <div ref={box} className="map-canvas" />
      {showKey && !mini && (
        <div className="map-key" aria-hidden="true">
          <span><i className="key-flood" />Reported flooding</span>
          <span><i className="key-ring" />Area only</span>
          <span><i className="key-team" />Rescue team</span>
        </div>
      )}
      {offline && !mini && <p className="map-offline">Map tiles unavailable. Showing locations only.</p>}
    </div>
  );
}
