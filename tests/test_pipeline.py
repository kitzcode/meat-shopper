"""End-to-end pipeline test against the shipped sample inbox.

Confirms the pieces fit together and, crucially, that the anti-fabrication and
matching rules hold on realistic input.
"""
import os
import sys
from pathlib import Path

# Keep this test offline and deterministic: fetch-mode stores behave as paste.
os.environ["MEATSHOPPER_OFFLINE"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meatshopper.build import run


def _find_group(result, key):
    return next(g for g in result.groups if g.key == key)


def main():
    result, cfg = run(str(ROOT / "config" / "config.yaml"), str(ROOT / "inbox"),
                      week_date="2026-08-22")

    # Every store adapter ran and reported (none crashed the build).
    assert len(result.store_statuses) == 6
    assert {s.store_id for s in result.store_statuses} == {
        "shoprite", "stop_and_shop", "big_y", "aldi", "walmart", "fresh_market"}

    # No qualifying deal ever lacks a computed per-pound price (anti-fabrication).
    for g in result.groups:
        for md in g.qualifying:
            assert md.normalized.confident
            assert md.normalized.price_per_lb is not None
            assert md.normalized.price_per_lb <= g.threshold_lb + 1e-9

    # Qualifying deals are sorted cheapest-first and best == cheapest.
    for g in result.groups:
        ppls = [d.normalized.price_per_lb for d in g.qualifying]
        assert ppls == sorted(ppls)
        if g.qualifying:
            assert g.best is g.qualifying[0]

    # Leanness gate: an 80% lean ground beef must NOT appear as a beef match.
    beef = _find_group(result, "ground_beef_93")
    for md in beef.qualifying + beef.over_threshold:
        assert (md.normalized.lean_pct or 0) >= 93

    # The "$4.99 each" chicken breast (no weight) is flagged for review, unranked.
    review_reasons = [(m.item_key, m.review_reason) for m in result.review_items]
    assert any(k == "chicken_breast_bnsl_sknls" and "unit unclear" in (r or "")
               for k, r in review_reasons)

    # Salmon 32oz/$13.97 normalizes to 6.99/lb (weight not double-counted).
    salmon = _find_group(result, "salmon")
    wal = [d for d in salmon.qualifying if d.normalized.raw.store_id == "walmart"]
    assert wal and wal[0].normalized.price_per_lb == 6.99

    # Fresh Market has no pasted data -> reports empty but ok, does not crash.
    fm = next(s for s in result.store_statuses if s.store_id == "fresh_market")
    assert fm.deal_count == 0

    print("pipeline test: all assertions passed")


if __name__ == "__main__":
    try:
        main()
    except AssertionError:
        import traceback
        traceback.print_exc()
        sys.exit(1)
