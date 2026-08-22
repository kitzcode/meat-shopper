"""Build the weekly digest: run adapters, normalize, match, rank, publish.

Usage:
    python -m meatshopper.build [--config config/config.yaml] [--inbox inbox]
                                [--date YYYY-MM-DD]

One flaky store never breaks the digest: adapter failures are caught and shown
in the "stores this week" section. Every per-pound figure is computed from
parsed values; ambiguous items land in the review section, never invented.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config, Config
from .adapters import get_adapter
from .normalize import normalize
from .match import match_deal
from .rank import build_groups
from .digest import render_markdown, render_html
from .models import DigestResult, StoreStatus


def run(config_path: str, inbox_dir: str, week_date: str | None = None
        ) -> tuple[DigestResult, Config]:
    cfg = load_config(config_path)
    inbox_root = Path(inbox_dir)

    now = datetime.now(timezone.utc)
    week_label = week_date or now.strftime("%Y-%m-%d")
    generated_at = now.strftime("%Y-%m-%d %H:%M UTC")

    all_matches = []
    statuses: list[StoreStatus] = []

    for store in cfg.enabled_stores:
        adapter = get_adapter(store, inbox_root)
        try:
            res = adapter.fetch()
        except Exception as e:  # belt-and-suspenders; adapters shouldn't raise
            statuses.append(StoreStatus(store.id, store.name, ok=False,
                                        deal_count=0, note=f"adapter error: {e}"))
            continue

        matched_here = 0
        for raw in res.deals:
            nd = normalize(raw)
            for md in match_deal(nd, cfg.watchlist):
                all_matches.append(md)
                matched_here += 1

        statuses.append(StoreStatus(
            store.id, store.name, ok=res.ok,
            deal_count=len(res.deals), note=res.note,
        ))

    groups, review = build_groups(all_matches, cfg.watchlist)

    result = DigestResult(
        week_label=week_label,
        location_label=cfg.location_label or cfg.location_postal,
        groups=groups,
        review_items=review,
        store_statuses=statuses,
        generated_at=generated_at,
    )
    return result, cfg


def _write_archive_index(cfg: Config, site_dir: Path) -> None:
    """Build archive.html listing every week snapshot we have kept."""
    archive_dir = Path(cfg.archive_dir)
    weeks = []
    if archive_dir.exists():
        for jf in sorted(archive_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            n = sum(len(g.get("qualifying", [])) for g in data.get("groups", []))
            weeks.append((data.get("week_label", jf.stem), n))

    rows = "".join(
        f'<li><a href="weeks/{wl}.html">Week of {wl}</a> '
        f'<span class="c">{n} deal(s)</span></li>'
        for wl, n in weeks
    ) or "<li>No archived weeks yet.</li>"

    from .digest import _CSS  # reuse the page styles
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{cfg.site_title} - all weeks</title><style>{_CSS}
.arch li{{list-style:none;padding:10px 12px;border-bottom:1px solid var(--line)}}
.arch{{padding:0;margin:0}} .arch .c{{color:var(--muted);font-size:.82rem}}</style>
</head><body><main>
<header class="top"><h1>{cfg.site_title}</h1>
<p class="sub">All weeks</p>
<p class="meta"><a href="index.html">back to latest</a></p></header>
<section class="block"><ul class="arch">{rows}</ul></section>
</main></body></html>
"""
    (site_dir / "archive.html").write_text(html, encoding="utf-8")


def publish(result: DigestResult, cfg: Config) -> dict:
    site_dir = Path(cfg.site_dir)
    weeks_dir = site_dir / "weeks"
    archive_dir = Path(cfg.archive_dir)
    for d in (site_dir, weeks_dir, archive_dir):
        d.mkdir(parents=True, exist_ok=True)

    md = render_markdown(result, cfg)
    html = render_html(result, cfg)
    wl = result.week_label

    # site: latest + per-week
    (site_dir / "index.html").write_text(html, encoding="utf-8")
    (weeks_dir / f"{wl}.html").write_text(html, encoding="utf-8")

    # archive: markdown + json snapshot
    (archive_dir / f"{wl}.md").write_text(md, encoding="utf-8")
    (archive_dir / f"{wl}.json").write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    # optional pruning of old weeks
    if cfg.keep_weeks and cfg.keep_weeks > 0:
        _prune(cfg, site_dir, weeks_dir, archive_dir)

    _write_archive_index(cfg, site_dir)

    return {
        "index": str(site_dir / "index.html"),
        "week_html": str(weeks_dir / f"{wl}.html"),
        "archive_md": str(archive_dir / f"{wl}.md"),
        "archive_json": str(archive_dir / f"{wl}.json"),
    }


def _prune(cfg: Config, site_dir: Path, weeks_dir: Path, archive_dir: Path) -> None:
    keep = cfg.keep_weeks
    snaps = sorted(archive_dir.glob("*.json"), key=lambda p: p.stem, reverse=True)
    for old in snaps[keep:]:
        stem = old.stem
        for p in (old, archive_dir / f"{stem}.md", weeks_dir / f"{stem}.html"):
            p.unlink(missing_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the weekly meat-deal digest.")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--inbox", default="inbox")
    ap.add_argument("--date", default=None, help="override week label (YYYY-MM-DD)")
    args = ap.parse_args(argv)

    result, cfg = run(args.config, args.inbox, args.date)
    out = publish(result, cfg)

    n_deals = sum(len(g.qualifying) for g in result.groups)
    n_review = len(result.review_items)
    ok_stores = sum(1 for s in result.store_statuses if s.ok)
    print(f"Built digest for week {result.week_label}")
    print(f"  {n_deals} qualifying deal(s), {n_review} review item(s), "
          f"{ok_stores}/{len(result.store_statuses)} stores reporting")
    print(f"  site: {out['index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
