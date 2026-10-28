import { memo } from "react";

const POLICY = {
  nearest_depot: "original rule (idealised)",
  first_free: "first free ambulance",
  greedy: "nearest free ambulance by road",
  optimal: "best overall assignment",
};

/** F13 — "Why this decision?" for one person, from row.decision recorded by
 * the allocator (person_ops._decision) at the moment it decided. */
function DecisionCard({ d, compact = false }) {
  if (!d) return null;
  const choice = d.unit?.choice;
  const considered = choice?.considered || [];
  return (
    <details className="decision-card" open={!compact}>
      <summary>Why this decision?</summary>
      <dl>
        <dt>Queue</dt>
        <dd>
          Rank {d.queue?.rank ?? "—"} ({d.queue?.people_ahead ?? 0} ahead) · {d.queue?.vulnerability}. {d.queue?.rule}.
          {d.queue?.waited_min != null ? ` Waited ${d.queue.waited_min} min.` : ""}
        </dd>
        <dt>Unit</dt>
        <dd>
          {d.unit?.name} ({d.unit?.role}) from {d.unit?.from || "base"} — {d.unit?.why}.
          {choice ? ` Policy: ${POLICY[choice.policy] || choice.policy} — ${choice.rule}.` : ""}
          {choice?.batch_size ? ` Solved jointly for ${choice.batch_size} waiting SOS × ${choice.free_ambulances} free ambulances.` : ""}
          {considered.length ? (
            <span className="muted">
              {" "}
              Compared:{" "}
              {considered
                .slice()
                .sort((a, b) => (a.minutes ?? 1e9) - (b.minutes ?? 1e9))
                .slice(0, 4)
                .map((c) => `${c.unit.replace("Ambulance Unit", "Unit")} ${c.minutes ?? "—"} min`)
                .join(" · ")}
            </span>
          ) : null}
          {d.unit?.rejected_before?.length ? ` Declined before by: ${d.unit.rejected_before.join(", ")}.` : ""}
        </dd>
        <dt>Shelter</dt>
        <dd>
          {d.shelter?.chosen} ({d.shelter?.km_straight ?? "—"} km) — {d.shelter?.rule}.
          {d.shelter?.next_options?.length ? (
            <span className="muted">
              {" "}
              Next options: {d.shelter.next_options.map((s) => `${s.name} ${s.km_straight} km, ${s.seats_left} seats`).join(" · ")}
            </span>
          ) : null}
          {d.shelter?.closed?.length ? ` Closed (skipped): ${d.shelter.closed.join(", ")}.` : ""}
        </dd>
        <dt>Route</dt>
        <dd>
          {d.route?.no_open_road
            ? "No open road — straight-line estimate only."
            : `${d.route?.km} km, ${d.route?.minutes} min · ${d.route?.method} over ${d.route?.candidates} candidate(s)`}
          {d.route?.qaoa_matches_exhaustive != null
            ? ` · QAOA ${d.route.qaoa_matches_exhaustive ? "=" : "≠"} best of the candidates`
            : ""}
          {d.route?.flood_forecast ? ` · ${d.route.flood_forecast.note}` : ""}
        </dd>
      </dl>
    </details>
  );
}

export default memo(DecisionCard);
