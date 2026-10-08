"""Fail-closed dispatch: a high probability alone must never auto-call rescue teams."""

import pytest

from backend.services.decision_engine import evaluate_policy
from backend.services.dispatch import apply_threshold_dispatch, dispatch_permitted
from backend.thresholds import auto_threshold


def test_dispatch_rule_end_to_end_is_fail_closed():
    """Policy -> hold -> dispatch rule: dispatch implies healthy, agreeing models, or an operator override."""
    for i in range(101):
        p = i / 100
        for mask in range(8):
            ok = all((mask & 1, mask & 2, mask & 4))
            for hold in (False, True):
                for override in (False, True):
                    action = evaluate_policy(p, bool(mask & 1), bool(mask & 2), bool(mask & 4), human_override=override)["action"]
                    if hold and not override:
                        action = "HUMAN_REVIEW"
                    fired = dispatch_permitted(action, hold, override) and p >= auto_threshold()
                    if fired:
                        assert override or (ok and not hold)


@pytest.mark.asyncio
async def test_dispatch_held_when_policy_blocks_automation():
    out = await apply_threshold_dispatch(0.95, "simulation", allowed=False)
    assert out["called"] is False
    assert out["held"] is True
    assert out["teams"] == []


@pytest.mark.asyncio
async def test_dispatch_called_when_policy_allows():
    out = await apply_threshold_dispatch(0.95, "simulation", allowed=True)
    assert out["called"] is True
    assert out["teams"]


@pytest.mark.asyncio
async def test_no_dispatch_below_auto_band():
    out = await apply_threshold_dispatch(0.30, "simulation", allowed=True)
    assert out["called"] is False
