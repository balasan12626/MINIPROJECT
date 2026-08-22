# Benchmarks

Numbers are generated at runtime. Do not copy these as universal results.

## ML

`GET /api/ml/benchmark` returns `models/evaluation.json` (see ML_MODEL.md).

Latest trained comparison (event-level test set):

- Random Forest accuracy **76.8%**, ROC-AUC **0.818**, F1 0.657 (selected)
- XGBoost accuracy 75.8% at tuned threshold, ROC-AUC 0.806

Severe-vs-Flood in INDOFLOODS is mostly a station label; ~76% is near the Bayes ceiling for that target. Live policy probability also uses rainfall + stage (see ML_MODEL.md).

## Optimization

`POST /api/optimization/benchmark` runs greedy, Dijkstra, simulated annealing, and QAOA-inspired on the current shelter/zone set and stores `benchmark_results`.

## Real-time

`GET /api/metrics` returns last measured pipeline latencies: ingestion, ml, agent, optimization, websocket, end-to-end. Empty until a pipeline cycle has run (`DATA UNAVAILABLE`).
