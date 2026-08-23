"""Store-specific structured parsers for the opt-in `fetch` mode.

These parse deal data that a store embeds in its own page HTML (not an
undocumented internal API, not a Flipp endpoint). They are used only when the
owner has explicitly pointed a store at a URL via `source: fetch`. They are
best-effort and terms-gray: a store can change its markup at any time, at which
point the parser returns nothing and the store falls back to whatever was
pasted. Nothing here evades an anti-bot block; a store that returns 403 to a
plain fetch simply yields no deals.

Only stores whose page genuinely exposes clean, reliably-associated
{name, price, size} data get a parser here. Stores whose fetchable content is
not their real weekly meat ad (for example Aldi's print URL, which server-renders
only a small clearance rail) are deliberately NOT here; they stay paste-only.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from .models import RawDeal


def _next_data(html: str) -> Optional[dict]:
    """Return the parsed __NEXT_DATA__ JSON blob from a Next.js page, or None."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except (ValueError, TypeError):
        return None


def parse_fresh_market(html: str, store_id: str, store_name: str,
                       url: str) -> list[RawDeal]:
    """Parse The Fresh Market weekly features.

    Data lives in __NEXT_DATA__ under
    props.pageProps.weeklySpecialsContent -> {group} -> specialItemsCollection
    -> items[] -> {specialItemName, specialMarketingPrice, specialMarketingSavings,
                   promoBody, product{description, department}}.
    The price is on the item, not on product (product.price is null). Groups
    repeat the same featured items, so we dedupe by (name, price).
    """
    data = _next_data(html)
    if not data:
        return []
    try:
        wsc = data["props"]["pageProps"]["weeklySpecialsContent"]
    except (KeyError, TypeError):
        return []

    groups = list(wsc.values()) if isinstance(wsc, dict) else (wsc or [])
    deals: list[RawDeal] = []
    seen: set[tuple] = set()

    for g in groups:
        if not isinstance(g, dict):
            continue
        items = (g.get("specialItemsCollection") or {}).get("items") or []
        for it in items:
            if not isinstance(it, dict):
                continue
            prod = it.get("product") or {}
            name = (it.get("specialItemName") or prod.get("name") or "").strip()
            price = (it.get("specialMarketingPrice") or "").strip()
            if not name or not price:
                continue
            key = (name.lower(), price.lower())
            if key in seen:
                continue
            seen.add(key)

            size = (prod.get("description")
                    or prod.get("shortDescriptionForSpecials") or "").strip()
            promo = " ".join(x for x in (it.get("specialMarketingSavings"),
                                         it.get("promoBody")) if x).strip()
            cta = it.get("ctaUrl") or url

            deals.append(RawDeal(
                store_id=store_id, store_name=store_name,
                title=name,
                price_text=price,      # e.g. "$8.99 lb", "$6.49 ea"
                pack_text=size,        # e.g. "FRESH, FARM-RAISED, 3.5 LB AVG"
                promo_text=promo,      # e.g. "Save at least $5.00 lb"
                source_url=cta,
                source_kind="fetch",
                raw_line=f"{name} | {price} | {size} | {promo}",
            ))
    return deals


# store_id -> parser(html, store_id, store_name, url) -> [RawDeal]
SITE_PARSERS: dict[str, Callable[[str, str, str, str], list[RawDeal]]] = {
    "fresh_market": parse_fresh_market,
}
