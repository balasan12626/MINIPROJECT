# Implementation Progress & Roadmap Status

This document tracks all completed implementations, current work in progress, and upcoming tasks for the 6 roadmap features requested.

---

## Summary Matrix

| Feature | Description | Status | Backend / Script | Frontend UI | Tests |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **F27** | Shelter capacity from building size (Sphere Standard) | **✅ BUILT** | `scripts/build_shelter_capacity.py` | `ShelterCapacityPanel.jsx` | 9/9 Passed |
| **F28** | Food, water & medicine supply runs to shelters | **✅ BUILT** | `backend/services/supply.py` | `SupplyPanel.jsx`, 🚚 Map icon | 4/4 Passed |
| **F22** | Boats for cut-off people | **✅ BUILT** | `backend/services/boat_route.py` | `LiveRescueMap.jsx`, 🚤 Map icon | 5/5 Passed |
| **F35** | AI Assistant accuracy evaluation (Grounded vs Raw) | **✅ BUILT** | `scripts/eval_ai_assistant.py` | `AiEvalCard` on Algorithms tab | 6/6 Passed |
| **F26** | Height-based road flood risk (HAND from Copernicus DEM) | **✅ BUILT** | `scripts/build_hand.py` | `HandCompareCard`, Setup toggle | 3/3 Passed |
| **F20** | Validate road closures against satellite flood maps | **✅ BUILT** | `scripts/validate_closures.py` | `ClosureValidationCard` | 11/11 Passed |

---

## Detailed Breakdown of Work Done

### 1. F27 — Shelter Capacity from Building Size (Sphere Standard)
* **Standard & Citation**: Sphere Handbook 2018 (4th ed.), Shelter & Settlement Standard 3: Living space (minimum covered living space 3.5 m² per person).
* **Backend**:
  * Implemented [`scripts/build_shelter_capacity.py`](file:///d:/fineal%20mini%20proejct/1/scripts/build_shelter_capacity.py) using pure Python geodesic polygon area calculation.
  * Formula: $\text{Capacity} = \lfloor \frac{\text{area\_m2} \times \text{levels} \times \text{usable\_share}}{3.5} \rfloor$ with `usable_share = 0.5` (explicitly labelled assumed).
  * Rebuilt all 6 city JSON files (`delhi`, `mumbai`, `chennai`, `kolkata`, `guwahati`, `patna`).
  * Shelters without OSM building footprints fall back safely to `"assumed by building type"`.
* **Frontend**:
  * Added [`ShelterCapacityPanel.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/rescue/ShelterCapacityPanel.jsx) displaying formula breakdown per shelter.
* **Tests**:
  * [`backend/tests/test_shelter_capacity.py`](file:///d:/fineal%20mini%20proejct/1/backend/tests/test_shelter_capacity.py) — 9/9 tests pass (known polygon area, capacity formula, missing outline fallback, citation verification).

---

### 2. F28 — Food, Water and Medicine Supply Runs to Shelters
* **Standard & Citation**: Sphere Handbook 2018: WASH Water standard 2.1 ($\ge 15\text{ L/person/day}$) and Food Security standard 6.1 ($\ge 2,100\text{ kcal/person/day}$).
* **Backend**:
  * Created [`backend/services/supply.py`](file:///d:/fineal%20mini%20proejct/1/backend/services/supply.py) modeling dynamic supply consumption as simulation time passes.
  * Supply trucks are dispatched nearest-need-first on real road networks using `person_ops.route_candidates`.
  * Reroutes automatically on road closures using the existing F1 reroute hook.
  * Added `supply_board` to `engine.state()`. Fleet parameter `trucks` defaults to 0 (feature off by default for backward compatibility).
* **Frontend**:
  * Added supply toggle and truck count slider in [`CityPicker.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/scenario/CityPicker.jsx).
  * Added [`SupplyPanel.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/rescue/SupplyPanel.jsx) showing water, food, medicine person-days and hours remaining per shelter.
  * Added cached 🚚 truck icon with real-time transit path on [`LiveRescueMap.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/rescue/LiveRescueMap.jsx).
* **Tests**:
  * [`backend/tests/test_supply.py`](file:///d:/fineal%20mini%20proejct/1/backend/tests/test_supply.py) — 4/4 tests pass (need scales with delivered people, trucks avoid closed roads, trucks=0 reproduces identical baseline).

---

### 3. F22 — Boats for Cut-Off People
* **Backend**:
  * Created [`backend/services/boat_route.py`](file:///d:/fineal%20mini%20proejct/1/backend/services/boat_route.py) with 8-directional A* grid search over mapped water bodies and flooded buffer zones.
  * Computes exact navigation coordinates, nautical distance (km), and travel minutes at assumed 15 km/h.
  * Integrated unit role `boat` into `person_ops.py`: boats are offered **strictly** to people with `no_open_road`. People with open roads continue to use ambulances.
  * Fleet parameter `boats` defaults to 0 (feature off by default).
* **Frontend**:
  * Added boat fleet slider in `CityPicker.jsx`.
  * Rendered cached 🚤 boat icon and dashed blue marine paths on `LiveRescueMap.jsx`.
  * Added `🚤 by boat` badge in `LivePeopleTable.jsx`.
* **Tests**:
  * [`backend/tests/test_boats.py`](file:///d:/fineal%20mini%20proejct/1/backend/tests/test_boats.py) — 5/5 tests pass (synthetic grid passability, A* never crosses dry land, boats never given to accessible people, boats=0 preservation).

---

### 4. F35 — AI Assistant Accuracy Evaluation
* **Backend & Benchmark**:
  * Created [`scripts/eval_ai_assistant.py`](file:///d:/fineal%20mini%20proejct/1/scripts/eval_ai_assistant.py) generating 200 deterministic questions from state across 6 categories (people, unknown people, fleet, shelters, dams, flood risk).
  * Executed live against Groq LLM with seed 42 and saved results to [`models/ai_eval_v1.json`](file:///d:/fineal%20mini%20proejct/1/models/ai_eval_v1.json).
  * Measured:
    * **Production System (with Grounding Filter)**: 70.5% accuracy, 100% numerical groundedness (0 hallucinated numbers), 63% refusal rate on unknown entities.
    * **Ablation (Raw LLM without Grounding Filter)**: 65.5% accuracy, lower groundedness.
* **Frontend**:
  * Built `AiEvalCard` in [`MeasuredCards.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/scenario/MeasuredCards.jsx) showing production accuracy, grounded rate, and category breakdowns.
* **Tests**:
  * [`backend/tests/test_eval_ai_assistant.py`](file:///d:/fineal%20mini%20proejct/1/backend/tests/test_eval_ai_assistant.py) — 6/6 tests pass (deterministic question bank, scorer verification, ablation flag).

---

### 5. F26 — Height-Based Road Flood Risk (HAND)
* **Hydrological Model**:
  * Height Above Nearest Drainage (HAND, Rennó et al. 2008) based on Copernicus DEM GLO-30 (30 m).
  * Implemented pure NumPy D8 steepest descent flow direction, drainage accumulation, and HAND calculation in [`scripts/build_hand.py`](file:///d:/fineal%20mini%20proejct/1/scripts/build_hand.py) (zero external GIS dependencies).
* **Backend**:
  * Processed all 6 cities; added `flood_exposure_v2`, `elevation_m`, and `hand_m` to all city files while preserving `flood_exposure` v1.
  * Added `exposure_model: Literal["distance", "hand"] = "distance"` in schemas, `engine.py`, and `ops_sim.py`.
  * Saved comparison models [`models/hand_compare_v1_<city>.json`](file:///d:/fineal%20mini%20proejct/1/models/).
* **Frontend**:
  * Added Exposure Model selector (v1 Distance vs v2 HAND) in Setup tab ([`CityPicker.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/scenario/CityPicker.jsx)).
  * Added `HandCompareCard` to [`MeasuredCards.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/scenario/MeasuredCards.jsx) and mounted it in [`ScenarioOutputs.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/scenario/ScenarioOutputs.jsx).
* **Tests**:
  * [`backend/tests/test_hand.py`](file:///d:/fineal%20mini%20proejct/1/backend/tests/test_hand.py) — 3/3 tests pass (synthetic valley, v1 preservation, closure order divergence under identical rule).

---

### 6. F20 — Validate Road Closures Against Satellite Flood Maps
* **Ground Truth Data**:
  * UNOSAT activation `FL20151123IND` ("Geodata of Flood Waters Over Chennai Area, Tamil Nadu State, India") from CERN/HDX (Sentinel-1 SAR analysis).
  * OSM-India crowdsourced and verified flooded streets layer (`chennai-flooded-streets-Dec2.geojson`, CC0).
* **Backend**:
  * Implemented pure-Python ESRI Shapefile reader, Jordan curve theorem point-in-polygon ray-caster with grid spatial bounding-box indexing.
  * Spatial `BucketGrid` index for crowdsourced points.
  * Evaluated against real road network: **Precision: 93.6%, Recall: 37.2%, F1: 0.532** at default blockage level (0.35).
  * Generated [`models/closure_validation_v1_chennai.json`](file:///d:/fineal%20mini%20proejct/1/models/closure_validation_v1_chennai.json) with breakdown by road class (primary, secondary, trunk) and threshold sweeps across blockage levels [0.0..0.75].
* **Frontend**:
  * Created `ClosureValidationCard` in [`MeasuredCards.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/scenario/MeasuredCards.jsx) showing precision/recall, F1, and threshold sweep table.
  * Mounted on the Algorithms tab in [`ScenarioOutputs.jsx`](file:///d:/fineal%20mini%20proejct/1/frontend/src/components/scenario/ScenarioOutputs.jsx).
* **Tests**:
  * [`backend/tests/test_closure_validation.py`](file:///d:/fineal%20mini%20proejct/1/backend/tests/test_closure_validation.py) — 11/11 tests pass (point-in-polygon on known geometry, spatial indices, precision/recall math, metadata verification).

---

## All 6 Roadmap Features Completed & Tested

| Feature | Unit Tests | Verification Result |
| :--- | :---: | :--- |
| **F27 (Sphere Shelter Capacity)** | 9/9 Passed | Sphere Standard 3.5 m² per person applied to building outlines |
| **F28 (Food/Water/Medicine Supply)** | 4/4 Passed | Supply trucks route dynamically avoiding closures |
| **F22 (Boats for Cut-Off People)** | 5/5 Passed | Marine A* pathfinding strictly for stranded citizens |
| **F35 (AI Assistant Evaluation)** | 6/6 Passed | Grounded accuracy measured against ablation |
| **F26 (HAND Flood Risk Model)** | 3/3 Passed | Copernicus DEM GLO-30 D8 drainage topography |
| **F20 (Satellite Closure Validation)** | 11/11 Passed | Precision & recall validated against UNOSAT & OSM ground truth |

* Full backend test suite: **306/306 passed (100%)**
* Full frontend test suite: **112/112 passed (100%)**
* Frontend build: **Clean production build (0 compiler errors)**

