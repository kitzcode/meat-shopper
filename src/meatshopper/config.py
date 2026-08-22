"""Load and lightly validate the owner's config.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class WatchItem:
    key: str
    label: str
    threshold_lb: float
    include: list[str] = field(default_factory=list)
    require_all: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    rule: dict = field(default_factory=dict)


@dataclass
class StoreCfg:
    id: str
    name: str
    tier: str = "A"
    source: str = "paste"
    enabled: bool = True


@dataclass
class Config:
    location_postal: str
    location_country: str
    location_label: str
    watchlist: list[WatchItem]
    stores: list[StoreCfg]
    site_title: str
    currency: str
    keep_weeks: int
    site_dir: str
    archive_dir: str
    raw: dict = field(default_factory=dict)

    @property
    def enabled_stores(self) -> list[StoreCfg]:
        return [s for s in self.stores if s.enabled]


def load_config(path: str | Path) -> Config:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    loc = data.get("location", {}) or {}
    out = data.get("output", {}) or {}

    watch = []
    for w in data.get("watchlist", []) or []:
        watch.append(WatchItem(
            key=w["key"],
            label=w["label"],
            threshold_lb=float(w["threshold_lb"]),
            include=[s.lower() for s in w.get("include", [])],
            require_all=[s.lower() for s in w.get("require_all", [])],
            exclude=[s.lower() for s in w.get("exclude", [])],
            rule=w.get("rule", {}) or {},
        ))

    stores = []
    for s in data.get("stores", []) or []:
        stores.append(StoreCfg(
            id=s["id"],
            name=s["name"],
            tier=str(s.get("tier", "A")),
            source=s.get("source", "paste"),
            enabled=bool(s.get("enabled", True)),
        ))

    if not watch:
        raise ValueError("config.yaml has no watchlist items")
    if not stores:
        raise ValueError("config.yaml has no stores")

    return Config(
        location_postal=str(loc.get("postal_code", "")),
        location_country=str(loc.get("country", "US")),
        location_label=str(loc.get("label", "") or ""),
        watchlist=watch,
        stores=stores,
        site_title=str(out.get("site_title", "Weekly Meat Deals")),
        currency=str(out.get("currency", "$")),
        keep_weeks=int(out.get("keep_weeks", 0)),
        site_dir=str(out.get("site_dir", "docs")),
        archive_dir=str(out.get("archive_dir", "archive")),
        raw=data,
    )
