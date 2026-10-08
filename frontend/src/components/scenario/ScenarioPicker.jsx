import { useEffect, useId, useMemo, useRef, useState } from "react";
import { SCENARIOS, SCENARIO_GROUPS, groupLabel, searchScenarios } from "../../config/scenarios.js";
import { useScenario } from "../../state/ScenarioContext.jsx";

/** Top-of-page scenario selector: type to filter, or pick a card.
 *
 * Selecting only fills the inputs below — it never starts a run. */
export default function ScenarioPicker() {
  const ctx = useScenario();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef(null);
  const listId = useId();

  const matches = useMemo(() => searchScenarios(query), [query]);

  // Close the dropdown on an outside click.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (!boxRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  if (!ctx) return null;
  const { activeId, scenario, selectScenario, running } = ctx;

  const choose = (id) => {
    selectScenario(id);
    setQuery("");
    setOpen(false);
    setCursor(0);
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setCursor((c) => Math.min(c + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      if (open && matches[cursor]) {
        e.preventDefault();
        choose(matches[cursor].id);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <section className="panel scenario-picker" aria-label="Choose scenario">
      <div className="panel-head">
        <h3>Choose scenario</h3>
        <span className="hint scenario-picker-count">
          {SCENARIOS.length} scenarios · {SCENARIO_GROUPS.length} groups
        </span>
      </div>

      {/* ---- combobox ---- */}
      <div className="scenario-combo" ref={boxRef}>
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-label="Search scenarios"
          placeholder="Search scenarios — try “rain”, “shelter”, “benchmark”…"
          value={query}
          disabled={running}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setCursor(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {open ? (
          <ul className="scenario-combo-list" id={listId} role="listbox">
            {matches.length === 0 ? (
              <li className="scenario-combo-empty" role="presentation">
                No scenario matches “{query}”
              </li>
            ) : (
              matches.map((s, i) => (
                <li key={s.id} role="option" aria-selected={s.id === activeId}>
                  <button
                    type="button"
                    className={i === cursor ? "cursor" : ""}
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => choose(s.id)}
                  >
                    <strong>{s.label}</strong>
                    <span className="badge sim">{groupLabel(s.group)}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        ) : null}
      </div>

      {/* ---- grouped cards ---- */}
      {SCENARIO_GROUPS.map((group) => {
        const list = matches.filter((s) => s.group === group.id);
        if (!list.length) return null;
        return (
          <div className="scenario-group" key={group.id}>
            <div className="scenario-group-head">
              <h4>{group.label}</h4>
              <span className="hint">{group.hint}</span>
            </div>
            <div className="form-grid scenario-pick-grid" role="radiogroup" aria-label={group.label}>
              {list.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  role="radio"
                  aria-checked={s.id === activeId}
                  disabled={running}
                  className={`scenario-pick ${s.id === activeId ? "active" : ""}`}
                  onClick={() => choose(s.id)}
                >
                  <strong>{s.label}</strong>
                  <span>{s.description}</span>
                </button>
              ))}
            </div>
          </div>
        );
      })}

      {/* ---- selected summary ---- */}
      {scenario ? (
        <div className="scenario-selected status-row">
          <span className="badge live">{groupLabel(scenario.group)}</span>
          <strong className="scenario-selected-name">{scenario.label}</strong>
          <span className={`badge ${scenario.provenance === "native" ? "live" : "sim"}`}>
            {scenario.provenance === "native" ? "BACKEND PRESET" : "COMPOSED FROM INPUTS"}
          </span>
          <span className="badge warn">EXPECTED {scenario.expectedRisk}</span>
          <p className="hint scenario-selected-desc">{scenario.description}</p>
        </div>
      ) : null}
    </section>
  );
}
