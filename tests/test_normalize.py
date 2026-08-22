"""Tests for the deterministic price-per-pound normalizer.

The most important assertions are the negative ones: when weight/unit is
unclear, the normalizer must NOT invent a $/lb.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meatshopper.models import RawDeal
from meatshopper.normalize import (
    normalize, parse_price, parse_weight_lb, parse_lean_pct,
    parse_promo_multiplier, is_per_lb_marker,
)


def rd(**kw):
    base = dict(store_id="s", store_name="S", title="", price_text="",
                pack_text="", promo_text="", raw_line="")
    base.update(kw)
    return RawDeal(**base)


# ---- price parsing ----

def test_price_per_lb():
    assert parse_price("$2.49/lb")["kind"] == "per_lb"
    assert parse_price("$2.49/lb")["price"] == 2.49
    assert parse_price("2.49 per lb")["price"] == 2.49


def test_price_multibuy():
    p = parse_price("2 for $5")
    assert p["kind"] == "multibuy"
    assert p["count"] == 2
    assert abs(p["price"] - 2.5) < 1e-9


def test_price_each_and_flat():
    assert parse_price("$4.99 each")["kind"] == "each"
    assert parse_price("$4.99")["kind"] == "flat"


def test_price_does_not_grab_percent():
    # "93% lean" must NOT be read as a $93 price (no $ prefix, not a cents decimal)
    assert parse_price("93% lean")["price"] is None
    assert parse_lean_pct("93% lean") == 93


def test_price_does_not_grab_weight_integer():
    # free-text: the "16" in "16 oz" must not become a $16 price
    p = parse_price("chicken thighs 16 oz $4.99")
    assert p["price"] == 4.99
    # and with no real price, a bare weight integer yields no price
    assert parse_price("chicken thighs 16 oz")["price"] is None


# ---- weight parsing ----

def test_weight_oz_and_lb():
    assert abs(parse_weight_lb("16 oz") - 1.0) < 1e-9
    assert abs(parse_weight_lb("1.5 lb") - 1.5) < 1e-9
    assert abs(parse_weight_lb("24-oz") - 1.5) < 1e-9


def test_weight_none_for_count_or_vague():
    assert parse_weight_lb("family pack") is None
    assert parse_weight_lb("10 ct") is None
    assert parse_weight_lb("each") is None


# ---- lean parsing ----

def test_lean():
    assert parse_lean_pct("93% lean") == 93
    assert parse_lean_pct("80/20 blend") == 80
    assert parse_lean_pct("boneless chicken") is None


# ---- promo parsing ----

def test_bogo():
    assert abs(parse_promo_multiplier("BOGO")["factor"] - 0.5) < 1e-9


def test_buy2get1():
    f = parse_promo_multiplier("buy 2 get 1 free")["factor"]
    assert abs(f - (2 / 3)) < 1e-9


def test_pct_off():
    assert abs(parse_promo_multiplier("20% off")["factor"] - 0.8) < 1e-9


def test_promo_unclear():
    assert parse_promo_multiplier("$5 off with coupon")["unclear"] is True


# ---- end-to-end normalize: confident cases ----

def test_normalize_per_lb():
    n = normalize(rd(title="Chicken thighs", price_text="$2.49/lb"))
    assert n.confident
    assert n.price_per_lb == 2.49


def test_normalize_package_with_weight():
    n = normalize(rd(title="Chicken breast", price_text="$4.99", pack_text="16 oz"))
    assert n.confident
    assert n.price_per_lb == 4.99  # $4.99 / 1 lb


def test_normalize_multibuy_with_weight():
    # 2 for $6, each package 1 lb -> $3.00/lb
    n = normalize(rd(title="Pork chops", price_text="2 for $6", pack_text="1 lb"))
    assert n.confident
    assert n.price_per_lb == 3.00


def test_normalize_bogo_per_lb():
    # $6/lb BOGO -> $3.00/lb
    n = normalize(rd(title="Salmon", price_text="$6.00/lb", promo_text="BOGO"))
    assert n.confident
    assert n.price_per_lb == 3.00


def test_normalize_dollars_off_buy_n():
    # $5 each, 1 lb pkg, $2 off when you buy 2 -> ($5*2-$2)/2 = $4 -> /1lb = $4/lb
    n = normalize(rd(title="Cod", price_text="$5.00 each", pack_text="1 lb",
                     promo_text="$2 off when you buy 2"))
    assert n.confident
    assert n.price_per_lb == 4.00


def test_weight_not_read_as_per_lb_price():
    # "1.5 lb" is a weight, not a $1.50/lb price
    assert parse_price("chicken 1.5 lb pkg")["kind"] != "per_lb"


def test_flat_price_with_weight_divides():
    # "$4.99" flat + "1.5 lb pkg" -> 4.99/1.5 = 3.33/lb
    n = normalize(rd(title="Chicken breast", price_text="$4.99", pack_text="1.5 lb pkg"))
    assert n.confident
    assert n.price_per_lb == 3.33


def test_split_price_and_per_lb_marker():
    # price "$2.99" + pack "per lb" -> $2.99/lb
    assert is_per_lb_marker("per lb") is True
    assert is_per_lb_marker("1.5 lb") is False
    n = normalize(rd(title="Pork loin roast", price_text="$2.99", pack_text="per lb"))
    assert n.confident
    assert n.price_per_lb == 2.99


def test_weight_not_double_counted_from_raw_line():
    # raw_line repeats pack_text (as in JSON input); weight must stay 1 lb, not 2
    n = normalize(rd(title="Ground Beef 93% Lean", price_text="$5.49",
                     pack_text="1 lb pkg",
                     raw_line='{"price_text":"$5.49","pack_text":"1 lb pkg"}'))
    assert n.confident
    assert n.weight_lb == 1.0
    assert n.price_per_lb == 5.49


def test_weight_not_double_counted_free_text():
    # free text: title == raw_line, both contain "32 oz"; must be 2 lb not 4 lb
    line = "Atlantic Salmon Portions 32 oz $13.97"
    n = normalize(rd(title=line, raw_line=line))
    assert n.confident
    assert n.weight_lb == 2.0
    assert n.price_per_lb == 6.99  # 13.97 / 2


# ---- end-to-end normalize: the anti-fabrication (review) cases ----

def test_review_each_no_weight():
    n = normalize(rd(title="Chicken thighs", price_text="$4.99 each"))
    assert not n.confident
    assert n.price_per_lb is None
    assert "unit unclear" in n.review_reason


def test_review_flat_no_weight():
    n = normalize(rd(title="Whole chicken", price_text="$5.00"))
    assert not n.confident
    assert n.price_per_lb is None


def test_review_no_price():
    n = normalize(rd(title="Salmon fillet", pack_text="1 lb"))
    assert not n.confident
    assert n.price_per_lb is None


def test_review_unclear_promo():
    n = normalize(rd(title="Sirloin", price_text="$8.99/lb",
                     promo_text="$5 off with coupon"))
    assert not n.confident
    assert "unclear" in n.review_reason


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
