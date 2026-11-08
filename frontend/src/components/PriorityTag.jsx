import { PRIORITY } from "../lib/format.js";

export default function PriorityTag({ priority, long = false }) {
  const p = PRIORITY[priority] ? priority : "P3";
  return (
    <span className={`ptag ptag-${p}`} title={PRIORITY[p].name}>
      <span className="ptag-code">{p}</span>
      {long && <span className="ptag-name">{PRIORITY[p].name}</span>}
    </span>
  );
}
