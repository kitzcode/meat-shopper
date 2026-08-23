"""Offline test for the Fresh Market structured site parser.

Uses a small synthetic __NEXT_DATA__ document with the same shape as the live
page (verified 2026-08-23), so parser logic is covered without a network call.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meatshopper.sites import parse_fresh_market
from meatshopper.normalize import normalize
from meatshopper.match import match_deal
from meatshopper.config import load_config

ROOT = Path(__file__).resolve().parents[1]

# Minimal document mirroring the real structure: weeklySpecialsContent is a dict
# of groups; each group's specialItemsCollection.items[] carry the price on the
# ITEM (product.price is null). Two groups repeat an item to exercise dedupe.
_NEXT = {
    "props": {"pageProps": {"weeklySpecialsContent": {
        "0": {"specialItemsCollection": {"items": [
            {"specialItemName": "Whole Atlantic Salmon Fillet",
             "specialMarketingPrice": "$8.99 lb",
             "specialMarketingSavings": "Save at least $5.00 lb",
             "product": {"name": "Whole Atlantic Salmon Fillet",
                         "description": "FRESH, FARM-RAISED, 3.5 LB AVG",
                         "department": "Seafood", "price": None}},
            {"specialItemName": "Lean Ground Sirloin",
             "specialMarketingPrice": "$6.99 lb",
             "specialMarketingSavings": "Save at least $3.00 lb",
             "product": {"name": "Lean Ground Sirloin",
                         "description": "GROUND FRESH DAILY",
                         "department": "Meat", "price": None}},
            {"specialItemName": "Broccoli Crowns",
             "specialMarketingPrice": "$2.49 lb",
             "product": {"name": "Broccoli Crowns", "description": "",
                         "department": "Produce", "price": None}},
        ]}},
        "1": {"specialItemsCollection": {"items": [
            {"specialItemName": "Whole Atlantic Salmon Fillet",   # duplicate
             "specialMarketingPrice": "$8.99 lb",
             "product": {"name": "Whole Atlantic Salmon Fillet",
                         "description": "FRESH, FARM-RAISED, 3.5 LB AVG",
                         "department": "Seafood", "price": None}},
        ]}},
    }}}
}

_HTML = ('<html><head><script id="__NEXT_DATA__" type="application/json">'
         + json.dumps(_NEXT) + '</script></head><body></body></html>')


def main():
    deals = parse_fresh_market(_HTML, "fresh_market", "The Fresh Market",
                               "https://www.thefreshmarket.com/features/weekly-features")

    # 3 unique deals (the duplicate salmon is deduped away).
    assert len(deals) == 3, [d.title for d in deals]
    titles = [d.title for d in deals]
    assert titles.count("Whole Atlantic Salmon Fillet") == 1

    # Salmon $8.99 lb -> qualifying at 8.99/lb.
    cfg = load_config(str(ROOT / "config" / "config.yaml"))
    by_status = {}
    for d in deals:
        for m in match_deal(normalize(d), cfg.watchlist):
            by_status.setdefault((m.item_key, m.status), []).append(m)

    salmon = by_status.get(("salmon", "qualifying"))
    assert salmon and salmon[0].normalized.price_per_lb == 8.99

    # "Lean Ground Sirloin" states no lean % -> ground beef match goes to review.
    assert ("ground_beef_93", "review") in by_status

    # A malformed / non-Next page yields nothing, never raises.
    assert parse_fresh_market("<html>no next data</html>", "fresh_market",
                              "The Fresh Market", "u") == []

    print("sites test: all assertions passed")


if __name__ == "__main__":
    try:
        main()
    except AssertionError:
        import traceback
        traceback.print_exc()
        sys.exit(1)
