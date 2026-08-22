"""Data structures passed between pipeline stages.

Everything is a plain dataclass so the whole pipeline stays inspectable and
easy to serialize into the weekly JSON archive.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class RawDeal:
    """A candidate deal as an adapter found it, before any normalization.

    Adapters should fill in as much as the source plainly states and leave the
    rest as None/"". The normalizer decides what can be computed confidently.
    """
    store_id: str
    store_name: str
    title: str                       # the deal text as printed, e.g.
                                     # "Boneless Skinless Chicken Thighs, family pack"
    price_text: str = ""             # the price as printed, e.g. "$2.49/lb", "2/$5"
    pack_text: str = ""              # size/pack as printed, e.g. "16 oz", "per lb"
    promo_text: str = ""             # promo as printed, e.g. "BOGO", "$1 off"
    source_url: str = ""             # link back to flyer page / store page
    valid_from: str = ""             # ISO date string if known
    valid_to: str = ""               # ISO date string if known
    source_kind: str = ""            # "paste", "flipp", "paste-ocr", etc.
    raw_line: str = ""               # the original unparsed text, for auditing

    def search_text(self) -> str:
        """All text an adapter captured, lowercased, for matching."""
        return " ".join(
            t for t in (self.title, self.pack_text, self.promo_text, self.raw_line)
            if t
        ).lower()


@dataclass
class NormalizedDeal:
    """A RawDeal after the normalizer ran.

    Exactly one of these is true:
      * confident is True  -> price_per_lb is a real, computed number.
      * confident is False -> price_per_lb is None and review_reason explains why.
    """
    raw: RawDeal
    price_per_lb: Optional[float] = None
    unit_price: Optional[float] = None      # effective price for the sold unit
    weight_lb: Optional[float] = None       # parsed weight in pounds, if any
    basis: str = ""                         # human-readable "how we got here"
    confident: bool = False
    review_reason: Optional[str] = None     # set iff not confident

    # Parsed lean percentage for ground beef ("93% lean" -> 93). None if absent.
    lean_pct: Optional[int] = None


@dataclass
class MatchedDeal:
    """A normalized deal assigned to a watch-list item (or flagged for review)."""
    normalized: NormalizedDeal
    item_key: str                    # which watch-list item this belongs to
    item_label: str
    threshold_lb: float
    # "qualifying"  -> confident AND at/below threshold (goes in ranked list)
    # "over"        -> confident but above threshold (kept, shown as context)
    # "review"      -> not rankable (unit unclear, lean unknown, ambiguous cut)
    status: str = "review"
    review_reason: Optional[str] = None


@dataclass
class ItemGroup:
    """All deals for one watch-list item, ready for the digest."""
    key: str
    label: str
    threshold_lb: float
    qualifying: list = field(default_factory=list)   # MatchedDeal, cheapest first
    over_threshold: list = field(default_factory=list)
    best: Optional[MatchedDeal] = None               # cheapest qualifying deal


@dataclass
class StoreStatus:
    """Result of running one store's adapter this week."""
    store_id: str
    store_name: str
    ok: bool
    deal_count: int = 0
    note: str = ""                   # why unavailable, or how data was sourced


@dataclass
class DigestResult:
    """The full assembled digest for one week."""
    week_label: str                  # e.g. "2026-08-22" (build date)
    location_label: str
    groups: list = field(default_factory=list)       # ItemGroup
    review_items: list = field(default_factory=list) # MatchedDeal (review status)
    store_statuses: list = field(default_factory=list)  # StoreStatus
    generated_at: str = ""           # ISO timestamp

    def to_dict(self) -> dict:
        return asdict(self)
