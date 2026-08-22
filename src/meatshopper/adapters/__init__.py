"""Adapter registry. Map a store's `source` to an adapter class.

All current sources read the paste inbox; `fetch` adds one owner-initiated
fetch on top. A future compliant automated adapter would register here behind
the same StoreAdapter interface without touching the pipeline.
"""
from __future__ import annotations

from pathlib import Path

from ..config import StoreCfg
from .base import StoreAdapter, AdapterResult
from .paste import PasteAdapter
from .fetch import FetchAdapter

_REGISTRY = {
    "paste": PasteAdapter,
    "fetch": FetchAdapter,
}

# Sources we accept in config but which still fall back to paste behavior.
_ALIASES = {
    "unavailable": PasteAdapter,   # no automated path; paste is all there is
    "flipp": PasteAdapter,         # no compliant Flipp feed exists; paste only
}


def get_adapter(store: StoreCfg, inbox_root: Path) -> StoreAdapter:
    cls = _REGISTRY.get(store.source) or _ALIASES.get(store.source, PasteAdapter)
    return cls(store, inbox_root)


__all__ = ["StoreAdapter", "AdapterResult", "get_adapter",
           "PasteAdapter", "FetchAdapter"]
