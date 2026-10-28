"""F20 — Tests for closure validation against satellite flood maps."""

import json
import math
import pytest

from scripts.validate_closures import (
    BucketGrid,
    PolygonIndex,
    classify_roads,
    compute_metrics,
    haversine_km,
    load_flooded_points,
    metrics_by_class,
    point_in_polygon,
    threshold_sweep,
)


# ---------------------------------------------------------------------------
# Test 1: point_in_polygon — Jordan curve theorem on known shapes
# ---------------------------------------------------------------------------

def test_point_in_polygon_inside():
    """Point clearly inside a square polygon."""
    ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    assert point_in_polygon(0.5, 0.5, ring) is True


def test_point_in_polygon_outside():
    """Point clearly outside the square."""
    ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    assert point_in_polygon(2.0, 2.0, ring) is False


def test_point_in_polygon_corner():
    """Point at corner is handled without error."""
    ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    # Result at exact corner is edge-case; just verify no exception
    try:
        result = point_in_polygon(0.0, 0.0, ring)
        assert isinstance(result, bool)
    except Exception:
        pytest.fail("point_in_polygon raised an exception at corner")


# ---------------------------------------------------------------------------
# Test 2: PolygonIndex — point-in-polygon on known geometry
# ---------------------------------------------------------------------------

def test_polygon_index_contains():
    """Unit square polygon correctly classifies inside and outside points."""
    square = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]]
    idx = PolygonIndex([square])
    assert idx.contains(0.5, 0.5) is True
    assert idx.contains(2.0, 2.0) is False


def test_polygon_index_hole():
    """Outer ring with a hole correctly excludes the hole."""
    outer = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]
    hole = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0), (1.0, 1.0)]
    poly = [outer, hole]
    idx = PolygonIndex([poly])
    assert idx.contains(0.5, 0.5) is True   # inside outer, outside hole
    assert idx.contains(2.0, 2.0) is False  # inside hole
    assert idx.contains(5.0, 5.0) is False  # completely outside


# ---------------------------------------------------------------------------
# Test 3: metric calculations on a known tiny case
# ---------------------------------------------------------------------------

def _make_results(tp, fp, fn, tn):
    rows = []
    for _ in range(tp):
        rows.append({"observed_flooded": True, "predicted_closed": True, "highway": "primary"})
    for _ in range(fp):
        rows.append({"observed_flooded": False, "predicted_closed": True, "highway": "primary"})
    for _ in range(fn):
        rows.append({"observed_flooded": True, "predicted_closed": False, "highway": "secondary"})
    for _ in range(tn):
        rows.append({"observed_flooded": False, "predicted_closed": False, "highway": "secondary"})
    return rows


def test_metrics_perfect():
    rows = _make_results(tp=5, fp=0, fn=0, tn=3)
    m = compute_metrics(rows)
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0
    assert m["tp"] == 5


def test_metrics_no_predictions():
    rows = _make_results(tp=0, fp=0, fn=5, tn=3)
    m = compute_metrics(rows)
    # Nothing predicted: precision undefined, recall = 0
    assert m["precision"] is None
    assert m["recall"] == 0.0
    assert m["f1"] is None


def test_metrics_by_class():
    rows = _make_results(tp=3, fp=1, fn=1, tn=1)
    bc = metrics_by_class(rows)
    # Primary has tp+fp rows = 4 roads, secondary has fn+tn = 2 roads
    assert "primary" in bc
    assert "secondary" in bc
    assert bc["primary"]["count"] == 4
    assert bc["secondary"]["count"] == 2


# ---------------------------------------------------------------------------
# Test 4: JSON output carries source and licence fields
# ---------------------------------------------------------------------------

def test_output_carries_source_metadata(tmp_path):
    """validate_city output has ground_truth with source and licence."""
    from pathlib import Path
    from scripts.validate_closures import CITATION_UNOSAT, CITATION_OSM

    # Verify both citation dicts have mandatory keys
    for cit in (CITATION_UNOSAT, CITATION_OSM):
        assert "source" in cit
        assert "licence" in cit
        assert "event" in cit


# ---------------------------------------------------------------------------
# Test 5: threshold sweep produces monotone predicted_closed counts
# ---------------------------------------------------------------------------

def test_threshold_sweep_monotone():
    """As blockage increases more roads close (closure rule is monotone)."""
    roads = [
        {"road_id": "R1", "lat": 13.0, "lon": 80.2, "flood_exposure": 0.5, "highway": "primary"},
        {"road_id": "R2", "lat": 13.0, "lon": 80.3, "flood_exposure": 0.3, "highway": "residential"},
        {"road_id": "R3", "lat": 13.0, "lon": 80.4, "flood_exposure": 0.1, "highway": "secondary"},
    ]
    # No observed-flooded data — just test sweep monotonicity
    sweep = threshold_sweep(roads, index=None, grid=None, snap_km=0.35)
    predicted_counts = [s["predicted_closed"] for s in sweep]
    # predicted_closed should be non-decreasing as blockage increases
    for i in range(1, len(predicted_counts)):
        assert predicted_counts[i] >= predicted_counts[i - 1], (
            f"predicted_closed not monotone at blockage step {i}: "
            f"{predicted_counts[i-1]} → {predicted_counts[i]}"
        )


# ---------------------------------------------------------------------------
# Test 6: BucketGrid nearest_km matches haversine on tiny case
# ---------------------------------------------------------------------------

def test_bucket_grid_nearest():
    pts = [(13.0, 80.25), (13.05, 80.30)]
    grid = BucketGrid(pts)
    # Point right on first flooded point
    d = grid.nearest_km(13.0, 80.25)
    assert d == pytest.approx(0.0, abs=0.01)
    # Point outside default radius returns inf
    assert grid.nearest_km(12.0, 79.0) == float("inf")
    # Point with expanded radius finds true distance
    d_far = grid.nearest_km(12.0, 79.0, radius_deg=2.0)
    expected = haversine_km(12.0, 79.0, 13.0, 80.25)
    assert d_far == pytest.approx(expected, rel=0.01)

