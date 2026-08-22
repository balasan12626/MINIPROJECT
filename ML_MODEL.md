# ML model

## Task

Binary classification of INDOFLOODS events:

- `y = 1` if `Flood Type == "Severe Flood"`
- `y = 0` if `Flood Type == "Flood"`

4548 events (2919 / 1629). Peak flood level is **not a feature**.

This label is largely **station-specific** (a gauge-majority classifier already scores ~75.7%). Precipitation correlation with Severe Flood is near zero. ExtraTrees / stacking matched Random Forest and were discarded as 100MB+ files with no accuracy gain.

## Measured test metrics (held-out 910 events)

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
| --- | --- | --- | --- | --- | --- |
| **Random Forest (selected)** | **76.8%** | 0.68 | 0.64 | 0.657 | **0.818** |
| XGBoost | 75.8% (best threshold) / 74.8% @0.5 | — | — | 0.626 | 0.806 |

These numbers are in `models/evaluation.json`. They are the real ceiling for this label, not 99% marketing accuracy.

## Live / simulation probability

Command-center **Flood Probability** used by decision policy is:

`INDOFLOODS ML prior + rainfall sigmoid + stage vs danger`

so risk **rises as rain and river/dam stage rise** (required for monitor → human review → auto). Raw `ml_probability` is stored and shown beside it. ML accuracy above is **not** claimed for the rainfall sigmoid.

## Artifacts

```
models/random_forest_flood.pkl
models/xgboost_flood.pkl
models/model_metadata.json
models/evaluation.json
```

Retrain: `python scripts/train_flood_model.py`
