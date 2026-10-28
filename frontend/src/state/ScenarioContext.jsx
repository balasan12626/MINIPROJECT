import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchCities,
  fetchDams,
  fetchMlBenchmarkV4,
  hqrlAblation,
  hqrlBenchmark,
  hqrlConfigure,
  runDamSimulation,
  startSimulation,
} from "../services/api.js";
import {
  BENCHMARK_N_SCENARIOS,
  BENCHMARK_SEED,
  DEFAULT_SCENARIO_ID,
  deriveHqrlConfig,
  divergedFields,
  getScenario,
  scenarioInputs,
  splitInputs,
} from "../config/scenarios.js";
import { resizeRoster, roster } from "../data/citizens.js";
import { DEFAULT_FEATURES } from "../components/FeatureToggles.jsx";

const ScenarioCtx = createContext(null);

/** The four backends one RUN SCENARIO click drives, in order. */
export const RUN_STEPS = [
  { id: "dam", label: "Dam simulation", endpoint: "POST /api/simulation/run" },
  { id: "evacuation", label: "Evacuation", endpoint: "POST /api/simulation/start" },
  { id: "benchmark", label: "HQRL benchmark", endpoint: "POST /api/simulation/hqrl/benchmark" },
  { id: "ml", label: "ML model benchmark", endpoint: "GET /api/ml/benchmark-v4" },
];

const IDLE_STEPS = {
  dam: { status: "idle" }, evacuation: { status: "idle" }, benchmark: { status: "idle" }, ml: { status: "idle" },
};
const EMPTY_RESULTS = { dam: null, run: null, benchmark: null, ml: null };

function errText(err) {
  return err?.response?.data?.detail || err?.message || "Request failed";
}

/** Single source of truth for /simulation.
 *
 * Holds the scenario selection, every editable input, and the one run flow.
 * Nothing here fetches or runs on mount except the dam registry, which is
 * read-only reference data for the dam selector.
 *
 * Results are stored PER RUN (`runs[runId]`). Every rendered result value —
 * header label, KPIs, dam block, benchmark, evacuation — reads the record of
 * `currentRunId`, which also carries the scenario id/label and the input
 * signature it ran with. A header can therefore never name one scenario while
 * the numbers come from another.
 */
export function ScenarioProvider({ children }) {
  // ---- selection + inputs ------------------------------------------------
  const [activeId, setActiveId] = useState(DEFAULT_SCENARIO_ID);
  // Bumped on every explicit select/reset so downstream effects can re-apply
  // a preset even when the same scenario is chosen again.
  const [revision, setRevision] = useState(0);
  const [overrides, setOverrides] = useState({});
  const [features, setFeatures] = useState({ ...DEFAULT_FEATURES });

  const scenario = useMemo(() => getScenario(activeId), [activeId]);
  const presetInputs = useMemo(() => scenarioInputs(scenario), [scenario]);
  const inputs = useMemo(() => ({ ...presetInputs, ...overrides }), [presetInputs, overrides]);

  // ---- dam registry (the only mount-time fetch: reference data) -----------
  const [dams, setDams] = useState([]);
  const [damsError, setDamsError] = useState("");
  const [damId, setDamIdRaw] = useState("");
  // The evacuation region the engine simulates, and the registry dam the
  // backend pairs with it (GET /api/dams -> evacuation_region / region_dam).
  const [evacuationRegion, setEvacuationRegion] = useState(null);
  const [regionDam, setRegionDam] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchDams()
      .then((res) => {
        if (!alive) return;
        const list = res?.dams || [];
        setDams(list);
        setEvacuationRegion(res?.evacuation_region || null);
        setRegionDam(res?.region_dam || null);
        setDamsError(list.length ? "" : res?.message || "No dams returned");
        // Default to the region's dam — never simply the first registry row
        // (that paired Mettur, Tamil Nadu with a Delhi/Yamuna flood).
        const preferred = res?.region_dam?.dam_id;
        setDamIdRaw((prev) => prev || (list.some((d) => d.id === preferred) ? preferred : list[0]?.id) || "");
      })
      .catch((err) => alive && setDamsError(errText(err)));
    return () => {
      alive = false;
    };
  }, []);

  // ---- cities (F7: reference data, read once) -----------------------------
  // The run plans on one city's real road network (backend/data/cities).
  const [cities, setCities] = useState([]);
  const [cityId, setCityId] = useState("delhi");
  useEffect(() => {
    let alive = true;
    Promise.resolve()
      .then(() => fetchCities())
      .then((res) => {
        if (!alive) return;
        const list = res?.cities || [];
        setCities(list);
        // Keep "delhi" when it exists, else whatever the backend has first.
        setCityId((prev) => (list.some((c) => c.id === prev) ? prev : list[0]?.id || prev));
      })
      .catch(() => alive && setCities([]));
    return () => {
      alive = false;
    };
  }, []);
  const city = useMemo(() => cities.find((c) => c.id === cityId) || null, [cities, cityId]);
  // F8 / F9: which free ambulance serves an SOS, and whether idle ones pre-position.
  const [dispatchPolicy, setDispatchPolicy] = useState("optimal");
  const [preposition, setPreposition] = useState(true);
  // F18: "forecast" = Open-Meteo hourly rain for the city drives the run (labelled forecast).
  const [rainSource, setRainSource] = useState("scenario");
  // F23: ASSUMED share of a warned zone that leaves early (0 = off; used by the what-if planner).
  const [warningCompliance, setWarningCompliance] = useState(0);
  // F25: assumed crew shift / fuel rules (off = today's unlimited crews).
  const [crewRules, setCrewRules] = useState(false);
  // F32: fairness knob of the "fair" dispatch policy.
  const [fairLambda, setFairLambda] = useState(1);
  // F28: food / water supply runs with an assumed truck fleet (off by default).
  const [supplyOn, setSupplyOn] = useState(false);
  // F22: assumed boat fleet for cut-off people (0 = off by default).
  const [boatsCount, setBoatsCount] = useState(0);
  // F26: road flood exposure model ("distance" = proxy v1, "hand" = height above nearest drainage v2).
  const [exposureModel, setExposureModel] = useState("distance");

  const selectedDam = useMemo(() => dams.find((d) => d.id === damId) || null, [dams, damId]);

  /** Changing the reservoir drops a typed reservoir level: that number was an
   * elevation (m MSL) for the previous dam and means nothing for another one. */
  // Once the operator picks a dam, loading a scenario must not swap it back.
  const userPickedDam = useRef(false);
  const setDamId = useCallback((id) => {
    userPickedDam.current = true;
    setDamIdRaw(id);
    setOverrides((prev) => {
      if (prev.current_level_m == null && prev.capacity_override_m == null) return prev;
      const next = { ...prev };
      delete next.current_level_m;
      delete next.capacity_override_m;
      return next;
    });
  }, []);

  // Reservoir level (m MSL) defaults to the selected dam's own reading until
  // edited. This is NOT the evacuation-side `dam_level` (Yamuna barrage stage,
  // from scenario.sim.params) — the two are never copied into each other.
  const damLevel = overrides.current_level_m ?? selectedDam?.current_level_m ?? null;
  // Edited full reservoir level (m MSL) — the backend's `capacity_override_m`.
  // Unset means the registry's own FRL is used.
  const damFrlOverride = typeof overrides.capacity_override_m === "number" ? overrides.capacity_override_m : null;

  // ---- people roster -----------------------------------------------------
  const [citizens, setCitizens] = useState(() => roster(10));
  // A scenario's sos_count sizes the roster; manual row edits survive resizes.
  const sosCount = Number(inputs.sos_count) || 0;
  useEffect(() => {
    setCitizens((prev) => resizeRoster(prev, sosCount));
  }, [sosCount]);

  // ---- run state ---------------------------------------------------------
  // runs[runId] = { runId, scenarioId, label, signature, startedAt, finishedAt,
  //                 steps, dam, run, benchmark, ml }
  const [runs, setRuns] = useState({});
  const [currentRunId, setCurrentRunId] = useState(null);
  const [running, setRunning] = useState(false);
  const runSeq = useRef(0);

  const currentRun = currentRunId ? runs[currentRunId] || null : null;
  const steps = currentRun?.steps || IDLE_STEPS;
  const results = useMemo(
    () =>
      currentRun
        ? { dam: currentRun.dam, run: currentRun.run, benchmark: currentRun.benchmark, ml: currentRun.ml }
        : EMPTY_RESULTS,
    [currentRun]
  );

  // ---- derived -----------------------------------------------------------
  const changedFields = useMemo(() => {
    const diverged = divergedFields(scenario, inputs).filter((k) => k !== "capacity_override_m");
    if (overrides.current_level_m != null && overrides.current_level_m !== selectedDam?.current_level_m) {
      diverged.push("current_level_m");
    }
    if (damFrlOverride != null && damFrlOverride !== selectedDam?.full_reservoir_level_m) {
      diverged.push("capacity_override_m");
    }
    return diverged;
  }, [scenario, inputs, overrides.current_level_m, selectedDam?.current_level_m, selectedDam?.full_reservoir_level_m, damFrlOverride]);

  const isCustom = changedFields.length > 0;

  /** Everything a run consumes — used to detect "results are stale". */
  const signature = useMemo(
    () => JSON.stringify({ inputs, damId, damLevel, citizens, features, cityId, dispatchPolicy, preposition, rainSource, warningCompliance, crewRules, fairLambda, supplyOn, boatsCount, exposureModel }),
    [inputs, damId, damLevel, citizens, features, cityId, dispatchPolicy, preposition, rainSource, warningCompliance, crewRules, fairLambda, supplyOn, boatsCount, exposureModel]
  );

  const hasResults = Boolean(results.dam || results.run || results.benchmark || results.ml);
  const isOutdated = Boolean(
    currentRun && hasResults && (currentRun.scenarioId !== activeId || currentRun.signature !== signature)
  );

  /** Kept for existing readers: the finished run's identity. */
  const lastRun = useMemo(
    () =>
      currentRun?.finishedAt
        ? {
            runId: currentRun.runId,
            scenarioId: currentRun.scenarioId,
            signature: currentRun.signature,
            label: currentRun.label,
            at: currentRun.finishedAt,
          }
        : null,
    [currentRun]
  );

  // ---- actions -----------------------------------------------------------
  const selectScenario = useCallback(
    (id) => {
      if (!getScenario(id)) return;
      setActiveId(id);
      // Scenario presets reset every scenario input, but the reservoir level
      // and capacity belong to the chosen DAM, not the scenario — keep them.
      setOverrides((prev) => {
        const keep = {};
        if (prev.current_level_m != null) keep.current_level_m = prev.current_level_m;
        if (prev.capacity_override_m != null) keep.capacity_override_m = prev.capacity_override_m;
        return keep;
      });
      // Until the operator picks a dam, the reservoir follows the scenario's
      // evacuation region. A dam the operator clicked is kept.
      if (!userPickedDam.current && regionDam?.dam_id) setDamIdRaw(regionDam.dam_id);
      setRevision((r) => r + 1);
    },
    [regionDam]
  );

  const resetToScenario = useCallback(() => {
    setOverrides({});
    setRevision((r) => r + 1);
  }, []);

  const patchInputs = useCallback((patch) => {
    if (!patch) return;
    setOverrides((prev) => ({ ...prev, ...patch }));
  }, []);

  const clearResults = useCallback(() => {
    runSeq.current += 1; // orphan any in-flight run
    setRuns({});
    setCurrentRunId(null);
    setRunning(false);
  }, []);

  /** THE run handler. Four independent backends, one click.
   *
   * Each step has its own try/catch so a failure never wipes the other steps'
   * results, and every write is guarded by a monotonic sequence so a
   * superseded run can never land on top of a newer one. A single-step retry
   * reuses the current run record only while it still matches the inputs;
   * otherwise it becomes a full new run, so one record never mixes two input
   * sets. */
  const runScenario = useCallback(
    async (opts = {}) => {
      if (running) return;
      if (!scenario) return;

      const sameInputs = Boolean(currentRun && currentRun.scenarioId === activeId && currentRun.signature === signature);
      const only = opts.only && sameInputs ? opts.only : null;
      const wants = (id) => !only || only === id;

      const mySeq = runSeq.current + 1;
      runSeq.current = mySeq;
      const stale = () => runSeq.current !== mySeq;
      const runId = only ? currentRun.runId : `run-${mySeq}`;

      const patchRun = (fn) => setRuns((prev) => (prev[runId] ? { ...prev, [runId]: fn(prev[runId]) } : prev));
      const markStep = (id, patch) =>
        patchRun((r) => ({ ...r, steps: { ...r.steps, [id]: { ...r.steps[id], ...patch } } }));

      const { dam: damControls, sim: simParams } = splitInputs(scenario, inputs);

      setRunning(true);
      if (only) {
        markStep(only, { status: "running", error: undefined });
      } else {
        // A fresh record: nothing from an earlier run can leak into it.
        setRuns({
          [runId]: {
            runId,
            scenarioId: activeId,
            label: scenario.label,
            signature,
            startedAt: new Date().toISOString(),
            finishedAt: null,
            steps: {
              dam: { status: "running" },
              evacuation: { status: "running" },
              benchmark: { status: "running" },
              ml: { status: "running" },
            },
            ...EMPTY_RESULTS,
          },
        });
        setCurrentRunId(runId);
      }

      // The full-screen run theater belongs to the old flow; this page shows
      // its own per-box loading state instead.
      try {
        window.sessionStorage?.removeItem("flood_run_theater");
      } catch {
        /* private mode — non-fatal */
      }

      // ---- 1. dam water balance -------------------------------------------
      // NOTE: `scenario` is deliberately NOT sent. backend/api/dams.py
      // overwrites every typed input with the preset's defaults when it is,
      // which would make the input boxes above decorative.
      if (wants("dam")) {
        try {
          if (!damId) throw new Error("No dam selected");
          const dam = await runDamSimulation({
            dam_id: damId,
            ...damControls,
            ...(damLevel != null ? { current_level_m: Number(damLevel) } : {}),
            ...(damFrlOverride != null && damFrlOverride > 0 ? { capacity_override_m: damFrlOverride } : {}),
          });
          if (stale()) return;
          if (dam?.available === false) throw new Error(dam.message || "Dam simulation unavailable");
          patchRun((r) => ({ ...r, dam }));
          markStep("dam", { status: "success" });
        } catch (err) {
          if (stale()) return;
          markStep("dam", { status: "error", error: errText(err) });
        }
      }

      // ---- 2. evacuation engine -------------------------------------------
      if (wants("evacuation")) {
        try {
          const state = await startSimulation({
            scenario: scenario.sim.scenario,
            ...simParams,
            sos_count: citizens.length,
            citizens,
            features,
            ...(cities.length ? { city: cityId } : {}),
            dispatch_policy: dispatchPolicy,
            preposition,
            rain_source: rainSource,
            warning_compliance: warningCompliance,
            crew_rules: crewRules ? { on: true } : null,
            fair_lambda: fairLambda,
            supply: supplyOn ? { on: true } : null,
            boats: Number(boatsCount) || 0,
            exposure_model: exposureModel,
          });
          if (stale()) return;
          const engineRunId = state?.run_id;
          if (!engineRunId) throw new Error(state?.message || "Engine did not return a run id");
          patchRun((r) => ({
            ...r,
            run: {
              runId: engineRunId,
              scenario: scenario.sim.scenario,
              title: scenario.label,
              features,
              city: city ? { id: city.id, name: city.name } : null,
              region: evacuationRegion,
              dam: selectedDam
                ? {
                    id: selectedDam.id,
                    name: selectedDam.name,
                    lat: selectedDam.lat,
                    lon: selectedDam.lon,
                    state: selectedDam.state,
                    river: selectedDam.river,
                  }
                : null,
            },
          }));
          markStep("evacuation", { status: "success" });
        } catch (err) {
          if (stale()) return;
          markStep("evacuation", { status: "error", error: errText(err) });
        }
      }

      // ---- 3. HQRL benchmark ----------------------------------------------
      if (wants("benchmark")) {
        try {
          const mode = scenario.hqrl?.mode || "benchmark";
          const nScenarios = scenario.hqrl?.n_scenarios || BENCHMARK_N_SCENARIOS;
          // Configure first so the benchmark reflects THIS scenario's
          // severity/traffic/closures rather than the server's last config.
          await hqrlConfigure(deriveHqrlConfig(simParams, citizens.length));
          if (stale()) return;
          const body = { n_scenarios: nScenarios, seed: BENCHMARK_SEED };
          const out = mode === "ablation" ? await hqrlAblation(body) : await hqrlBenchmark(body);
          if (stale()) return;
          const payload = mode === "ablation" ? out?.ablation : out?.benchmark;
          if (!payload) throw new Error(out?.message || "Benchmark returned no table");
          patchRun((r) => ({ ...r, benchmark: { mode, ...payload } }));
          markStep("benchmark", { status: "success" });
        } catch (err) {
          if (stale()) return;
          markStep("benchmark", { status: "error", error: errText(err) });
        }
      }

      // ---- 4. ML model benchmark ------------------------------------------
      // The backend re-scores the saved v4 model on its untouched unseen-gauge
      // test set on every call, so these numbers are computed for this run.
      if (wants("ml")) {
        try {
          const ml = await fetchMlBenchmarkV4();
          if (stale()) return;
          if (ml?.available === false) throw new Error(ml.message || "ML benchmark unavailable");
          patchRun((r) => ({ ...r, ml }));
          markStep("ml", { status: "success" });
        } catch (err) {
          if (stale()) return;
          markStep("ml", { status: "error", error: errText(err) });
        }
      }

      if (stale()) return;
      patchRun((r) => ({ ...r, finishedAt: new Date().toISOString() }));
      setRunning(false);
    },
    [running, scenario, currentRun, activeId, signature, inputs, damId, damLevel, damFrlOverride, citizens, features, selectedDam, evacuationRegion, cities, cityId, city, dispatchPolicy, preposition, rainSource, warningCompliance, crewRules, fairLambda, supplyOn]
  );

  const value = useMemo(
    () => ({
      // selection
      activeId,
      scenario,
      revision,
      selectScenario,
      resetToScenario,
      // inputs
      inputs,
      presetInputs,
      patchInputs,
      changedFields,
      isCustom,
      features,
      setFeatures,
      citizens,
      setCitizens,
      // dams + evacuation region
      dams,
      damId,
      setDamId,
      selectedDam,
      damLevel,
      damFrlOverride,
      damsError,
      evacuationRegion,
      regionDam,
      // city (F7)
      cities,
      cityId,
      setCityId,
      city,
      dispatchPolicy,
      setDispatchPolicy,
      preposition,
      setPreposition,
      rainSource,
      setRainSource,
      warningCompliance,
      setWarningCompliance,
      crewRules,
      setCrewRules,
      fairLambda,
      setFairLambda,
      supplyOn,
      setSupplyOn,
      boatsCount,
      setBoatsCount,
      exposureModel,
      setExposureModel,
      // run (all result readers go through currentRun)
      steps,
      results,
      runs,
      currentRunId,
      currentRun,
      running,
      hasResults,
      isOutdated,
      lastRun,
      runScenario,
      clearResults,
    }),
    [
      activeId, scenario, revision, selectScenario, resetToScenario,
      inputs, presetInputs, patchInputs, changedFields, isCustom,
      features, citizens, dams, damId, setDamId, selectedDam, damLevel, damFrlOverride, damsError, evacuationRegion, regionDam,
      cities, cityId, city, dispatchPolicy, preposition, rainSource, warningCompliance, crewRules, fairLambda, supplyOn, boatsCount, exposureModel,
      steps, results, runs, currentRunId, currentRun, running, hasResults, isOutdated, lastRun, runScenario, clearResults,
    ]
  );

  return <ScenarioCtx.Provider value={value}>{children}</ScenarioCtx.Provider>;
}

/** Returns null outside a provider so components stay usable standalone. */
export function useScenario() {
  return useContext(ScenarioCtx);
}
