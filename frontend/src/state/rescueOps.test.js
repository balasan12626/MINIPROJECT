import { describe, expect, it } from "vitest";
import {
  bearingDeg,
  buildEventFeed,
  deriveRescueOps,
  pathMetrics,
  positionAlong,
  serverClockOffset,
  slicePath,
  stageOf,
} from "./rescueOps.js";
import { CHILD_MAX_AGE, SHELTER_BY_NAME, isChild, shelterLocation } from "../data/rescueAssets.js";
import { gridCluster, bubbleSize } from "../components/rescue/LiveRescueMap.jsx";

/** Backend-issued stage length (person_ops `ops_stage_seconds`). */
const STAGE_SECONDS = 20;

const T0 = Date.parse("2026-09-23T10:00:00+00:00");
const at = (secs) => new Date(T0 + secs * 1000).toISOString();

/** A citizen shaped exactly like GET /api/simulation/state returns. */
function citizen(over = {}) {
  return {
    citizen_name: "Priya Sharma",
    age: 29,
    people: 3,
    lat: 28.651,
    lon: 77.262,
    water_level_note: "knee-deep",
    rescue_order: 1,
    vulnerability: "standard",
    cluster_id: "C1",
    assigned_team_name: "Delhi Police Disaster Cell ITO",
    ambulance_name: "Ambulance Unit 1",
    shelter_name: "Delhi University Sports Complex",
    ops_status: "queued",
    ops_stage_at: at(0),
    ops_stage_seconds: STAGE_SECONDS,
    journey: [],
    timestamps: {},
    ...over,
  };
}

const DEPOT = [28.6288, 77.2419]; // Delhi Police Disaster Cell ITO

function sim(over = {}) {
  return {
    citizens: [citizen()],
    team_paths: [
      {
        team_id: "RT-03",
        team_name: "Delhi Police Disaster Cell ITO",
        role: "rescue",
        from: DEPOT,
        to: [28.651, 77.262],
        citizen_name: "Priya Sharma",
      },
    ],
    eta_board: [{ citizen_name: "Priya Sharma", eta_min: 9.4 }],
    contact_log: [],
    events: [],
    shelter_board: [],
    ...over,
  };
}

describe("shelter resolution", () => {
  it("resolves every name person_ops can assign", () => {
    // backend/services/person_ops.py SHELTER_POOL — every name must resolve or
    // a person's drop-off leg cannot be drawn.
    const pool = [
      "Delhi University Sports Complex",
      "Talkatora Indoor Stadium",
      "Jawaharlal Nehru Stadium",
      "Commonwealth Games Village Hall",
      "Yamuna Sports Complex Shelter",
      "Thyagaraj Sports Complex",
      "Chhatrasal Stadium",
      "IIT Delhi Lecture Hall Complex",
      "Akshardham Community Shelter",
    ];
    for (const name of pool) {
      const loc = shelterLocation(name);
      expect(loc, `${name} must resolve`).toBeTruthy();
      expect(Number.isFinite(loc.lat)).toBe(true);
      expect(Number.isFinite(loc.lon)).toBe(true);
    }
  });

  it("covers the desk-only shelter that seed.py lacks", () => {
    // Regression guard: a seed-only lookup silently drops 1 person in 5.
    expect(SHELTER_BY_NAME.has("Yamuna Sports Complex Shelter")).toBe(true);
  });

  it("returns null for an unknown name rather than guessing", () => {
    expect(shelterLocation("Nowhere Stadium")).toBeNull();
    expect(shelterLocation(null)).toBeNull();
  });
});

describe("stage reading", () => {
  it("uses the backend's own precedence", () => {
    expect(stageOf({ ops_status: "en_route", live_status: "queued" })).toBe("en_route");
    expect(stageOf({ live_status: "to_shelter" })).toBe("to_shelter");
    expect(stageOf({ status: "rescued" })).toBe("rescued");
  });

  it("falls back to queued for unknown values instead of inventing one", () => {
    expect(stageOf({ ops_status: "banana" })).toBe("queued");
    expect(stageOf({})).toBe("queued");
  });
});

describe("unit interpolation", () => {
  it("draws no unit while queued — nothing is moving yet", () => {
    const { units } = deriveRescueOps(sim(), T0 + 5000);
    expect(units).toHaveLength(0);
  });

  it("draws no unit once rescued", () => {
    const s = sim({ citizens: [citizen({ ops_status: "rescued", ops_stage_at: at(0) })] });
    expect(deriveRescueOps(s, T0 + 5000).units).toHaveLength(0);
  });

  it("moves depot -> person across the en_route stage", () => {
    const s = sim({ citizens: [citizen({ ops_status: "en_route", ops_stage_at: at(0) })] });

    const start = deriveRescueOps(s, T0).units[0];
    expect(start.position[0]).toBeCloseTo(DEPOT[0], 6);
    expect(start.position[1]).toBeCloseTo(DEPOT[1], 6);

    const mid = deriveRescueOps(s, T0 + (STAGE_SECONDS / 2) * 1000).units[0];
    expect(mid.position[0]).toBeCloseTo((DEPOT[0] + 28.651) / 2, 6);
    expect(mid.position[1]).toBeCloseTo((DEPOT[1] + 77.262) / 2, 6);

    const end = deriveRescueOps(s, T0 + STAGE_SECONDS * 1000).units[0];
    expect(end.position[0]).toBeCloseTo(28.651, 6);
    expect(end.position[1]).toBeCloseTo(77.262, 6);
  });

  it("moves person -> shelter across the to_shelter stage", () => {
    const s = sim({
      citizens: [citizen({ ops_status: "to_shelter", ops_stage_at: at(0), unit_role: "ambulance", unit_name: "Ambulance Unit 1" })],
    });
    const shelter = shelterLocation("Delhi University Sports Complex");
    const u = deriveRescueOps(s, T0 + STAGE_SECONDS * 1000).units[0];
    expect(u.role).toBe("ambulance");
    expect(u.label).toBe("Ambulance Unit 1");
    expect(u.position[0]).toBeCloseTo(shelter.lat, 6);
    expect(u.position[1]).toBeCloseTo(shelter.lon, 6);
  });

  it("clamps rather than overshooting when a stage runs long", () => {
    const s = sim({ citizens: [citizen({ ops_status: "en_route", ops_stage_at: at(0) })] });
    const u = deriveRescueOps(s, T0 + 999_000).units[0];
    expect(u.progress).toBe(1);
    expect(u.position[0]).toBeCloseTo(28.651, 6);
  });

  it("never runs backwards if the client clock is ahead", () => {
    const s = sim({ citizens: [citizen({ ops_status: "en_route", ops_stage_at: at(60) })] });
    const u = deriveRescueOps(s, T0).units[0];
    expect(u.progress).toBe(0);
  });

  it("does not animate when the backend gave no stage timestamp", () => {
    const s = sim({ citizens: [citizen({ ops_status: "en_route", ops_stage_at: null })] });
    const u = deriveRescueOps(s, T0 + 6000).units[0];
    expect(u.progress).toBe(0);
  });

  it("falls back to the team depot when team_paths has no entry", () => {
    const s = sim({ team_paths: [], citizens: [citizen({ ops_status: "en_route", ops_stage_at: at(0) })] });
    const u = deriveRescueOps(s, T0).units[0];
    expect(u.position[0]).toBeCloseTo(DEPOT[0], 4);
  });
});

describe("people projection", () => {
  it("carries real backend fields through untouched", () => {
    const { people } = deriveRescueOps(sim(), T0);
    const p = people[0];
    expect(p.name).toBe("Priya Sharma");
    expect(p.age).toBe(29);
    expect(p.etaMin).toBe(9.4); // from eta_board, joined by name
    expect(p.ambulance).toBe("Ambulance Unit 1");
    expect(p.shelterLoc).toBeTruthy();
  });

  it("prefers the backend's own ETA and unit fields", () => {
    const s = sim({
      citizens: [citizen({ eta_min: 14.2, eta_to_shelter_min: 6.1, unit_role: "rescue", unit_name: "Delhi Police Disaster Cell ITO", ambulance_name: null })],
    });
    const p = deriveRescueOps(s, T0).people[0];
    expect(p.etaMin).toBe(14.2);
    expect(p.etaShelterMin).toBe(6.1);
    expect(p.ambulance).toBeNull();
    expect(p.unitName).toBe("Delhi Police Disaster Cell ITO");
  });

  it("marks SAFE people small only after 5 s", () => {
    const s = sim({ citizens: [citizen({ ops_status: "rescued", ops_stage_at: at(0) })] });
    expect(deriveRescueOps(s, T0 + 2000).people[0].safeSmall).toBe(false);
    expect(deriveRescueOps(s, T0 + 6000).people[0].safeSmall).toBe(true);
  });

  it("gives child / elderly / chest-deep a priority ring", () => {
    const s = sim({ citizens: [citizen({ vulnerability: "child" }), citizen({ citizen_name: "B", vulnerability: "standard" })] });
    const [a, b] = deriveRescueOps(s, T0).people;
    expect(a.priorityRing).toBe(true);
    expect(b.priorityRing).toBe(false);
  });

  it("counts stages and people delivered", () => {
    const s = sim({
      citizens: [
        citizen({ citizen_name: "A", ops_status: "queued", people: 2 }),
        citizen({ citizen_name: "B", ops_status: "en_route", people: 1 }),
        citizen({ citizen_name: "C", ops_status: "rescued", people: 4 }),
        citizen({ citizen_name: "D", ops_status: "rescued", people: 3 }),
      ],
      team_paths: [],
    });
    const { counters } = deriveRescueOps(s, T0 + 1000);
    expect(counters.unitsMoving).toBe(1);
    expect(counters.totalSos).toBe(4);
    expect(counters.waiting).toBe(1);
    expect(counters.enRoute).toBe(1);
    expect(counters.rescued).toBe(2);
    expect(counters.peopleRescued).toBe(7);
  });

  it("reports shelter arrivals separately from backend occupancy", () => {
    // engine.py inflates occupancy on a growth curve unrelated to rescues, so
    // blending the two would misreport the run.
    const s = sim({
      citizens: [
        citizen({ citizen_name: "A", ops_status: "rescued", people: 2 }),
        citizen({ citizen_name: "B", ops_status: "to_shelter", people: 3 }),
      ],
      shelter_board: [
        { shelter_id: "S06", name: "Delhi University Sports Complex", capacity: 1400, occupancy: 110, seats_left: 1290 },
      ],
      team_paths: [],
    });
    const { shelters } = deriveRescueOps(s, T0);
    expect(shelters[0].backendOccupancy).toBe(110);
    expect(shelters[0].arrivedThisRun).toBe(2);
    expect(shelters[0].inboundThisRun).toBe(3);
  });
});

describe("route interpolation", () => {
  const route = [
    [28.6, 77.2],
    [28.7, 77.2],
    [28.7, 77.3],
  ];

  it("follows the backend route polyline, not a straight line", () => {
    const s = sim({
      citizens: [
        citizen({
          ops_status: "en_route",
          ops_stage_at: at(0),
          ops_stage_seconds: 10,
          route_to_person: { points: route, km: 20, sim_minutes: 20 },
        }),
      ],
    });
    const u = deriveRescueOps(s, T0).units[0];
    expect(u.path).toHaveLength(3);
    const { cum } = pathMetrics(route);
    const mid = positionAlong(route, cum, 0.5);
    // halfway along an L-shaped route is the corner-ish, never the diagonal midpoint
    expect(mid[0]).toBeGreaterThan(28.69);
    const end = deriveRescueOps(s, T0 + 10_000).units[0];
    expect(end.position[0]).toBeCloseTo(28.7, 6);
    expect(end.position[1]).toBeCloseTo(77.3, 6);
    expect(end.moving).toBe(false);
  });

  it("uses the backend's per-stage duration, not a fixed step", () => {
    const s = sim({
      citizens: [citizen({ ops_status: "en_route", ops_stage_at: at(0), ops_stage_seconds: 40 })],
    });
    expect(deriveRescueOps(s, T0 + 20_000).units[0].progress).toBeCloseTo(0.5, 6);
  });

  it("slices a trail between two fractions", () => {
    const { cum } = pathMetrics(route);
    const part = slicePath(route, cum, 0.25, 0.75);
    expect(part.length).toBeGreaterThanOrEqual(3); // includes the corner
  });
});

describe("map helpers", () => {
  it("grid-clusters close points and keeps far ones single", () => {
    const pts = [
      { key: "a", lat: 0, lon: 0 },
      { key: "b", lat: 0.001, lon: 0.001 },
      { key: "c", lat: 5, lon: 5 },
    ];
    const project = ([lat, lon]) => ({ x: lon * 1000, y: lat * 1000 });
    const { singles, clusters } = gridCluster(pts, project, 44);
    expect(clusters).toHaveLength(1);
    expect(clusters[0].members.map((m) => m.key).sort()).toEqual(["a", "b"]);
    expect(singles.map((m) => m.key)).toEqual(["c"]);
  });

  it("scales bubble size with people, capped at 5+", () => {
    expect(bubbleSize(1)).toBeLessThan(bubbleSize(3));
    expect(bubbleSize(5)).toBe(bubbleSize(40));
  });

  it("mirrors the backend child definition", () => {
    expect(CHILD_MAX_AGE).toBe(12);
    expect(isChild(11)).toBe(true);
    expect(isChild(12)).toBe(false);
    expect(isChild(null)).toBe(false);
  });
});

describe("event feed", () => {
  it("merges engine events with per-person journey entries, newest first", () => {
    const s = sim({
      events: [{ timestamp: at(5), message: "Flood probability 74%", sim_time_sec: 5 }],
      citizens: [
        citizen({
          journey: [
            { at: at(1), event: "QUEUED", detail: "In SOS queue", agent: "Administrator Agent", status: "queued" },
            { at: at(9), event: "ASSIGNED", detail: "Ambulance assigned", agent: "Ambulance Agent", status: "assigned" },
          ],
        }),
      ],
    });
    const feed = buildEventFeed(s);
    expect(feed).toHaveLength(3);
    expect(feed[0].text).toMatch(/Ambulance assigned/);
    expect(feed[1].text).toBe("Flood probability 74%");
    expect(feed[2].text).toMatch(/In SOS queue/);
    expect(feed[0].personKey).toBe("Priya Sharma");
    expect(feed[1].kind).toBe("engine");
  });

  it("survives malformed timestamps", () => {
    const s = sim({ events: [{ timestamp: "not-a-date", message: "x" }] });
    expect(buildEventFeed(s)).toHaveLength(0);
  });
});

describe("clock offset", () => {
  it("corrects forward when the server is ahead of the client", () => {
    const s = sim({ citizens: [citizen({ ops_stage_at: at(0) })] });
    const offset = serverClockOffset(s, T0 - 30_000);
    expect(offset).toBe(30_000);
  });

  it("never corrects backwards", () => {
    const s = sim({ citizens: [citizen({ ops_stage_at: at(0) })] });
    expect(serverClockOffset(s, T0 + 30_000)).toBe(0);
  });
});

describe("bearing", () => {
  it("points north and east correctly", () => {
    expect(bearingDeg([28.6, 77.2], [28.7, 77.2])).toBeCloseTo(0, 1);
    expect(bearingDeg([28.6, 77.2], [28.6, 77.3])).toBeCloseTo(90, 1);
  });
});
