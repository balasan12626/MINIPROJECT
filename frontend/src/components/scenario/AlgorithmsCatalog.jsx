import { memo, useState } from "react";

const pctTxt = (p) => (typeof p === "number" ? `${(p * 100).toFixed(1)}%` : "—");

/** Algorithms this run actually uses, in pipeline order. The descriptions are
 * fixed facts about the code; every "live" figure comes from the current
 * simulation state passed in by the caller. */
function buildCatalog(s) {
  const clusters = s.clusters || [];
  const people = s.citizens || [];
  const byPriority = {};
  for (const p of people) {
    const k = p.vulnerability || "standard";
    byPriority[k] = (byPriority[k] || 0) + 1;
  }
  const methods = {};
  for (const p of people) {
    const m = p.route_to_person?.method;
    if (m) methods[m] = (methods[m] || 0) + 1;
  }
  const used = (s.allocation || []).filter((x) => x.allocated_this_run > 0);
  const qs = people.flatMap((p) => [p.route_to_person?.quantum, p.route_to_shelter?.quantum]).filter((q) => q?.candidates);
  const ma = s.multiAgent || {};
  const v2 = s.prediction?.v2 || {};
  const dual = s.prediction?.dual || {};

  return [
    {
      id: "kmeans",
      step: "1 · Group SOS calls",
      name: "K-means clustering",
      lib: "scikit-learn KMeans (k = min(teams, SOS, 8), n_init 10, seed 42)",
      what: "Groups SOS GPS points into clusters and links each cluster to the nearest rescue team. A new SOS joins the nearest existing cluster, so nobody already in progress is re-clustered.",
      live: clusters.length
        ? `${clusters.length} clusters from ${people.length} SOS · ${clusters
            .map((c) => `${c.cluster_id}: ${c.sos_count}`)
            .join(", ")}`
        : "Clusters appear after the SOS queue is ingested.",
    },
    {
      id: "priority",
      step: "2 · Order the queue",
      name: "Vulnerable-first priority queue",
      lib: "backend/services/priority.py",
      what: "Children, elderly and chest-deep water cases are dispatched first. The administrator agent dispatches one SOS every few seconds in that order.",
      live: Object.keys(byPriority).length
        ? Object.entries(byPriority)
            .map(([k, n]) => `${k}: ${n}`)
            .join(" · ")
        : "—",
    },
    {
      id: "dispatch",
      step: "3 · Pick a unit",
      name: "Unit allocation (greedy, capacity-aware)",
      lib: "backend/services/person_ops.py",
      what: "Vulnerable or injured callers get the first free ambulance from a pool of 10, sent from the depot nearest the person; everyone else gets their cluster's rescue team. If every ambulance is busy, the SOS waits in the queue.",
      live: s.fleet
        ? `${s.fleet.ambulances_busy} ambulances busy · ${s.fleet.ambulances_free} free · ${(s.fleet.rescue_units_active || []).length} rescue teams on a job`
        : "—",
    },
    {
      id: "shelter",
      step: "4 · Pick a shelter",
      name: "Nearest shelter with free seats",
      lib: "backend/services/person_ops.py",
      what: "Chooses the closest shelter (straight-line distance) whose capacity minus occupancy minus seats already allocated this run still fits the whole group.",
      live: used.length ? `${used.length} shelters used: ${used.map((x) => `${x.name} (+${x.allocated_this_run})`).join(", ")}` : "No shelter allocated yet.",
    },
    {
      id: "routing",
      step: "5 · Plan the route",
      name: "Yen k-shortest paths + QAOA route choice (simulated)",
      lib: "networkx shortest_simple_paths → backend/optimization/qaoa_route.py (numpy statevector, COBYLA)",
      what: "Blocked roads are removed from the flood-weighted road graph. Yen's algorithm gives up to 4 candidate routes (the first one is the Dijkstra shortest path). Picking one is a one-hot QUBO — travel time + flood exposure — solved by a 3-layer QAOA circuit simulated exactly on a classical computer; the cheapest measured route is driven. Leg 2 is recomputed at pickup. No quantum hardware, no speed-up claimed.",
      live: Object.keys(methods).length
        ? `${Object.entries(methods)
            .map(([k, n]) => `${k}: ${n}`)
            .join(" · ")}${qs.length ? ` · QAOA matched the exhaustive optimum ${qs.filter((q) => q.matches_exhaustive).length}/${qs.length}` : ""}`
        : "No routes yet.",
    },
    {
      id: "arena",
      step: "5b · Compare routers",
      name: "Algorithm Arena: Dijkstra vs A*",
      lib: "backend/services/algorithm_arena.py",
      what: "Runs distance-only Dijkstra, flood-aware Dijkstra and flood-aware A* on the same trips and scores them. Its results are on the Routes tab.",
      live: "See Routes tab → Algorithm Arena.",
    },
    {
      id: "ml",
      step: "6 · Predict the flood",
      name: `Two-stage flood model: ${v2.stage1_model || "stage 1"} → ${v2.stage2_model || "stage 2"}`,
      lib: "backend/ml/inference.py (v2 path)",
      what: "Stage 1 predicts the peak flood level; stage 2 classifies the alert level. Its probability is blended with the physics twin for the final decision.",
      live: v2.available
        ? `peak ${v2.predicted_peak_flood_level_m} m · severe-flood ${pctTxt(v2.flood_type_probability)} · alert ${v2.alert_level || "—"}`
        : v2.message || "Waiting for the first tick.",
    },
    {
      id: "crosscheck",
      step: "6b · Safety cross-check",
      name: "Random Forest vs XGBoost (v1 models)",
      lib: "backend/ml (v1 artifacts)",
      what: "Two older models score the same reading. If they disagree by too much, auto-dispatch is held until an operator overrides.",
      live: dual.available ? `RF ${pctTxt(dual.random_forest)} · XGB ${pctTxt(dual.xgboost)} · ${dual.disagree ? "DISAGREE" : "agree"}` : "Loads with the first tick.",
    },
    {
      id: "iforest",
      step: "6c · Sensor anomaly",
      name: "Isolation Forest + sudden-change monitor",
      lib: "scikit-learn IsolationForest (backend/ml/change_monitor.py)",
      what: "Flags sudden jumps in rainfall / river / dam readings between samples.",
      live: s.cardMonitor?.sudden ? `${(s.cardMonitor.alerts || []).length} sudden change(s) flagged` : "No sudden change flagged.",
    },
    {
      id: "mas",
      step: "8 · Coordinate",
      name: "Multi-agent system: Manager + 8 agents",
      lib: "backend/agents/mas.py — rule-based agents, shared message board",
      what: "Probability, Flood and Dam agents report to the Manager. Below 50% flood probability the Manager hands the decision to the Administrator (human review); at 50% it declares CRITICAL and tells ambulances, rescue teams and shelters to be ready; at 75% all units go on the field. Ambulance, Rescue, Shelter and Route agents report every dispatch, accept, pickup and admission.",
      live: ma.tier ? `${ma.tier_label} · ${(ma.messages || []).length} messages` : "Starts with the run.",
    },
    {
      id: "hqrl",
      step: "9 · Benchmark the planner",
      name: "HQRL evacuation planner vs baselines",
      lib: "backend/api/hqrl.py — seeded scenarios",
      what: "Compares the HQRL planner with baseline planners on seeded evacuation scenarios built from this run's inputs. Results table and charts are below.",
      live: "See the benchmark below.",
    },
  ];
}

function AlgorithmsCatalog(props) {
  const [open, setOpen] = useState("kmeans");
  const items = buildCatalog(props);
  return (
    <div className="panel algo-catalog">
      <div className="panel-head">
        <h3>Algorithms used in this run</h3>
        <span className="badge sim">{items.length} stages</span>
      </div>
      <p className="hint">From SOS call to shelter, in the order the pipeline runs them. Click one to see what it does.</p>
      <ol className="algo-flow">
        {items.map((a) => (
          <li key={a.id} className={`algo-item ${open === a.id ? "is-open" : ""}`}>
            <button type="button" className="algo-head" aria-expanded={open === a.id} onClick={() => setOpen(open === a.id ? null : a.id)}>
              <span className="algo-step">{a.step}</span>
              <b>{a.name}</b>
              <span className="algo-live">{a.live}</span>
            </button>
            {open === a.id ? (
              <div className="algo-body">
                <p>{a.what}</p>
                <p className="muted">
                  <code>{a.lib}</code>
                </p>
              </div>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}

export default memo(AlgorithmsCatalog);
