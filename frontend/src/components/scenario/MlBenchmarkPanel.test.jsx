import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MlBenchmarkPanel from "./MlBenchmarkPanel.jsx";

const payload = {
  available: true,
  computed_at: "2026-09-29T15:00:00Z",
  task: "flood within 3 days",
  dataset: "CAMELS-IND",
  selected_model: "xgboost_d6",
  test_set: { rows: 1000, gauges: 40, years: "2015-2020" },
  live_test: { accuracy: 0.9, balanced_accuracy: 0.876, recall: 0.8, precision: 0.5, roc_auc: 0.95, tp: 80, fn: 20, fp: 80, tn: 820, n: 1000 },
  baseline_persistence: { balanced_accuracy: 0.8 },
  baseline_always_no_flood_accuracy: 0.9,
  inference: { rows: 1000, total_ms: 12.5, per_1000_rows_ms: 12.5 },
  fit_check: { train_balanced_accuracy: 0.9, validation_balanced_accuracy: 0.88, test_balanced_accuracy: 0.876, verdict: "BALANCED" },
  candidates: { xgboost_d6: { train_bal: 0.9, val_bal: 0.88 } },
  zoo: {
    new: {
      info: { test: 1000, test_gauges: 40, test_positive_rate: 0.1, baseline: "persistence", baseline_test_acc: 0.9, baseline_test_bal: 0.8 },
      rows: [
        { model: "16 XGBoost", train_bal: 0.9, val_bal: 0.88, test_acc: 0.9, test_bal: 0.87, gap: 0.03, verdict: "BALANCED", passed: 6,
          tests: { "T1_acc>=85": true, "T2_bal>=85": true, T3_not_overfit: true, T4_not_underfit: true, T5_beats_baseline: true, T6_stable_unseen: true } },
      ],
    },
  },
};

describe("MlBenchmarkPanel", () => {
  it("renders nothing without a result", () => {
    const { container } = render(<MlBenchmarkPanel ml={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the live re-scored numbers from the API payload", () => {
    render(<MlBenchmarkPanel ml={payload} />);
    expect(screen.getAllByText("87.6%").length).toBeGreaterThan(0);
    expect(screen.getByText("80 of 100 flood days")).toBeTruthy();
    expect(screen.getByText("+7.6 pts")).toBeTruthy();
    expect(screen.getByText("6/6")).toBeTruthy();
  });
});
