import { memo, useCallback, useEffect, useRef, useState } from "react";
import { fetchMlBenchmarkV2 } from "../services/api.js";

function fmt(v, digits = 2) {
  return v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(digits);
}

/** Reads the already-computed V3 holdout evaluation artifact — never retrains
 * or recomputes. It is a single GET, so it loads by itself once the panel is
 * mounted (the page lazy-mounts it when scrolled near) instead of offering a
 * second "run" button next to RUN SCENARIO. */
function ModelBenchmarkPanel() {
  const [state, setState] = useState("idle"); // idle | loading | success | error
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const alive = useRef(true);
  const run = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const res = await fetchMlBenchmarkV2();
      if (!alive.current) return;
      if (!res?.available) {
        setState("error");
        setError(res?.message || "Evaluation artifact unavailable.");
        return;
      }
      setData(res);
      setState("success");
    } catch (err) {
      if (!alive.current) return;
      setState("error");
      setError(err?.message || "Evaluation request failed.");
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    run();
    return () => {
      alive.current = false;
    };
  }, [run]);

  const reg = data?.regression_holdout;
  const clf = data?.classifier_holdout;

  return (
    <div className="panel">
      <h2>MODEL BENCHMARK — HELD-OUT EVALUATION</h2>
      <p className="hint">
        Real, pre-computed metrics on the untouched 31-gauge holdout set. Not test-set-tuned, not retrained on demand.
      </p>
      {state === "loading" ? (
        <div className="kpi-loading" style={{ marginBottom: 10 }}>
          <span className="run-spinner" aria-hidden /> Loading held-out evaluation…
        </div>
      ) : null}

      {state === "error" ? (
        <div className="unavailable" role="alert">
          Evaluation unavailable
          <div className="hint" style={{ marginTop: 4 }}>Reason: {error}</div>
          <button type="button" className="primary" style={{ marginTop: 8 }} onClick={run}>Retry</button>
        </div>
      ) : null}

      {state === "success" && reg ? (
        <>
          <p className="hint" style={{ marginTop: 8 }}>
            Model: <b>{data.stage1_model}</b> → <b>{data.stage2_model}</b> · Version <b>{data.version}</b> · Source: {data.source}
          </p>
          <h3 style={{ marginTop: 10 }}>Stage 1 — Peak flood level regressor</h3>
          <div className="grid-4">
            <div className="metric"><span>MAE</span><b>{fmt(reg.mae)}</b></div>
            <div className="metric"><span>RMSE</span><b>{fmt(reg.rmse)}</b></div>
            <div className="metric"><span>R²</span><b>{fmt(reg.r2, 3)}</b></div>
            <div className="metric"><span>Median AE</span><b>{fmt(reg.medae)}</b></div>
          </div>
          <p className="hint" style={{ marginTop: 6 }}>
            Mean bias {fmt(reg.mean_bias)} — the model under-predicts on the extreme high tail
            (top-1 MAE {fmt(reg.top1_mae)}, top-5 MAE {fmt(reg.top5_mae)}). Shown as-is, not corrected or clipped.
          </p>
          {clf ? (
            <>
              <h3 style={{ marginTop: 10 }}>Stage 2 — Severe-flood classifier</h3>
              <div className="grid-4">
                <div className="metric"><span>Precision</span><b>{fmt(clf.precision, 3)}</b></div>
                <div className="metric"><span>Recall</span><b>{fmt(clf.recall, 3)}</b></div>
                <div className="metric"><span>F1</span><b>{fmt(clf.f1, 3)}</b></div>
                <div className="metric"><span>ROC-AUC</span><b>{fmt(clf.roc_auc, 3)}</b></div>
              </div>
            </>
          ) : null}
        </>
      ) : null}

    </div>
  );
}

export default memo(ModelBenchmarkPanel);
