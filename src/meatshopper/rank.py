"""Group matched deals by watch item, rank cheapest-first, split out review."""
from __future__ import annotations

from .config import WatchItem
from .models import MatchedDeal, ItemGroup


def build_groups(matches: list[MatchedDeal], watchlist: list[WatchItem]
                 ) -> tuple[list[ItemGroup], list[MatchedDeal]]:
    """Return (item_groups_in_watchlist_order, global_review_list).

    Within each group, qualifying deals are sorted by $/lb ascending and the
    cheapest is marked as `best`. Deals above threshold are kept as context.
    Anything flagged for review is pulled into the global review list so nothing
    is silently dropped.
    """
    by_key: dict[str, list[MatchedDeal]] = {}
    review: list[MatchedDeal] = []

    for m in matches:
        if m.status == "review":
            review.append(m)
        else:
            by_key.setdefault(m.item_key, []).append(m)

    groups: list[ItemGroup] = []
    for item in watchlist:
        deals = by_key.get(item.key, [])
        qualifying = sorted(
            [d for d in deals if d.status == "qualifying"],
            key=lambda d: d.normalized.price_per_lb,
        )
        over = sorted(
            [d for d in deals if d.status == "over"],
            key=lambda d: d.normalized.price_per_lb,
        )
        groups.append(ItemGroup(
            key=item.key,
            label=item.label,
            threshold_lb=item.threshold_lb,
            qualifying=qualifying,
            over_threshold=over,
            best=qualifying[0] if qualifying else None,
        ))

    # Stable, useful ordering for the review section: by item label then store.
    review.sort(key=lambda d: (d.item_label, d.normalized.raw.store_name))
    return groups, review
