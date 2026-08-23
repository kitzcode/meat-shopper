"""Opt-in single-fetch adapter.

For a store whose config sets `source: fetch`, the owner puts ONE URL in
inbox/<store_id>/source.url pointing at a SPECIFIC public flyer artifact they
chose (a direct image, a PDF, or a simple deals page). We do a single, human-
initiated GET of exactly that document and run it through the same extractor.

This is deliberately narrow. It is NOT a crawler and must not be pointed at a
store's internal endpoints or an interactive Flipp flyer widget (canvas/JS,
unparseable and against terms). See SOURCES.md. Any paste files in the same
folder are also read, so fetch augments rather than replaces the paste path.
"""
from __future__ import annotations

import os
import ssl
import tempfile
import urllib.request
from pathlib import Path


def _ssl_context() -> ssl.SSLContext:
    """A verifying SSL context that works on macOS too.

    Python installers on macOS often ship without the system CA store wired up,
    which makes urllib raise CERTIFICATE_VERIFY_FAILED even though the fetch is
    fine. Use certifi's CA bundle when available; fall back to the default.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

from ..extract import extract_file, parse_text, ExtractionSkipped
from ..sites import SITE_PARSERS
from .paste import PasteAdapter
from .base import AdapterResult

_UA = "meat-shopper/1.0 (personal weekly deal digest; single manual fetch)"
_TIMEOUT = 20


def _strip_html(html: str) -> str:
    import re
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", "\n", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"[ \t]+", " ", html)
    return "\n".join(ln.strip() for ln in html.splitlines() if ln.strip())


class FetchAdapter(PasteAdapter):
    def fetch(self) -> AdapterResult:
        # Start from whatever is pasted in the folder.
        result = super().fetch()

        # Offline mode (tests, or a no-network run): behave as paste-only.
        if os.environ.get("MEATSHOPPER_OFFLINE"):
            note = "offline mode; skipped fetch, paste only"
            result.note = (result.note + "; " + note) if result.note else note
            return result

        url_file = self.inbox_dir / "source.url"
        if not url_file.exists():
            note = "no source.url to fetch; using paste only"
            result.note = (result.note + "; " + note) if result.note else note
            return result

        url = ""
        for line in url_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                url = line
                break
        if not url.lower().startswith(("http://", "https://")):
            result.note += "; source.url has no valid http(s) URL"
            return result

        try:
            fetched = self._fetch_url(url)
            result.deals.extend(fetched)
            result.note += f"; fetched {url} ({len(fetched)} candidates)"
            result.ok = result.ok or bool(fetched)
        except ExtractionSkipped as e:
            result.note += f"; fetch skipped: {e}"
        except Exception as e:
            result.note += f"; fetch failed: {e}"
        return result

    def _fetch_url(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        ctx = _ssl_context()
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:  # noqa: S310
            ctype = (resp.headers.get("Content-Type") or "").lower()
            body = resp.read()

        if "text/html" in ctype or "text/plain" in ctype:
            raw = body.decode("utf-8", errors="replace")

            # If this store has a structured site parser (e.g. Fresh Market's
            # embedded JSON), try it on the RAW html first. It gives clean
            # name/price/size tuples. Fall back to generic text extraction only
            # if it yields nothing (markup changed, or wrong page).
            parser = SITE_PARSERS.get(self.store.id)
            if parser and "text/html" in ctype:
                deals = parser(raw, self.store.id, self.store.name, url)
                if deals:
                    for d in deals:
                        d.source_url = d.source_url or url
                    return deals

            text = _strip_html(raw) if "text/html" in ctype else raw
            deals = parse_text(text, self.store.id, self.store.name, "fetch")
            for d in deals:
                d.source_url = d.source_url or url
            return deals

        # binary: image or pdf -> write to temp file and OCR via extract_file
        suffix = ".pdf" if "pdf" in ctype else ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(body)
            tmp = Path(tf.name)
        try:
            deals = extract_file(tmp, self.store.id, self.store.name)
            for d in deals:
                d.source_url = d.source_url or url
                d.source_kind = "fetch-ocr"
            return deals
        finally:
            tmp.unlink(missing_ok=True)
