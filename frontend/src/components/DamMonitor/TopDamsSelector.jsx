/** India Top 10 Dams picker — reference/navigation only. Selecting a dam
 * flies the existing map to it; it does not load or affect a simulation
 * scenario. Mirrors DamSelector's card styling. */
export default function TopDamsSelector({ dams = [], selectedId, onSelect }) {
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
            {dam.state} · {dam.river}
          </span>
        </button>
      ))}
    </div>
  );
}
