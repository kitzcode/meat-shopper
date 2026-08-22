"""Assign normalized deals to watch-list items with careful, non-greedy rules.

The matcher errs toward flagging for review rather than making a false claim.
Keyword matching alone is useless (it catches seasoning, soup, pet food), so
each item carries include / require_all / exclude phrase sets plus optional
special rules for the tricky cases:

  * min_lean       ground beef only counts if stated lean% >= threshold;
                   if lean% is not stated -> review, never assumed.
  * prefer_plain_cut  fish that looks prepared/breaded -> review, not ranked.
  * exact_cut      steak must be the named cut, not another beef cut.
"""
from __future__ import annotations

from typing import Optional

from .config import WatchItem
from .models import NormalizedDeal, MatchedDeal

# Words that suggest a prepared/value-added product for fish (prefer_plain_cut).
# The clear cases (breaded, battered, cake, smoked) are usually excluded in
# config; these catch the ambiguous ones so they land in review, not ranked.
_PREPARED_HINTS = (
    "stuffed", "topped", "crusted", "encrusted", "kit", "meal", "entree",
    "entrée", "marinated", "teriyaki", "florentine", "wellington", "en croute",
    "seasoned", "rub", "glazed", "prepared", "oven ready", "oven-ready",
)


def _phrase_in(text: str, phrase: str) -> bool:
    return phrase in text


def _item_matches_text(item: WatchItem, text: str) -> bool:
    """True if the text is a candidate for this item (include/require/exclude)."""
    if not any(_phrase_in(text, p) for p in item.include):
        return False
    if item.require_all and not all(_phrase_in(text, p) for p in item.require_all):
        return False
    if any(_phrase_in(text, p) for p in item.exclude):
        return False
    return True


def _apply_rules(item: WatchItem, nd: NormalizedDeal, text: str
                 ) -> tuple[bool, Optional[str]]:
    """Apply item special rules.

    Returns (keep, review_reason). If keep is False the deal is dropped for this
    item entirely (it is not that product). If review_reason is set, the deal is
    kept but must go to the review section rather than the ranked list.
    """
    rule = item.rule or {}

    # Ground beef leanness gate.
    if "min_lean" in rule:
        need = int(rule["min_lean"])
        if nd.lean_pct is None:
            return True, f"lean % not stated (need {need}%+)"
        if nd.lean_pct < need:
            return False, None  # e.g. 80% lean is simply not this item

    # Fish: demote anything that looks prepared/value-added.
    if rule.get("prefer_plain_cut"):
        if any(h in text for h in _PREPARED_HINTS):
            return True, "may be prepared/value-added, verify it is a plain cut"

    # Steak: must be the exact named cut.
    if "exact_cut" in rule:
        toks = [t.lower() for t in rule["exact_cut"]]
        if not any(t in text for t in toks):
            return True, "cut ambiguous, verify it is the named cut"

    return True, None


def match_deal(nd: NormalizedDeal, watchlist: list[WatchItem]) -> list[MatchedDeal]:
    """Return a MatchedDeal for every watch item this deal legitimately matches.

    Usually a deal matches zero or one item. Excludes keep cross-matches out
    (e.g. "ground sirloin" matches ground beef, not sirloin steak).
    """
    text = nd.raw.search_text()
    results: list[MatchedDeal] = []

    for item in watchlist:
        if not _item_matches_text(item, text):
            continue

        keep, rule_review = _apply_rules(item, nd, text)
        if not keep:
            continue

        md = MatchedDeal(
            normalized=nd,
            item_key=item.key,
            item_label=item.label,
            threshold_lb=item.threshold_lb,
        )

        # Decide status. Review wins over ranking whenever anything is unsure.
        if not nd.confident:
            md.status = "review"
            md.review_reason = nd.review_reason
        elif rule_review is not None:
            md.status = "review"
            md.review_reason = rule_review
        elif nd.price_per_lb is not None and nd.price_per_lb <= item.threshold_lb:
            md.status = "qualifying"
        else:
            md.status = "over"

        results.append(md)

    return results
