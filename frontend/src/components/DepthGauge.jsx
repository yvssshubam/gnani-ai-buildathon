import { WATER_LEVELS, waterMark } from "../lib/format.js";

/**
 * A river staff gauge (the painted post at bridges), filled to the caller's water level,
 * from ankle to neck. size="row": small, for lists. size="large": with level names.
 */
export default function DepthGauge({ level, rising = false, size = "row" }) {
  const mark = waterMark(level);
  const known = Boolean(mark);
  const large = size === "large";
  const W = large ? 24 : 11;
  const H = large ? 150 : 34;
  const labelW = large ? 84 : 0;
  const pad = large ? 7 : 1;
  const water = known ? Math.round(mark.at * H) : 0;
  const title = known ? `${mark.over ? "Water above neck" : `Water at ${mark.label.toLowerCase()}`}${rising ? ", rising" : ""}`
    : "Water level not known";
  const ticks = Array.from({ length: 10 }, (_, i) => i);

  return (
    <svg className={`gauge gauge-${size}`} width={W + labelW + 2} height={H + pad * 2}
      viewBox={`0 0 ${W + labelW + 2} ${H + pad * 2}`} role="img" aria-label={title}>
      <title>{title}</title>
      <g transform={`translate(1 ${pad})`}>
        <rect x="0" y="0" width={W} height={H} className={known ? "gauge-post" : "gauge-post unknown"} />
        {ticks.map((i) => (
          <rect key={i} x="0" y={H - (i + 1) * (H / 10)} width={W / 2}
            height={H / 20} className={i % 2 ? "gauge-tick light" : "gauge-tick"} />
        ))}
        {known && <rect x="0" y={H - water} width={W} height={water} className={mark.over ? "gauge-water over" : "gauge-water"} />}
        {known && !mark.over && <line x1="-1" x2={W + 1} y1={H - water} y2={H - water} className="gauge-surface" />}
        {large && WATER_LEVELS.map((l) => (
          <g key={l.key} transform={`translate(${W + 6} ${H - Math.round(l.at * H)})`}>
            <line x1="0" x2="5" y1="0" y2="0" className="gauge-label-tick" />
            <text x="9" y={l.at === 1 ? 9 : 4} className={l.key === mark?.key ? "gauge-label current" : "gauge-label"}>
              {l.key === mark?.key && mark.over ? "Above neck" : l.label}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}
