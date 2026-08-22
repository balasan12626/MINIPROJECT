"""Default multi-citizen SOS roster for scenario builder."""

DEFAULT_CITIZENS = [
    {"citizen_name": "Priya Sharma", "age": 29, "lat": 28.6510, "lon": 77.2620, "people": 3, "water_level_note": "knee-deep"},
    {"citizen_name": "Aarav Mehta", "age": 41, "lat": 28.6284, "lon": 77.2495, "people": 2, "water_level_note": "waist-deep"},
    {"citizen_name": "Ananya Reddy", "age": 17, "lat": 28.6075, "lon": 77.2898, "people": 4, "water_level_note": "ankle-deep"},
    {"citizen_name": "Rohan Gupta", "age": 54, "lat": 28.7150, "lon": 77.2315, "people": 1, "water_level_note": "chest-deep"},
    {"citizen_name": "Fatima Khan", "age": 36, "lat": 28.5518, "lon": 77.2934, "people": 5, "water_level_note": "knee-deep"},
    {"citizen_name": "Kabir Singh", "age": 8, "lat": 28.6558, "lon": 77.2675, "people": 2, "water_level_note": "ankle-deep"},
    {"citizen_name": "Isha Patel", "age": 63, "lat": 28.6406, "lon": 77.2495, "people": 2, "water_level_note": "waist-deep"},
    {"citizen_name": "Vivek Nair", "age": 33, "lat": 28.5889, "lon": 77.2532, "people": 3, "water_level_note": "knee-deep"},
    {"citizen_name": "Meera Joshi", "age": 24, "lat": 28.6127, "lon": 77.2773, "people": 1, "water_level_note": "waist-deep"},
    {"citizen_name": "Arjun Das", "age": 47, "lat": 28.5672, "lon": 77.2100, "people": 4, "water_level_note": "chest-deep"},
]


def roster(n: int = 10) -> list[dict]:
    n = max(0, int(n or 0))
    out = []
    for i in range(n):
        src = dict(DEFAULT_CITIZENS[i % len(DEFAULT_CITIZENS)])
        if i >= len(DEFAULT_CITIZENS):
            src["citizen_name"] = f"{src['citizen_name']} {i + 1}"
            src["lat"] = round(src["lat"] + 0.004 * (i // 10), 5)
            src["lon"] = round(src["lon"] + 0.004 * (i % 5), 5)
        out.append(src)
    return out
