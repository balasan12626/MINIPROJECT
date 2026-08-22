"""K-means clustering for many concurrent SOS requests."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.cluster import KMeans

from backend.utils.geo import haversine_km


def cluster_emergencies(
    emergencies: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    max_clusters: int | None = None,
) -> dict[str, Any]:
    open_items = [
        e
        for e in emergencies
        if str(e.get("status") or "open").lower() in {"open", "assigned", "active"}
        and e.get("lat") is not None
        and e.get("lon") is not None
    ]
    if not open_items:
        return {"available": True, "algorithm": "kmeans", "n_sos": 0, "n_clusters": 0, "clusters": []}

    coords = np.array([[float(e["lat"]), float(e["lon"])] for e in open_items], dtype=float)
    n = len(open_items)
    k_cap = max_clusters or max(len(teams) or 1, 1)
    k = max(1, min(k_cap, n, 8))
    if n == 1 or k == 1:
        labels = np.zeros(n, dtype=int)
        centers = np.array([coords.mean(axis=0)])
    else:
        model = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = model.fit_predict(coords)
        centers = model.cluster_centers_

    clusters = []
    available_teams = [t for t in teams if str(t.get("status") or "AVAILABLE").upper() in {"AVAILABLE", "ASSIGNED"}] or list(teams)
    used = set()
    for cid in range(int(centers.shape[0])):
        members = [open_items[i] for i, lab in enumerate(labels) if int(lab) == cid]
        if not members:
            continue
        lat, lon = float(centers[cid][0]), float(centers[cid][1])
        people = sum(int(m.get("people") or 1) for m in members)
        team = None
        if available_teams:
            remaining = [t for t in available_teams if t.get("team_id") not in used] or available_teams
            team = min(remaining, key=lambda t: haversine_km(lat, lon, float(t["lat"]), float(t["lon"])))
            used.add(team.get("team_id"))
        clusters.append(
            {
                "cluster_id": f"C{cid + 1}",
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "sos_count": len(members),
                "people": people,
                "emergency_ids": [str(m.get("_id") or m.get("id") or "") for m in members],
                "members": [
                    {
                        "citizen_name": m.get("citizen_name"),
                        "age": m.get("age"),
                        "water_level_note": m.get("water_level_note"),
                        "lat": m.get("lat"),
                        "lon": m.get("lon"),
                        "people": m.get("people"),
                        "_id": str(m.get("_id") or m.get("id") or ""),
                    }
                    for m in members
                ],
                "assigned_team": (team or {}).get("team_id"),
                "assigned_team_name": (team or {}).get("name"),
            }
        )
    clusters.sort(key=lambda c: c["sos_count"], reverse=True)
    from backend.services.priority import rank_citizens, vulnerability_label

    flat = []
    for cl in clusters:
        for m in cl.get("members") or []:
            row = dict(m)
            row["cluster_id"] = cl["cluster_id"]
            row["assigned_team"] = cl.get("assigned_team")
            row["assigned_team_name"] = cl.get("assigned_team_name")
            flat.append(row)
        ranked = rank_citizens(cl.get("members") or [])
        cl["priority_queue"] = []
        for i, m in enumerate(ranked, start=1):
            cl["priority_queue"].append(
                {
                    "order_in_cluster": i,
                    "citizen_name": m.get("citizen_name"),
                    "age": m.get("age"),
                    "water_level_note": m.get("water_level_note"),
                    "vulnerability": vulnerability_label(m),
                    "people": m.get("people"),
                }
            )
    global_order = rank_citizens(flat)
    return {
        "available": True,
        "algorithm": "kmeans",
        "n_sos": n,
        "n_clusters": len(clusters),
        "clusters": clusters,
        "priority_global": [
            {
                "rescue_order": c.get("rescue_order"),
                "citizen_name": c.get("citizen_name"),
                "age": c.get("age"),
                "water_level_note": c.get("water_level_note"),
                "vulnerability": c.get("vulnerability"),
                "cluster_id": c.get("cluster_id"),
                "assigned_team": c.get("assigned_team"),
                "assigned_team_name": c.get("assigned_team_name"),
                "lat": c.get("lat"),
                "lon": c.get("lon"),
                "people": c.get("people"),
            }
            for c in global_order
        ],
    }
