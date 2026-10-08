import { useMemo, useState } from "react";
import KpiCard from "../KpiCard.jsx";
import V4ReplayPanel from "./V4ReplayPanel.jsx";
import { formatTimeIST } from "../../utils/time.js";

/** ML model benchmark for one RUN SCENARIO click.
 *
 * Every number comes from GET /api/ml/benchmark-v4, which re-scores the saved
 * v4 model on its untouched unseen-gauge test set during this run. The 20-model
 * table is the training-time comparison the same endpoint returns. Nothing is
 * hard-coded here. */

const pct = (v, d = 1) => (typeof v === "number" && Number.isFinite(v) ? `${(v * 100).toFixed(d)}%` : "—");
const pts = (v) => (typeof v === "number" && Number.isFinite(v) ? `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)} pts` : "—");
const int = (v) => (typeof v === "number" ? v.toLocaleString("en-IN") : "—");

const TEST_LABELS = {
  "T1_acc>=85": "Accuracy ≥ 85%",
  "T2_bal>=85": "Balanced acc ≥ 85%",
  T3_not_overfit: "Not overfit (gap ≤ 5 pts)",
  T4_not_underfit: "Not underfit (train ≥ 80%)",
  T5_beats_baseline: "Beats simple baseline",
  T6_stable_unseen: "Stable on unseen gauges",
};

const VERDICT_TONE = { BALANCED: "live", OVERFIT: "warn", UNDERFIT: "crit" };

function Verdict({ value }) {
  if (!value) return <span className="muted">—</span>;
  return <span className={`badge ${VERDICT_TONE[value] || ""}`}>{value}</span>;
}

function FitBars({ fit }) {
  const rows = [
    ["Train", fit?.train_balanced_accuracy],
    ["Validation (2009–2014)", fit?.validation_balanced_accuracy],
    ["Test — unseen gauges (2015–2020)", fit?.test_balanced_accuracy],
  ];
  return (
    <div className="ml-fit-bars">
      {rows.map(([label, v]) => (
        <div className="metric" key={label}>
          <span>{label}</span>
          <span className="ml-bar" aria-hidden="true">
            <span style={{ width: typeof v === "number" ? `${Math.max(0, Math.min(1, v)) * 100}%` : 0 }} />
          </span>
          <b>{pct(v)}</b>
        </div>
      ))}
    </div>
  );
}

function ZooTable({ zoo }) {
  const [which, setWhich] = useState("new");
  const block = zoo?.[which];
  const rows = useMemo(
    () => [...(block?.rows || [])].sort((a, b) => (b.test_bal ?? -1) - (a.test_bal ?? -1)),
    [block]
  );
  if (!zoo) return <p className="muted">20-model comparison not generated yet (scripts/benchmark_20_models.py).</p>;
  const info = block?.info;
  const testKeys = Object.keys(TEST_LABELS);

  return (
    <>
      <div className="status-row" role="tablist">
        {[
          ["new", "New data — CAMELS-IND (3-day forecast)"],
          ["old", "Old data — INDOFLOODS (severe-flood event)"],
        ].map(([id, label]) =>
          zoo[id] ? (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={which === id}
              className={`radio-pill ${which === id ? "active" : ""}`}
              onClick={() => setWhich(id)}
            >
              {label}
            </button>
          ) : null
        )}
      </div>
      {info ? (
        <p className="hint">
          Test = {int(info.test)} rows from {int(info.test_gauges)} gauges never seen in training · flood rate{" "}
          {pct(info.test_positive_rate)} · baseline ({info.baseline}): accuracy {pct(info.baseline_test_acc)}, balanced{" "}
          {pct(info.baseline_test_bal)}
        </p>
      ) : null}
      <div className="table-wrap">
        <table className="data-table ml-zoo">
          <thead>
            <tr>
              <th>#</th>
              <th>Model</th>
              <th>Train bal.</th>
              <th>Test bal.</th>
              <th>Test acc.</th>
              <th>Gap</th>
              <th>Fit</th>
              {testKeys.map((k) => (
                <th key={k} title={TEST_LABELS[k]}>
                  {k.slice(0, 2)}
                </th>
              ))}
              <th>Passed</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) =>
              r.error ? (
                <tr key={r.model}>
                  <td>{i + 1}</td>
                  <td>{r.model.replace(/^\d+\s/, "")}</td>
                  <td colSpan={6 + testKeys.length} className="muted">
                    failed: {r.error}
                  </td>
                </tr>
              ) : (
                <tr key={r.model}>
                  <td>{i + 1}</td>
                  <td title={r.note || undefined}>
                    {r.model.replace(/^\d+\s/, "")}
                    {r.note ? " *" : ""}
                  </td>
                  <td>{pct(r.train_bal)}</td>
                  <td>
                    <b>{pct(r.test_bal)}</b>
                  </td>
                  <td>{pct(r.test_acc)}</td>
                  <td>{pts(r.gap)}</td>
                  <td>
                    <Verdict value={r.verdict} />
                  </td>
                  {testKeys.map((k) => (
                    <td key={k} aria-label={`${TEST_LABELS[k]}: ${r.tests?.[k] ? "pass" : "fail"}`}>
                      {r.tests?.[k] ? "✓" : "✗"}
                    </td>
                  ))}
                  <td>
                    <b>{r.passed}/6</b>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      </div>
      <p className="hint">
        T1–T6: {testKeys.map((k) => `${k.slice(0, 2)} ${TEST_LABELS[k]}`).join(" · ")}. Each model&apos;s decision
        threshold is chosen on validation; test is scored once. * = trained on a smaller sample (see tooltip).
      </p>
    </>
  );
}

export default function MlBenchmarkPanel({ ml }) {
  if (!ml) return null;
  const t = ml.live_test || {};
  const base = ml.baseline_persistence || {};
  const fit = ml.fit_check || {};
  const floods = (t.tp ?? 0) + (t.fn ?? 0);
  const alarms = (t.tp ?? 0) + (t.fp ?? 0);

  return (
    <div className="panel ml-benchmark" id="ml-benchmark">
      <div className="panel-head">
        <h3>ML flood-forecast benchmark</h3>
        <span className="badge live">re-scored live · {formatTimeIST(ml.computed_at)}</span>
      </div>
      <p className="hint">
        {ml.task} · {ml.dataset} · model <b>{ml.selected_model}</b> · tested on {int(ml.test_set?.rows)} days from{" "}
        {int(ml.test_set?.gauges)} river gauges the model never saw ({ml.test_set?.years}).
      </p>

      <div className="grid-4">
        <KpiCard label="Balanced accuracy (unseen rivers)" value={pct(t.balanced_accuracy)} sub={`persistence baseline ${pct(base.balanced_accuracy)}`} />
        <KpiCard label="Plain accuracy" value={pct(t.accuracy)} sub={`'always no flood' would score ${pct(ml.baseline_always_no_flood_accuracy)}`} />
        <KpiCard label="Floods caught (recall)" value={pct(t.recall)} sub={`${int(t.tp)} of ${int(floods)} flood days`} />
        <KpiCard label="Alarm precision" value={pct(t.precision)} sub={`${int(t.tp)} of ${int(alarms)} alarms were real`} />
        <KpiCard label="ROC-AUC" value={typeof t.roc_auc === "number" ? t.roc_auc.toFixed(3) : "—"} sub="1.0 = perfect ranking" />
        <KpiCard label="Fit check" value={fit.verdict || "—"} sub={`train − test ${pts((fit.train_balanced_accuracy ?? NaN) - (fit.test_balanced_accuracy ?? NaN))}`} />
        <KpiCard label="Beats persistence by" value={pts((t.balanced_accuracy ?? NaN) - (base.balanced_accuracy ?? NaN))} sub="balanced accuracy" />
        <KpiCard label="Inference time" value={`${ml.inference?.total_ms ?? "—"} ms`} sub={`${int(ml.inference?.rows)} rows · ${ml.inference?.per_1000_rows_ms ?? "—"} ms / 1000`} />
      </div>

      <p className="ml-plain">
        In plain words: across {int(t.n)} test days, {int(floods)} had a flood coming within 3 days. The model warned in
        time on <b>{int(t.tp)}</b> of them and missed <b>{int(t.fn)}</b>. It also raised <b>{int(t.fp)}</b> false alarms
        on {int(t.tn + t.fp)} quiet days.
      </p>

      <div className="grid-2">
        <div className="panel">
          <h3>Overfitting check</h3>
          <FitBars fit={fit} />
          <p className="hint">Balanced = train within 5 pts of test and train ≥ 80%.</p>
        </div>
        <div className="panel">
          <h3>Candidates compared on validation</h3>
          {Object.entries(ml.candidates || {}).map(([name, c]) => (
            <div className="metric" key={name}>
              <span>
                {name}
                {name === ml.selected_model ? " ✓ selected" : ""}
              </span>
              <b>
                {pct(c.val_bal)} <span className="muted">(train {pct(c.train_bal)})</span>
              </b>
            </div>
          ))}
        </div>
      </div>

      <V4ReplayPanel />

      <h3>20 model families — pass / fail</h3>
      <ZooTable zoo={ml.zoo} />
    </div>
  );
}
