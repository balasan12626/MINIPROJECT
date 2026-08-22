"""Delhi NCR operational geography: real coordinates, curated capacities."""

from datetime import datetime, timezone

SHELTERS = [
    {
        "shelter_id": "S01",
        "name": "Thyagaraj Sports Complex",
        "lat": 28.5786,
        "lon": 77.2134,
        "capacity": 1800,
        "occupancy": 210,
        "status": "open",
        "flood_risk": 0.18,
        "zone": "South-Central",
    },
    {
        "shelter_id": "S02",
        "name": "Jawaharlal Nehru Stadium",
        "lat": 28.5828,
        "lon": 77.2344,
        "capacity": 4200,
        "occupancy": 640,
        "status": "open",
        "flood_risk": 0.22,
        "zone": "South-East",
    },
    {
        "shelter_id": "S03",
        "name": "Chhatrasal Stadium",
        "lat": 28.6995,
        "lon": 77.1918,
        "capacity": 1600,
        "occupancy": 90,
        "status": "open",
        "flood_risk": 0.12,
        "zone": "North",
    },
    {
        "shelter_id": "S04",
        "name": "Talkatora Indoor Stadium",
        "lat": 28.6254,
        "lon": 77.1952,
        "capacity": 1200,
        "occupancy": 40,
        "status": "open",
        "flood_risk": 0.15,
        "zone": "Central",
    },
    {
        "shelter_id": "S05",
        "name": "Commonwealth Games Village Hall",
        "lat": 28.6098,
        "lon": 77.2755,
        "capacity": 900,
        "occupancy": 880,
        "status": "open",
        "flood_risk": 0.48,
        "zone": "East Yamuna",
    },
    {
        "shelter_id": "S06",
        "name": "Delhi University Sports Complex",
        "lat": 28.6886,
        "lon": 77.2095,
        "capacity": 1400,
        "occupancy": 110,
        "status": "open",
        "flood_risk": 0.20,
        "zone": "North Campus",
    },
    {
        "shelter_id": "S07",
        "name": "IIT Delhi Lecture Hall Complex",
        "lat": 28.5456,
        "lon": 77.1926,
        "capacity": 1100,
        "occupancy": 70,
        "status": "open",
        "flood_risk": 0.10,
        "zone": "South",
    },
    {
        "shelter_id": "S08",
        "name": "Akshardham Community Shelter",
        "lat": 28.6127,
        "lon": 77.2773,
        "capacity": 800,
        "occupancy": 800,
        "status": "full",
        "flood_risk": 0.55,
        "zone": "East Yamuna",
    },
]

ROADS = [
    {"road_id": "R01", "name": "Ring Road near ITO", "lat": 28.6284, "lon": 77.2410, "blocked": False, "flood_exposure": 0.42, "traffic": 0.55, "accessible": True},
    {"road_id": "R02", "name": "NH-9 Geeta Colony", "lat": 28.6558, "lon": 77.2675, "blocked": False, "flood_exposure": 0.61, "traffic": 0.48, "accessible": True},
    {"road_id": "R03", "name": "Outer Ring Road Wazirabad", "lat": 28.7125, "lon": 77.2308, "blocked": False, "flood_exposure": 0.57, "traffic": 0.40, "accessible": True},
    {"road_id": "R04", "name": "Mathura Road Nizamuddin", "lat": 28.5889, "lon": 77.2532, "blocked": False, "flood_exposure": 0.33, "traffic": 0.62, "accessible": True},
    {"road_id": "R05", "name": "Vikas Marg Laxmi Nagar", "lat": 28.6303, "lon": 77.2771, "blocked": False, "flood_exposure": 0.70, "traffic": 0.51, "accessible": True},
    {"road_id": "R06", "name": "Aurobindo Marg AIIMS", "lat": 28.5672, "lon": 77.2100, "blocked": False, "flood_exposure": 0.12, "traffic": 0.58, "accessible": True},
    {"road_id": "R07", "name": "GT Karnal Road Azadpur", "lat": 28.7072, "lon": 77.1756, "blocked": False, "flood_exposure": 0.18, "traffic": 0.45, "accessible": True},
    {"road_id": "R08", "name": "Yamuna Bank Road", "lat": 28.6255, "lon": 77.2688, "blocked": False, "flood_exposure": 0.82, "traffic": 0.30, "accessible": True},
]

ZONES = [
    {"zone_id": "Z-A", "name": "Yamuna Pushta / Geeta Colony", "lat": 28.6510, "lon": 77.2620, "population": 4280},
    {"zone_id": "Z-B", "name": "ITO / Rajghat floodplain", "lat": 28.6284, "lon": 77.2495, "population": 3100},
    {"zone_id": "Z-C", "name": "Mayur Vihar Phase I", "lat": 28.6075, "lon": 77.2898, "population": 5200},
    {"zone_id": "Z-D", "name": "Wazirabad / Signature Bridge", "lat": 28.7150, "lon": 77.2315, "population": 2650},
    {"zone_id": "Z-E", "name": "Okhla / Jamia", "lat": 28.5518, "lon": 77.2934, "population": 3800},
]

RESCUE_TEAMS = [
    {"team_id": "RT-01", "name": "NDRF 8th Bn Detachment", "lat": 28.6698, "lon": 77.4306, "status": "AVAILABLE", "capacity": 12},
    {"team_id": "RT-02", "name": "Delhi Fire Service HQ", "lat": 28.6328, "lon": 77.2197, "status": "AVAILABLE", "capacity": 8},
    {"team_id": "RT-03", "name": "Delhi Police Disaster Cell ITO", "lat": 28.6288, "lon": 77.2419, "status": "AVAILABLE", "capacity": 10},
    {"team_id": "RT-04", "name": "SDRF North District", "lat": 28.7041, "lon": 77.1025, "status": "AVAILABLE", "capacity": 8},
]

LANDMARKS = {
    "yamuna": {"name": "Yamuna River (ITO)", "lat": 28.6284, "lon": 77.2410, "kind": "river"},
    "hathnikund": {"name": "Hathnikund Barrage", "lat": 30.3139, "lon": 77.5886, "kind": "dam"},
    "okhla": {"name": "Okhla Barrage", "lat": 28.5463, "lon": 77.3124, "kind": "dam"},
}

GRAPH_NODES = {
    "ITO": (28.6284, 77.2410),
    "RAJGHAT": (28.6406, 77.2495),
    "GEETA": (28.6558, 77.2675),
    "MAYUR": (28.6075, 77.2898),
    "WAZIRABAD": (28.7125, 77.2308),
    "NIZAM": (28.5889, 77.2532),
    "AIIMS": (28.5672, 77.2100),
    "AZADPUR": (28.7072, 77.1756),
    "YBANK": (28.6255, 77.2688),
    "JN": (28.5828, 77.2344),
    "THYAGARAJ": (28.5786, 77.2134),
    "TALKATORA": (28.6254, 77.1952),
    "DU": (28.6886, 77.2095),
    "CHHATRASAL": (28.6995, 77.1918),
    "IIT": (28.5456, 77.1926),
    "CWG": (28.6098, 77.2755),
    "AKSHARDHAM": (28.6127, 77.2773),
}

GRAPH_EDGES = [
    ("ITO", "RAJGHAT", "R01"),
    ("ITO", "NIZAM", "R04"),
    ("ITO", "TALKATORA", "R06"),
    ("RAJGHAT", "GEETA", "R02"),
    ("GEETA", "YBANK", "R08"),
    ("YBANK", "MAYUR", "R05"),
    ("MAYUR", "CWG", "R05"),
    ("MAYUR", "AKSHARDHAM", "R05"),
    ("ITO", "WAZIRABAD", "R03"),
    ("WAZIRABAD", "AZADPUR", "R07"),
    ("AZADPUR", "CHHATRASAL", "R07"),
    ("AZADPUR", "DU", "R07"),
    ("NIZAM", "JN", "R04"),
    ("JN", "THYAGARAJ", "R06"),
    ("THYAGARAJ", "AIIMS", "R06"),
    ("AIIMS", "IIT", "R06"),
    ("CWG", "NIZAM", "R04"),
]


async def seed_if_empty() -> None:
    from backend.database import mongo

    existing = await mongo.find_many("shelters", {}, limit=1)
    now = datetime.now(timezone.utc)
    if not existing:
        for s in SHELTERS:
            await mongo.upsert("shelters", {"shelter_id": s["shelter_id"]}, {**s, "timestamp": now})
    roads = await mongo.find_many("roads", {}, limit=1)
    if not roads:
        for r in ROADS:
            await mongo.upsert("roads", {"road_id": r["road_id"]}, {**r, "timestamp": now})
    teams = await mongo.find_many("rescue_teams", {}, limit=1)
    if not teams:
        for t in RESCUE_TEAMS:
            await mongo.upsert("rescue_teams", {"team_id": t["team_id"]}, {**t, "timestamp": now})
