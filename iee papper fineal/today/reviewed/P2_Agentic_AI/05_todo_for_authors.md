# P2: what only the authors can do

**Before submitting**
- [ ] Read the whole PDF and confirm every claim (the AI-use disclosure says you did).
- [ ] **Labels:** open `final/data/p2_labels_review.txt` and check the reference labels, especially the 4 overrides in `label_p2_live.py` (`OVERRIDES`). The paper says "one annotator", so only change that wording if a second person labels the replies.
- [ ] Choose the venue and check its page limit and blind-review rules.

**Recommended (raises the score toward 9)**
- [ ] Finish the LLM judge on all 300 live replies after the Groq daily token quota resets. Run the command below; it resumes and only judges the missing replies. Then rebuild. The text and tables update automatically, and the asserts will tell you if a claim changes.
  `.venv\Scripts\python.exe .claude\skills\ieee-paper\series\p2_agentic\exp_p2_judge.py %TEMP%\aquasentinel-series 40`
- [ ] A second annotator labels the 300 replies independently; report Cohen's κ.
- [ ] Add a third generator model from another family and rerun `exp_p2_live.py` (about 40 minutes per model on the free tier).

**Rebuild**
`set PAPER_MAX_PAGES=6 && .venv\Scripts\python.exe .claude\skills\ieee-paper\series\build_series.py p2`
