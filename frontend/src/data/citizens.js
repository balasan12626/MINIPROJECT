/** The one people/residents roster used by /simulation.
 *
 * Mirrors backend/services/citizens.py::DEFAULT_CITIZENS exactly. The backend
 * falls back to its own copy when a run sends no `citizens`, so the two lists
 * must stay identical — otherwise the table you edit and the roster the engine
 * simulates would disagree.
 *
 * There is no second roster and no named roster presets anywhere in the repo:
 * a scenario sizes this list through `sos_count`, nothing more.
 */
export const DEFAULT_CITIZENS = [
  { citizen_name: "Priya Sharma", age: 29, lat: 28.651, lon: 77.262, people: 3, water_level_note: "knee-deep" },
  { citizen_name: "Aarav Mehta", age: 41, lat: 28.6284, lon: 77.2495, people: 2, water_level_note: "waist-deep" },
  { citizen_name: "Ananya Reddy", age: 17, lat: 28.6075, lon: 77.2898, people: 4, water_level_note: "ankle-deep" },
  { citizen_name: "Rohan Gupta", age: 54, lat: 28.715, lon: 77.2315, people: 1, water_level_note: "chest-deep" },
  { citizen_name: "Fatima Khan", age: 36, lat: 28.5518, lon: 77.2934, people: 5, water_level_note: "knee-deep" },
  { citizen_name: "Kabir Singh", age: 8, lat: 28.6558, lon: 77.2675, people: 2, water_level_note: "ankle-deep" },
  { citizen_name: "Isha Patel", age: 63, lat: 28.6406, lon: 77.2495, people: 2, water_level_note: "waist-deep" },
  { citizen_name: "Vivek Nair", age: 33, lat: 28.5889, lon: 77.2532, people: 3, water_level_note: "knee-deep" },
  { citizen_name: "Meera Joshi", age: 24, lat: 28.6127, lon: 77.2773, people: 1, water_level_note: "waist-deep" },
  { citizen_name: "Arjun Das", age: 47, lat: 28.5672, lon: 77.21, people: 4, water_level_note: "chest-deep" },
];

/** Cycles the roster to `n` people, mirroring citizens.py::roster(). */
export function roster(n) {
  const count = Math.max(0, Number(n) || 0);
  return Array.from({ length: count }, (_, i) => {
    const src = { ...DEFAULT_CITIZENS[i % DEFAULT_CITIZENS.length] };
    if (i >= DEFAULT_CITIZENS.length) {
      src.citizen_name = `${DEFAULT_CITIZENS[i % DEFAULT_CITIZENS.length].citizen_name} ${i + 1}`;
      src.lat = Number((src.lat + 0.004 * Math.floor(i / 10)).toFixed(5));
      src.lon = Number((src.lon + 0.004 * (i % 5)).toFixed(5));
    }
    return src;
  });
}

/** Grow or shrink an edited roster to `n` without losing the user's edits. */
export function resizeRoster(current = [], n) {
  const count = Math.max(0, Number(n) || 0);
  if (count === current.length) return current;
  if (count < current.length) return current.slice(0, count);
  const filler = roster(count).slice(current.length);
  return [...current, ...filler];
}
