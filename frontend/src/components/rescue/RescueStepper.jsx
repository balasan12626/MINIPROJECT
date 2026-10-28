import { memo } from "react";
import { formatTimeIST, toDate } from "../../utils/time.js";

/** The rescue flow, in order, keyed by the backend's `timestamps` fields
 * (backend/services/person_ops.py). "accepted" is stamped when the unit's
 * driver / crew lead acknowledges the dispatch request. */
export const RESCUE_STEPS = [
  { key: "queued", label: "SOS received" },
  { key: "assigned", label: "Unit + shelter allocated" },
  { key: "accepted", label: "Driver accepted" },
  { key: "en_route", label: "Driving to person" },
  { key: "to_shelter", label: "Picked up → shelter" },
  { key: "rescued", label: "Safe at shelter" },
];

/** Index of the step the person is on now. */
export function stepIndex(p) {
  switch (p?.stage) {
    case "assigned":
      return p.accepted ? 2 : 1;
    case "en_route":
      return 3;
    case "to_shelter":
      return 4;
    case "rescued":
      return 5;
    default:
      return 0;
  }
}

/** Minutes between two backend timestamps, or null. */
export function minutesBetween(a, b) {
  const x = toDate(a);
  const y = toDate(b);
  if (!x || !y) return null;
  return Math.max(0, (y.getTime() - x.getTime()) / 60000);
}

function RescueStepperInner({ p, compact = false }) {
  const now = stepIndex(p);
  const ts = p?.timestamps || {};
  const rejections = p?.rejections || [];
  return (
    <>
    {rejections.length ? (
      <ul className="rescue-rejections">
        {rejections.map((r) => (
          <li key={`${r.unit_name}@${r.at}`}>
            {r.reason === "no answer" ? "No answer from" : "Rejected by"} {r.unit_name} →{" "}
            {r.next_unit || `held: ${r.wait_reason || "no free unit"}`}
            {!compact ? <small> · {formatTimeIST(r.at)}</small> : null}
          </li>
        ))}
      </ul>
    ) : null}
    <ol className={`rescue-stepper ${compact ? "is-compact" : ""}`} aria-label={`Rescue progress for ${p?.name}`}>
      {RESCUE_STEPS.map((s, i) => {
        const state = i < now || (i === now && now === RESCUE_STEPS.length - 1) ? "done" : i === now ? "now" : "todo";
        return (
          <li key={s.key} className={`rescue-step is-${state}`}>
            <span className="rescue-step-dot" aria-hidden>
              {state === "done" ? "✓" : i + 1}
            </span>
            <span className="rescue-step-text">
              <b>{s.label}</b>
              {!compact ? <small>{ts[s.key] ? formatTimeIST(ts[s.key]) : state === "now" ? "in progress" : "—"}</small> : null}
            </span>
          </li>
        );
      })}
    </ol>
    </>
  );
}

export const RescueStepper = memo(RescueStepperInner);
export default RescueStepper;
