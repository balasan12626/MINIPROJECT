# P1: what only the authors can do

**Before submitting**
- [ ] Read the whole PDF (`final/SUBMIT_blind_review.pdf`) and confirm every claim. The IEEE AI-use disclosure in the Acknowledgment says you checked everything, so you must actually do so.
- [ ] Choose the venue and check its page limit, template and whether acknowledgments are allowed in the blind version.
- [ ] Do not submit P3 at the same time: its angle-memory idea is now covered by this paper's transfer result.

**To reach ~9 (optional, needs your accounts or time)**
- [ ] Hardware: run the fixed-angle XY circuit for 2–3 twin instances on IBM Quantum (free tier, 12 qubits). Report P_opt and success@32 against the noiseless and trajectory numbers.
- [ ] Larger sizes: G = 6–8 with an MPS simulator (qiskit-aer `matrix_product_state`) to test transfer at 18–24 qubits.
- [ ] Real demand: replace the sampled group sizes and seat counts in `exp_p1_cities.py` with recorded data if any is available.

**How to rebuild**
```
.venv\Scripts\python.exe .claude\skills\ieee-paper\series\p1_quantum\exp_p1_v2.py %TEMP%\aquasentinel-series
... exp_p1_transfer.py / exp_p1_holdout.py / exp_p1_cities.py (same argument)
set PAPER_MAX_PAGES=6 && .venv\Scripts\python.exe .claude\skills\ieee-paper\series\build_series.py p1
```
