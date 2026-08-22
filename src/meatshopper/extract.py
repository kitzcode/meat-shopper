"""Turn paste-fallback inputs into RawDeal candidates.

Supported inputs (dropped into inbox/<store_id>/):

  *.txt / *.md   One deal per line, free text, e.g.
                    Boneless Skinless Chicken Thighs family pack $2.49/lb
                 Optional pipe format for precision:
                    title | price | pack | promo | url | valid_from | valid_to
                 Directive/comment lines start with '#':
                    # valid: 2026-08-20..2026-08-26   (default dates below)
                    # url: https://store.example/flyer  (default source link)
                 Blank lines and other '#' lines are ignored.

  *.json         A list of deal objects, or {"deals": [...], "valid_from": ...,
                 "valid_to": ..., "source_url": ...} with per-deal overrides.
                 Keys: title, price_text, pack_text, promo_text, source_url,
                 valid_from, valid_to. This is the most precise path.

  *.png/.jpg/.jpeg/.pdf
                 OCR'd via Tesseract IF the optional deps are installed, then
                 parsed like a .txt. If the deps/binaries are missing we say so
                 clearly and skip the file. We never guess prices from a blurry
                 scan; the parser flags anything it cannot read confidently.

The parser only produces RawDeal candidates. All price-per-pound reasoning and
the anti-fabrication rule live in normalize.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .models import RawDeal

_URL_RE = re.compile(r"https?://\S+")
# "valid 8/20-8/26", "8/20/2026 - 8/26/2026", "2026-08-20..2026-08-26"
_DATE_RANGE_RE = re.compile(
    r"(\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,4})?)\s*(?:\.\.|-|to|through|–|—)\s*"
    r"(\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,4})?)",
    re.I,
)

TEXT_EXTS = {".txt", ".md"}
JSON_EXTS = {".json"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
PDF_EXTS = {".pdf"}


class ExtractionSkipped(Exception):
    """Raised when a file cannot be processed (e.g. OCR deps missing)."""


def _mk(store_id, store_name, source_kind, **kw) -> RawDeal:
    base = dict(store_id=store_id, store_name=store_name, source_kind=source_kind)
    base.update(kw)
    return RawDeal(**base)


def parse_text(text: str, store_id: str, store_name: str,
               source_kind: str = "paste") -> list[RawDeal]:
    """Parse a block of text into RawDeal candidates."""
    deals: list[RawDeal] = []
    default_url = ""
    default_from = ""
    default_to = ""

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue

        if s.startswith("#"):
            body = s.lstrip("#").strip()
            low = body.lower()
            if low.startswith("valid:") or low.startswith("dates:"):
                m = _DATE_RANGE_RE.search(body)
                if m:
                    default_from, default_to = m.group(1), m.group(2)
            elif low.startswith("url:") or low.startswith("source:"):
                m = _URL_RE.search(body)
                if m:
                    default_url = m.group(0)
            continue  # all '#' lines are directives/comments, never deals

        deals.append(_parse_line(s, store_id, store_name, source_kind,
                                 default_url, default_from, default_to))
    return deals


def _parse_line(line: str, store_id: str, store_name: str, source_kind: str,
                default_url: str, default_from: str, default_to: str) -> RawDeal:
    url = default_url
    vfrom, vto = default_from, default_to

    # pull a URL out of the line if present
    m = _URL_RE.search(line)
    if m:
        url = m.group(0)

    # pull a date range out of the line if present
    m = _DATE_RANGE_RE.search(line)
    if m:
        vfrom, vto = m.group(1), m.group(2)

    if " | " in line:
        # explicit pipe format
        parts = [p.strip() for p in line.split("|")]
        parts += [""] * (7 - len(parts))
        title, price, pack, promo, u, vf, vt = parts[:7]
        return _mk(store_id, store_name, source_kind,
                   title=title or line,
                   price_text=price,
                   pack_text=pack,
                   promo_text=promo,
                   source_url=(u or url),
                   valid_from=(vf or vfrom),
                   valid_to=(vt or vto),
                   raw_line=line)

    # free text: hand the whole line to the parsers via title + raw_line
    return _mk(store_id, store_name, source_kind,
               title=line,
               source_url=url,
               valid_from=vfrom,
               valid_to=vto,
               raw_line=line)


def parse_json(data, store_id: str, store_name: str,
               source_kind: str = "paste-json") -> list[RawDeal]:
    """Parse JSON deal data into RawDeal candidates."""
    if isinstance(data, dict) and "deals" in data:
        items = data.get("deals", [])
        d_url = data.get("source_url", "")
        d_from = data.get("valid_from", "")
        d_to = data.get("valid_to", "")
    elif isinstance(data, list):
        items = data
        d_url = d_from = d_to = ""
    else:
        raise ExtractionSkipped("JSON must be a list of deals or an object with 'deals'")

    out: list[RawDeal] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        if not title:
            continue
        out.append(_mk(
            store_id, store_name, source_kind,
            title=title,
            price_text=str(it.get("price_text", "")),
            pack_text=str(it.get("pack_text", "")),
            promo_text=str(it.get("promo_text", "")),
            source_url=str(it.get("source_url", d_url)),
            valid_from=str(it.get("valid_from", d_from)),
            valid_to=str(it.get("valid_to", d_to)),
            raw_line=json.dumps(it, ensure_ascii=False),
        ))
    return out


# ---------------------------------------------------------------------------
# Optional OCR (image / PDF). Degrades gracefully if deps are missing.
# ---------------------------------------------------------------------------

def ocr_available() -> tuple[bool, str]:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False, "pytesseract/Pillow not installed (pip install -r requirements-ocr.txt)"
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception:
        return False, "Tesseract binary not found (brew install tesseract)"
    return True, ""


def ocr_image_file(path: Path) -> str:
    ok, why = ocr_available()
    if not ok:
        raise ExtractionSkipped(why)
    import pytesseract
    from PIL import Image
    with Image.open(path) as img:
        return pytesseract.image_to_string(img)


def ocr_pdf_file(path: Path) -> str:
    ok, why = ocr_available()
    if not ok:
        raise ExtractionSkipped(why)
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ExtractionSkipped("pdf2image not installed (pip install -r requirements-ocr.txt)")
    import pytesseract
    try:
        pages = convert_from_path(str(path))
    except Exception as e:
        raise ExtractionSkipped(f"could not render PDF (need Poppler? brew install poppler): {e}")
    return "\n".join(pytesseract.image_to_string(p) for p in pages)


def extract_file(path: Path, store_id: str, store_name: str) -> list[RawDeal]:
    """Dispatch one inbox file to the right parser. Raises ExtractionSkipped
    if the file type needs unavailable OCR deps."""
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return parse_text(path.read_text(encoding="utf-8", errors="replace"),
                          store_id, store_name, "paste")
    if ext in JSON_EXTS:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return parse_json(data, store_id, store_name, "paste-json")
    if ext in IMAGE_EXTS:
        text = ocr_image_file(path)
        return parse_text(text, store_id, store_name, "paste-ocr")
    if ext in PDF_EXTS:
        text = ocr_pdf_file(path)
        return parse_text(text, store_id, store_name, "paste-ocr")
    raise ExtractionSkipped(f"unsupported file type: {ext}")
