"""The paste-fallback adapter: the compliant, always-available primary path.

Reads every supported file in inbox/<store_id>/ and turns it into RawDeal
candidates. This is a first-class path, not an afterthought: the 2026 source
investigation (see SOURCES.md) found no store offers a documented, terms-
compliant deal API, so paste is how every store is fed by default.
"""
from __future__ import annotations

from ..extract import (
    extract_file, ExtractionSkipped, TEXT_EXTS, JSON_EXTS, IMAGE_EXTS, PDF_EXTS,
)
from .base import StoreAdapter, AdapterResult

_SUPPORTED = TEXT_EXTS | JSON_EXTS | IMAGE_EXTS | PDF_EXTS


class PasteAdapter(StoreAdapter):
    def fetch(self) -> AdapterResult:
        result = AdapterResult()

        if not self.inbox_dir.exists():
            result.note = f"no inbox folder ({self.inbox_dir}); nothing pasted"
            return result

        files = sorted(
            p for p in self.inbox_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _SUPPORTED
            and not p.name.startswith(".") and p.name != "source.url"
        )
        if not files:
            result.note = "inbox empty; drop a flyer .txt/.json/.png/.pdf here"
            return result

        read, skipped = [], []
        for f in files:
            try:
                deals = extract_file(f, self.store.id, self.store.name)
                result.deals.extend(deals)
                read.append(f"{f.name} ({len(deals)})")
            except ExtractionSkipped as e:
                skipped.append(f"{f.name}: {e}")
            except Exception as e:  # never let one bad file break the store
                skipped.append(f"{f.name}: parse error: {e}")

        parts = []
        if read:
            parts.append("read " + ", ".join(read))
        if skipped:
            parts.append("skipped " + "; ".join(skipped))
            result.ok = bool(read)  # ok if at least something was read
        result.note = "; ".join(parts) or "no deals parsed"
        return result
