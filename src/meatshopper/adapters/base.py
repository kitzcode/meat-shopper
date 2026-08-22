"""Common adapter interface.

An adapter's one job is to return RawDeal candidates for a store. It must
degrade gracefully: a flaky source, a missing folder, or an unreadable file
returns an AdapterResult with ok/notes, never an exception that could take down
the whole digest. Every store gets an adapter; automated paths can be added
later behind this same interface without touching the pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..config import StoreCfg
from ..models import RawDeal


@dataclass
class AdapterResult:
    deals: list[RawDeal] = field(default_factory=list)
    ok: bool = True
    note: str = ""


class StoreAdapter(ABC):
    """Base class for all store adapters."""

    def __init__(self, store: StoreCfg, inbox_root: Path):
        self.store = store
        self.inbox_dir = Path(inbox_root) / store.id

    @abstractmethod
    def fetch(self) -> AdapterResult:
        """Return candidate deals for this store. Must not raise."""
        raise NotImplementedError
