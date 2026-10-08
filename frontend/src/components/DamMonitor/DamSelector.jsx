/** 5-dam scenario picker — mirrors ScenarioBuilder's .scenario-pick cards. */
export default function DamSelector({ dams = [], selectedId, onSelect }) {
  return (
    <div className="form-grid scenario-pick-grid dam-selector-grid">
      {dams.map((dam) => (
        <button
          key={dam.id}
          type="button"
          className={`scenario-pick ${dam.id === selectedId ? "active" : ""}`}
          onClick={() => onSelect?.(dam.id)}
        >
          <strong>{dam.name}</strong>
          <span>
            {dam.state} · {dam.fill_percentage}% · {dam.status.replace("_", " ")}
          </span>
        </button>
      ))}
    </div>
  );
}
