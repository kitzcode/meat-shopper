"""Normalize a raw deal to an effective price per pound, or flag it for review.

This module is the deterministic core of the tool and the place the
anti-fabrication rule is enforced:

    A price-per-pound number is ONLY produced when it was computed from values
    actually parsed out of the source text. If the weight or unit cannot be
    determined confidently, we return NO number and set a review_reason. A
    flagged item is safe; a guessed $/lb could send someone driving for a deal
    that is not there.

The parsing is intentionally conservative. When a promo or unit is ambiguous,
we prefer to flag for review rather than pick an interpretation.
"""
from __future__ import annotations

import re
from typing import Optional

from .models import RawDeal, NormalizedDeal

OZ_PER_LB = 16.0


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

# A dollar amount like $2, $2.49, 2.49, .99 (we require a $ or a decimal to
# avoid grabbing stray integers like "93" from "93% lean").
_MONEY = r"\$?\s*(\d{1,3}(?:\.\d{1,2})?)"


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_price(text: str) -> dict:
    """Extract a base price and its 'shape' from printed price text.

    Returns a dict:
      kind:   "per_lb" | "each" | "multibuy" | "flat" | "unknown"
      price:  dollars for one unit (or per lb for per_lb)     -> float | None
      count:  N for a multibuy "N for $P"                     -> int  | None
    """
    t = (text or "").lower().strip()
    if not t:
        return {"kind": "unknown", "price": None, "count": None}

    # "2 for $5", "2/$5", "2 for 5.00"
    m = re.search(r"(\d+)\s*(?:for|/)\s*" + _MONEY, t)
    if m:
        count = int(m.group(1))
        total = _to_float(m.group(2))
        if count and total is not None and count > 0:
            return {"kind": "multibuy", "price": total / count, "count": count}

    # explicit per-pound PRICE. We require a real per-lb price signal so that a
    # bare weight like "1.5 lb" is NOT mistaken for a "$1.50/lb" price:
    #   * a $ prefix:      "$2.49/lb", "$2.49 lb"
    #   * or a connector:  "2.49/lb", "2.49 per lb"
    m = re.search(r"\$\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:/|per|a)?\s*(?:lb|lbs|pound|#)\b", t)
    if not m:
        m = re.search(r"(?<![\d.])(\d{1,3}(?:\.\d{1,2})?)\s*(?:/|per)\s*(?:lb|lbs|pound|#)\b", t)
    if m:
        p = _to_float(m.group(1))
        if p is not None:
            return {"kind": "per_lb", "price": p, "count": None}

    # explicit each: "$4.99 each", "$4.99/ea", "$4.99 ea"
    m = re.search(_MONEY + r"\s*(?:/|per)?\s*(?:each|ea)\b", t)
    if m:
        p = _to_float(m.group(1))
        if p is not None:
            return {"kind": "each", "price": p, "count": None}

    # a price of unknown shape (could be per pkg or per lb). To avoid grabbing
    # a stray integer like the "16" in "16 oz", require either a $ prefix or a
    # cents decimal (e.g. 4.99). A bare integer is NOT treated as a price.
    m = re.search(r"\$\s*(\d{1,3}(?:\.\d{1,2})?)", t)
    if not m:
        m = re.search(r"(?<![\d.])(\d{1,3}\.\d{2})(?!\d)", t)
    if m:
        p = _to_float(m.group(1))
        if p is not None:
            return {"kind": "flat", "price": p, "count": None}

    return {"kind": "unknown", "price": None, "count": None}


# ---------------------------------------------------------------------------
# Weight / unit parsing
# ---------------------------------------------------------------------------

def parse_weight_lb(text: str) -> Optional[float]:
    """Return a stated package weight in pounds, or None if not clearly stated.

    Handles "16 oz", "1.5 lb", "2 lbs", "24-oz", "1 lb 8 oz". Returns None for
    count units ("10 ct"), vague sizes ("family pack"), or nothing at all.
    """
    if not text:
        return None
    t = text.lower()

    total_lb = 0.0
    found = False

    # pounds: "1.5 lb", "2 lbs", "1 pound", "2-lb"
    for m in re.finditer(r"(\d+(?:\.\d+)?)[\s-]*(?:lb|lbs|pound|pounds|#)\b", t):
        total_lb += float(m.group(1))
        found = True

    # ounces: "16 oz", "24-oz"  (weight ounces; assume fluid oz not used for meat)
    for m in re.finditer(r"(\d+(?:\.\d+)?)[\s-]*(?:oz|ounce|ounces)\b", t):
        total_lb += float(m.group(1)) / OZ_PER_LB
        found = True

    return total_lb if (found and total_lb > 0) else None


def is_per_lb_marker(text: str) -> bool:
    """True if text states a per-pound unit but no numeric weight.

    Distinguishes "per lb" / "priced per pound" / "/lb" (a unit marker, so a
    flat price is actually per pound) from "1.5 lb" (a package weight).
    """
    if not text:
        return False
    t = text.lower()
    has_unit = bool(
        re.search(r"per\s*(?:lb|lbs|pound|pounds)", t)
        or re.search(r"/\s*(?:lb|lbs|pound|#)", t)
        or re.search(r"by the pound", t)
        or re.search(r"\b(?:lb|lbs|pound|pounds)\b", t)
    )
    return has_unit and parse_weight_lb(t) is None


def parse_lean_pct(text: str) -> Optional[int]:
    """Return a stated lean percentage for ground beef ("93% lean" -> 93)."""
    if not text:
        return None
    t = text.lower()
    # "93% lean", "93/7", "lean 93%"
    m = re.search(r"(\d{2,3})\s*%\s*lean", t)
    if m:
        return int(m.group(1))
    m = re.search(r"lean\s*(\d{2,3})\s*%", t)
    if m:
        return int(m.group(1))
    # "93/7" blend notation
    m = re.search(r"\b(8\d|9\d|100)\s*/\s*(?:\d{1,2})\b", t)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Promo parsing
# ---------------------------------------------------------------------------

def parse_promo_multiplier(text: str) -> dict:
    """Interpret a promo as a multiplier on the base per-unit price.

    Returns dict:
      factor:  multiply base unit price by this        -> float | None
      note:    description for the basis string
      unclear: True if a promo is present but ambiguous -> flag for review

    Only unambiguous, common promos are handled. Anything we cannot interpret
    confidently is reported as unclear rather than guessed.
    """
    t = (text or "").lower()
    if not t.strip():
        return {"factor": 1.0, "note": "", "unclear": False}

    # Buy N get M free / at X% off  ->  "buy 2 get 1 free"
    m = re.search(r"buy\s*(\d+)\s*get\s*(\d+)\s*(?:free|at\s*100%|100%\s*off)", t)
    if m:
        n, k = int(m.group(1)), int(m.group(2))
        if n > 0 and k >= 0:
            factor = n / (n + k)
            return {"factor": factor, "note": f"buy {n} get {k} free", "unclear": False}

    # Plain BOGO / "buy one get one free" -> half price
    if re.search(r"\bbogo\b", t) or re.search(r"buy\s*one\s*get\s*one\s*free", t):
        return {"factor": 0.5, "note": "BOGO (half price)", "unclear": False}

    # Buy N get M at 50% off -> partial
    m = re.search(r"buy\s*(\d+)\s*get\s*(\d+)\s*(?:at\s*)?50%\s*off", t)
    if m:
        n, k = int(m.group(1)), int(m.group(2))
        if n > 0:
            factor = (n + 0.5 * k) / (n + k)
            return {"factor": factor, "note": f"buy {n} get {k} 50% off", "unclear": False}

    # Percent off the item -> "20% off"
    m = re.search(r"(\d{1,2})\s*%\s*off", t)
    if m:
        pct = int(m.group(1))
        if 0 < pct < 100:
            return {"factor": 1 - pct / 100.0, "note": f"{pct}% off", "unclear": False}

    # "$X off when you buy N"  -> handled at the unit-price level, needs base
    m = re.search(r"\$?\s*(\d+(?:\.\d{1,2})?)\s*off.*?buy\s*(\d+)", t)
    if m:
        return {
            "factor": None,
            "note": f"${m.group(1)} off when you buy {m.group(2)}",
            "unclear": False,
            "dollars_off": float(m.group(1)),
            "buy_n": int(m.group(2)),
        }

    # Generic "$X off" with no clear quantity -> ambiguous, flag it
    if re.search(r"\$?\d+(?:\.\d{1,2})?\s*off", t) or "coupon" in t:
        return {"factor": None, "note": "promo unclear", "unclear": True}

    return {"factor": 1.0, "note": "", "unclear": False}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _review(raw: RawDeal, reason: str, lean: Optional[int] = None) -> NormalizedDeal:
    return NormalizedDeal(
        raw=raw, price_per_lb=None, confident=False, review_reason=reason,
        lean_pct=lean,
    )


def normalize(raw: RawDeal) -> NormalizedDeal:
    """Compute an effective $/lb for a raw deal, or flag it for review.

    Never returns a $/lb it did not compute from parsed values.
    """
    price_field = raw.price_text or raw.raw_line

    # Read weight and lean from the FIRST field that yields one, never summed
    # across fields. pack_text, title and raw_line often overlap (raw_line can
    # repeat pack_text/title verbatim), so concatenating them would double-count
    # a weight like "1 lb" into "2 lb" and halve the reported $/lb.
    weight_lb = (parse_weight_lb(raw.pack_text)
                 or parse_weight_lb(raw.title)
                 or parse_weight_lb(raw.raw_line))
    lean = (parse_lean_pct(raw.pack_text) or parse_lean_pct(raw.title)
            or parse_lean_pct(raw.raw_line) or parse_lean_pct(raw.price_text))

    price = parse_price(price_field)
    promo = parse_promo_multiplier(raw.promo_text or raw.raw_line)

    if price["price"] is None:
        return _review(raw, "no parseable price", lean)

    if promo.get("unclear"):
        return _review(raw, "promo unclear (raw price shown)", lean)

    base = price["price"]
    kind = price["kind"]
    basis_parts: list[str] = []

    # A flat price with a per-lb unit marker (and no numeric weight) is really a
    # per-pound price, e.g. price "$2.99" + pack "per lb".
    if kind == "flat" and weight_lb is None and (
        is_per_lb_marker(raw.pack_text) or is_per_lb_marker(raw.raw_line)
    ):
        kind = "per_lb"

    # ---- establish an effective per-pound figure by price shape ----
    per_lb: Optional[float] = None
    unit_price: Optional[float] = None

    if kind == "per_lb":
        # Already per pound. Promo multipliers still apply per pound.
        per_lb = base
        basis_parts.append(f"${base:.2f}/lb as printed")
    else:
        # "each"/"flat"/"multibuy" give a per-UNIT price; we need a weight to
        # convert to per-pound. Without a stated weight we cannot compute it.
        unit_price = base
        if kind == "multibuy":
            basis_parts.append(
                f"{price['count']} for ${base * price['count']:.2f} "
                f"= ${base:.2f} each"
            )
        elif kind == "each":
            basis_parts.append(f"${base:.2f} each")
        else:
            basis_parts.append(f"${base:.2f}")

        if weight_lb is None:
            # count/each with no weight -> the classic un-normalizable case
            return _review(raw, "unit unclear (no weight to convert to $/lb)", lean)

        per_lb = unit_price / weight_lb
        basis_parts.append(f"/ {weight_lb:.2f} lb pkg")

    # ---- apply promo ----
    factor = promo.get("factor")
    if "dollars_off" in promo:
        # "$X off when you buy N": reduce the effective unit/lb cost.
        d, n = promo["dollars_off"], promo["buy_n"]
        if kind == "per_lb":
            # Can't apply a per-purchase dollars-off to a per-lb price without
            # knowing pounds bought -> flag rather than guess.
            return _review(raw, "promo ($ off/buy N) not convertible to $/lb", lean)
        # unit-based: effective unit price over the required buy quantity
        eff_unit = (unit_price * n - d) / n
        if eff_unit <= 0 or weight_lb is None:
            return _review(raw, "promo yields non-positive or unweighted price", lean)
        per_lb = eff_unit / weight_lb
        basis_parts.append(promo["note"])
    elif factor is not None and factor != 1.0:
        per_lb = per_lb * factor
        basis_parts.append(promo["note"])

    if per_lb is None or per_lb <= 0:
        return _review(raw, "could not compute a positive $/lb", lean)

    return NormalizedDeal(
        raw=raw,
        price_per_lb=round(per_lb, 2),
        unit_price=round(unit_price, 2) if unit_price is not None else None,
        weight_lb=round(weight_lb, 2) if weight_lb is not None else None,
        basis=", ".join(p for p in basis_parts if p),
        confident=True,
        review_reason=None,
        lean_pct=lean,
    )
