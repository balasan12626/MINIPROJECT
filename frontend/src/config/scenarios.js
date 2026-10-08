/** THE scenario catalogue for /simulation.
 *
 * One selection fills every input on the page. One RUN SCENARIO click then
 * drives three independent backends with those inputs:
 *
 *   1. dam        -> POST /api/simulation/run          (backend/services/dam_risk.py)
 *   2. evacuation -> POST /api/simulation/start        (backend/simulation/engine.py)
 *   3. benchmark  -> POST /api/simulation/hqrl/{benchmark|ablation}
 *                                                      (backend/simulation/hqrl_demo.py)
 *
 * ---------------------------------------------------------------------------
 * WHY WE NEVER SEND `scenario` TO /api/simulation/run
 *
 * backend/api/dams.py:50-51 overwrites every typed input with the preset's
 * defaults whenever a `scenario` id is present. That made the dam input boxes
 * decorative. We therefore send raw controls only; `dam.preset` below is kept
 * as provenance metadata (which backend preset these numbers came from), not
 * as a request field. What you see in the inputs is exactly what runs.
 *
 * The evacuation engine has the mirror-image quirk: it does NOT merge a
 * scenario's defaults server-side (backend/api/simulation.py:29), so the
 * caller must send the full parameter set. Every `sim.params` below is
 * therefore complete, not partial.
 * ---------------------------------------------------------------------------
 *
 * `provenance` is deliberate and user-visible:
 *   "native"   — both halves are verbatim backend values (a real dam preset
 *                from SCENARIO_PRESETS plus a real engine scenario's defaults).
 *   "composed" — no backend preset expresses this, but the existing inputs
 *                fully describe it. Nothing is invented beyond input values.
 *
 * NOTE: dam controls are reservoir quantities (mm, cumec, m MSL) and
 * sim.dam_level is the Yamuna barrage stage. Same word, different quantity —
 * never merge them.
 */

// Real backend ids, for the guard test in ScenarioContext.test.jsx:
//   engine (backend/simulation/engine.py:13):
//     heavy_rainfall, dam_overflow, river_rise, road_blockage,
//     shelter_congestion, mass_evacuation, multiple_sos
//   dam presets (backend/services/dam_risk.py:51):
//     normal, heavy_rainfall, extreme_rainfall, emergency_release, worst_case
//   HQRL: no named scenarios exist at all — only (mode, n_scenarios, seed).

/** Seeded scenarios per HQRL benchmark/ablation run. ONE constant for both the
 * request body and every description. Mirrors the backend default
 * (backend/api/hqrl.py HqrlBenchBody.n_scenarios = 10). */
export const BENCHMARK_N_SCENARIOS = 10;

export const SCENARIO_GROUPS = [
  {
    id: "dam",
    label: "Dam Scenarios",
    hint: "Reservoir-driven. Each one is a real preset from the dam risk engine.",
  },
  {
    id: "simulation",
    label: "Simulation Scenarios",
    hint: "Response-driven. Each one is a real preset from the evacuation engine.",
  },
  {
    id: "hqrl",
    label: "IEEE HQRL Benchmark",
    hint: "The planner benchmark itself. HQRL has no named scenarios — these select the benchmark mode.",
  },
];

/** Complete evacuation-engine parameter set. The engine requires all of them. */
function simParams({
  rainfall_intensity,
  dam_level,
  river_level,
  road_blockage,
  population,
  shelter_capacity_factor,
  traffic,
  sos_count,
  ticks = 24,
  tick_seconds = 2,
}) {
  return {
    rainfall_intensity,
    dam_level,
    river_level,
    road_blockage,
    population,
    shelter_capacity_factor,
    traffic,
    sos_count,
    ticks,
    tick_seconds,
  };
}

/** Reservoir control set sent to POST /api/simulation/run. */
function damControls({ rainfall_mm, rainfall_intensity_mm_hr, inflow_cumec, outflow_cumec, forecast_hours = 72 }) {
  return { rainfall_mm, rainfall_intensity_mm_hr, inflow_cumec, outflow_cumec, forecast_hours };
}

export const SCENARIOS = [
  // ---------------------------------------------------------------- dam group
  {
    id: "normal_operation",
    group: "dam",
    label: "Normal Operation",
    description:
      "Baseline monsoon day. The reservoir sits inside its normal band, the river stays below the danger mark and roads are clear.",
    keywords: ["baseline", "calm", "normal", "low risk", "monsoon"],
    provenance: "composed",
    expectedRisk: "LOW",
    // dam: SCENARIO_PRESETS["normal"] verbatim.
    dam: { preset: "normal", controls: damControls({ rainfall_mm: 15, rainfall_intensity_mm_hr: 3, inflow_cumec: 700, outflow_cumec: 650 }) },
    // sim: river_rise re-parameterised down — the engine ships no calm preset.
    sim: {
      scenario: "river_rise",
      params: simParams({ rainfall_intensity: 18, dam_level: 199.0, river_level: 203.4, road_blockage: 0.05, population: 13000, shelter_capacity_factor: 1.0, traffic: 0.35, sos_count: 6 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
  {
    id: "heavy_rainfall",
    group: "dam",
    label: "Heavy Rainfall",
    description:
      "Sustained heavy rain lifts inflow well above release and pushes the reservoir toward its warning band while river stage climbs.",
    keywords: ["rain", "monsoon", "inflow", "warning"],
    provenance: "native",
    expectedRisk: "HIGH",
    dam: { preset: "heavy_rainfall", controls: damControls({ rainfall_mm: 90, rainfall_intensity_mm_hr: 18, inflow_cumec: 1600, outflow_cumec: 900 }) },
    sim: {
      scenario: "heavy_rainfall",
      params: simParams({ rainfall_intensity: 72, dam_level: 199.2, river_level: 204.6, road_blockage: 0.22, population: 14000, shelter_capacity_factor: 1.0, traffic: 0.55, sos_count: 10 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
  {
    id: "extreme_rainfall",
    group: "dam",
    label: "Extreme Rainfall",
    description:
      "Cloudburst-scale rainfall. Inflow nearly triples the release and the river reaches its highest modelled stage.",
    keywords: ["cloudburst", "extreme", "flash flood", "critical", "spillway"],
    provenance: "native",
    expectedRisk: "CRITICAL",
    dam: { preset: "extreme_rainfall", controls: damControls({ rainfall_mm: 220, rainfall_intensity_mm_hr: 45, inflow_cumec: 3200, outflow_cumec: 1200, forecast_hours: 24 }) },
    sim: {
      scenario: "river_rise",
      params: simParams({ rainfall_intensity: 48, dam_level: 201.0, river_level: 205.6, road_blockage: 0.2, population: 13000, shelter_capacity_factor: 1.0, traffic: 0.52, sos_count: 10 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
  {
    id: "emergency_release",
    group: "dam",
    label: "Emergency Release",
    description:
      "The reservoir raises release above inflow to protect its own storage. Downstream stage climbs even though local rain is moderate.",
    keywords: ["release", "spillway", "downstream", "overflow", "upstream dam"],
    provenance: "native",
    expectedRisk: "HIGH",
    dam: { preset: "emergency_release", controls: damControls({ rainfall_mm: 60, rainfall_intensity_mm_hr: 12, inflow_cumec: 1400, outflow_cumec: 2400 }) },
    sim: {
      scenario: "dam_overflow",
      params: simParams({ rainfall_intensity: 38, dam_level: 206.5, river_level: 205.2, road_blockage: 0.18, population: 15000, shelter_capacity_factor: 0.95, traffic: 0.5, sos_count: 10 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
  {
    id: "worst_case",
    group: "dam",
    label: "Worst-Case Inflow",
    description:
      "Peak inflow against a throttled release, with a full-scale evacuation load downstream. The hardest case the models are asked to handle.",
    keywords: ["worst case", "peak", "mass evacuation", "critical", "overtopping"],
    provenance: "native",
    expectedRisk: "CRITICAL",
    dam: { preset: "worst_case", controls: damControls({ rainfall_mm: 260, rainfall_intensity_mm_hr: 50, inflow_cumec: 3600, outflow_cumec: 700 }) },
    sim: {
      scenario: "mass_evacuation",
      params: simParams({ rainfall_intensity: 65, dam_level: 202.0, river_level: 205.4, road_blockage: 0.35, population: 22000, shelter_capacity_factor: 0.8, traffic: 0.68, sos_count: 14, ticks: 28 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
  {
    id: "drought_low_inflow",
    group: "dam",
    label: "Drought / Low Inflow",
    description:
      "Prolonged dry spell. Inflow falls below release and the reservoir draws down toward its dead-storage floor.",
    keywords: ["drought", "dry", "low inflow", "dead storage", "drawdown"],
    // No drought preset exists in SCENARIO_PRESETS — these are raw controls.
    provenance: "composed",
    expectedRisk: "LOW",
    dam: { preset: null, controls: damControls({ rainfall_mm: 2, rainfall_intensity_mm_hr: 0, inflow_cumec: 260, outflow_cumec: 640 }) },
    sim: {
      scenario: "river_rise",
      params: simParams({ rainfall_intensity: 4, dam_level: 197.5, river_level: 201.8, road_blockage: 0.0, population: 13000, shelter_capacity_factor: 1.0, traffic: 0.3, sos_count: 4 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },

  // --------------------------------------------------------- simulation group
  {
    id: "road_blockage",
    group: "simulation",
    label: "Road Blockage",
    description:
      "Over half the road network is cut and traffic is heavy. Routing, not water, is the binding constraint.",
    keywords: ["roads", "blocked", "routing", "traffic", "closure"],
    provenance: "native",
    expectedRisk: "HIGH",
    dam: { preset: "heavy_rainfall", controls: damControls({ rainfall_mm: 90, rainfall_intensity_mm_hr: 18, inflow_cumec: 1600, outflow_cumec: 900 }) },
    sim: {
      scenario: "road_blockage",
      params: simParams({ rainfall_intensity: 50, dam_level: 199.5, river_level: 204.8, road_blockage: 0.55, population: 12000, shelter_capacity_factor: 1.0, traffic: 0.72, sos_count: 8 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
  {
    id: "shelter_congestion",
    group: "simulation",
    label: "Shelter Congestion",
    description:
      "The largest population of any scenario against barely half the usual shelter capacity. Allocation is the bottleneck.",
    keywords: ["shelter", "capacity", "congestion", "overflow", "allocation"],
    provenance: "native",
    expectedRisk: "HIGH",
    dam: { preset: "heavy_rainfall", controls: damControls({ rainfall_mm: 90, rainfall_intensity_mm_hr: 18, inflow_cumec: 1600, outflow_cumec: 900 }) },
    sim: {
      scenario: "shelter_congestion",
      params: simParams({ rainfall_intensity: 52, dam_level: 200.0, river_level: 204.9, road_blockage: 0.25, population: 18000, shelter_capacity_factor: 0.55, traffic: 0.6, sos_count: 12 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
  {
    id: "multiple_sos",
    group: "simulation",
    label: "Multiple SOS Surge",
    description:
      "Calm water, clear roads, but a burst of simultaneous distress calls. Tests triage and dispatch rather than hydrology.",
    keywords: ["sos", "dispatch", "triage", "calls", "surge"],
    provenance: "native",
    expectedRisk: "MODERATE",
    dam: { preset: "normal", controls: damControls({ rainfall_mm: 15, rainfall_intensity_mm_hr: 3, inflow_cumec: 700, outflow_cumec: 650 }) },
    sim: {
      scenario: "multiple_sos",
      params: simParams({ rainfall_intensity: 55, dam_level: 199.0, river_level: 204.2, road_blockage: 0.15, population: 12000, shelter_capacity_factor: 1.0, traffic: 0.45, sos_count: 10 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },

  // --------------------------------------------------------------- hqrl group
  {
    id: "hqrl_benchmark",
    group: "hqrl",
    label: "HQRL vs 5 Baselines",
    description:
      `Runs the full benchmark: Static Shortest Path, Time-Dependent A*, Risk-Aware Greedy, PPO, PPO+QUBO and PPO+QAOA over ${BENCHMARK_N_SCENARIOS} seeded scenarios.`,
    keywords: ["benchmark", "baseline", "ppo", "qaoa", "qubo", "ieee", "comparison"],
    provenance: "native",
    expectedRisk: "CRITICAL",
    dam: { preset: "worst_case", controls: damControls({ rainfall_mm: 260, rainfall_intensity_mm_hr: 50, inflow_cumec: 3600, outflow_cumec: 700 }) },
    sim: {
      scenario: "mass_evacuation",
      params: simParams({ rainfall_intensity: 65, dam_level: 202.0, river_level: 205.4, road_blockage: 0.35, population: 22000, shelter_capacity_factor: 0.8, traffic: 0.68, sos_count: 14, ticks: 28 }),
    },
    hqrl: { mode: "benchmark", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
  {
    id: "hqrl_ablation",
    group: "hqrl",
    label: "HQRL Safety-Layer Ablation",
    description:
      `Two arms only — PPO with the safety layer removed versus full HQRL (PPO+QUBO+QAOA) — over ${BENCHMARK_N_SCENARIOS} seeded scenarios.`,
    keywords: ["ablation", "safety layer", "ppo", "hqrl", "ieee", "no safety"],
    provenance: "native",
    expectedRisk: "CRITICAL",
    dam: { preset: "extreme_rainfall", controls: damControls({ rainfall_mm: 220, rainfall_intensity_mm_hr: 45, inflow_cumec: 3200, outflow_cumec: 1200 }) },
    sim: {
      scenario: "heavy_rainfall",
      params: simParams({ rainfall_intensity: 72, dam_level: 199.2, river_level: 204.6, road_blockage: 0.22, population: 14000, shelter_capacity_factor: 1.0, traffic: 0.55, sos_count: 10 }),
    },
    hqrl: { mode: "ablation", n_scenarios: BENCHMARK_N_SCENARIOS },
  },
];

export const DEFAULT_SCENARIO_ID = "normal_operation";

/** Seed shared by every benchmark run so the table is reproducible. */
export const BENCHMARK_SEED = 42;

export function getScenario(id) {
  return SCENARIOS.find((s) => s.id === id) || null;
}

export function scenariosByGroup(groupId) {
  return SCENARIOS.filter((s) => s.group === groupId);
}

export function groupLabel(groupId) {
  return SCENARIO_GROUPS.find((g) => g.id === groupId)?.label || groupId;
}

/** Substring match over label, description and keywords — powers the combobox. */
export function searchScenarios(query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return SCENARIOS;
  return SCENARIOS.filter((s) => {
    const hay = [s.label, s.description, groupLabel(s.group), ...(s.keywords || [])].join(" ").toLowerCase();
    return hay.includes(q);
  });
}

/** Every input a scenario asserts, flattened for editing and change-detection. */
export function scenarioInputs(scenario) {
  if (!scenario) return {};
  return { ...(scenario.dam?.controls || {}), ...(scenario.sim?.params || {}) };
}

/** Field-level diff so the UI can name exactly which inputs the user changed. */
export function divergedFields(scenario, current = {}) {
  const base = scenarioInputs(scenario);
  return Object.keys(base).filter((k) => {
    const a = base[k];
    const b = current[k];
    if (b === undefined || b === null || b === "") return false;
    return Number(a) !== Number(b);
  });
}

/** Split flat inputs back into the two request bodies the backends expect. */
export function splitInputs(scenario, inputs = {}) {
  const damKeys = Object.keys(scenario?.dam?.controls || {});
  const simKeys = Object.keys(scenario?.sim?.params || {});
  const dam = {};
  const sim = {};
  for (const k of damKeys) dam[k] = inputs[k];
  for (const k of simKeys) sim[k] = inputs[k];
  return { dam, sim };
}

/** HQRL planner config derived from the evacuation inputs.
 *
 * Mirrors the mapping IeeeHqrlEmbed already used, kept here so the benchmark,
 * the planner and the on-screen inputs cannot drift apart. Ranges match
 * HqrlConfigBody (backend/api/hqrl.py:17). */
export function deriveHqrlConfig(simInputs = {}, citizenCount = 0) {
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const blockage = Number(simInputs.road_blockage) || 0;
  return {
    seed: BENCHMARK_SEED,
    n_groups: clamp(Math.round((citizenCount || Number(simInputs.sos_count) || 6) / 2), 3, 12),
    n_shelters: 3,
    shelter_capacity_scale: clamp(Number(simInputs.shelter_capacity_factor) || 1, 0.3, 2),
    flood_severity: clamp((Number(simInputs.rainfall_intensity) || 0) / 120, 0, 1),
    traffic_level: clamp(Number(simInputs.traffic) || 0, 0, 1),
    n_road_closures: blockage >= 0.45 ? 2 : blockage >= 0.25 ? 1 : 0,
    vehicles_available: 8,
  };
}

/* ---------------------------------------------------------------------------
 * Deliberately NOT in this catalogue:
 *
 * - "Structural Stress / Seepage". The repo has no seepage, structural-stress
 *   or dam-integrity model — the risk engine uses fill %, the ML severity head
 *   and level trend only. Shipping it would mean inventing numbers.
 *
 * - Named HQRL scenarios. There is no HQRL preset table anywhere in the repo;
 *   a "benchmark scenario" is only a seed offset (base_seed + i*17,
 *   backend/simulation/hqrl_demo.py:1222). The two hqrl-group entries above
 *   select a real endpoint mode, not an invented scenario.
 *
 * - Named people/resident rosters. There is one roster (DEFAULT_CITIZENS,
 *   backend/services/citizens.py:3); a scenario sizes it through sos_count.
 *   See frontend/src/data/citizens.js.
 *
 * - A per-scenario dam. The evacuation engine simulates exactly ONE region
 *   (Delhi Yamuna floodplain, backend/services/seed.py ZONES), so every
 *   scenario shares it. The reservoir paired with it is chosen by the backend
 *   (GET /api/dams -> `region_dam`: nearest registry dam to that region by real
 *   haversine distance) and re-applied on every scenario select. It is never
 *   a hard-coded dam here, and never the first row of the registry.
 *   The dam stays user-editable, and its reservoir level (m MSL) is never
 *   copied into sim.dam_level (Yamuna barrage stage) or vice versa.
 * ------------------------------------------------------------------------- */
