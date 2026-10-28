# Second-annotator task for P2 (reviewer request: independent labels + Cohen's kappa)

One co-author who has **not** seen the guard verdicts labels every reply. Do not open the work folder,
the stored JSON or the paper tables while labelling.

Files
- `replies_to_label.csv`: 432 live replies in random order. Model names and all checker verdicts are hidden.
- `state_facts.csv`: the facts the narrator was given for each `state_index`.

For each row, write `supported` or `unsupported` in the LABEL column.

Protocol (the same written rules the first annotator used)
- **Supported**: the number states a value of the state for the quantity it describes (either model's flood
  probability, rainfall, river level, barrage stage, current time). Honest rounding is fine (87.3% -> 87%).
  Quoting a threshold of the band (40/50/60 %) is also supported.
- **Unsupported**: anything else: a wrong value, a value attached to the wrong quantity, or a quantity the
  state does not contain (arrival time / ETA / travel time, head-count, distance, number of teams, duration).
  An arrival time is always unsupported, even if it happens to equal the current clock time.
- **Procedural** numbers are not claims and are ignored: reporting intervals ("report every 5 minutes"),
  priority or unit labels ("priority 1", "Team 2", "Mission 4", "level 2 alert"), the number of named places
  ("both locations"), band ranges quoted from the rules ("50-60%"), deadlines given as orders
  ("secure the perimeter within 30 minutes").
- A reply is **unsupported** if any number in it is unsupported. Numbers written in words count.
- Use the notes column for any case you found hard.

When done, save the CSV and run (repo root):

    .venv\Scripts\python.exe ".claude\skills\ieee-paper\series\p2_agentic\kappa_p2.py" "iee papper fineal\10OCT\P2_Agentic_AI\second_annotator\replies_to_label.csv"

It prints Cohen's kappa against the first annotator's labels, the disagreements, and guard recall/false-rejection
under the second annotator's labels. Send the output back so the paper can report it.
