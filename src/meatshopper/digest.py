"""Render a DigestResult to markdown and a self-contained HTML page.

House rule: no em dashes in the body/UI copy produced here. Use hyphens or
"to" instead. (Comments and code may use them; the generated digest may not.)
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .config import Config
from .models import DigestResult, ItemGroup, MatchedDeal


def _money(cur: str, v: float) -> str:
    return f"{cur}{v:.2f}"


def _dates(md: MatchedDeal) -> str:
    r = md.normalized.raw
    if r.valid_from and r.valid_to:
        return f"{r.valid_from} to {r.valid_to}"
    if r.valid_from:
        return f"from {r.valid_from}"
    return ""


def _raw_desc(md: MatchedDeal) -> str:
    """The as-printed price/pack, so the owner can eyeball the source claim."""
    r = md.normalized.raw
    bits = []
    if r.price_text:
        bits.append(r.price_text)
    if r.pack_text:
        bits.append(r.pack_text)
    if not bits:
        bits.append(r.title)
    if r.promo_text:
        bits.append(r.promo_text)
    return ", ".join(b for b in bits if b)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def render_markdown(d: DigestResult, cfg: Config) -> str:
    cur = cfg.currency
    L: list[str] = []
    L.append(f"# {cfg.site_title}")
    loc = f" for {d.location_label}" if d.location_label else ""
    L.append(f"\nWeek of {d.week_label}{loc}. Built {d.generated_at}.\n")
    L.append("All prices normalized to price per pound. Only items at or below "
             "your threshold are listed as deals; cheapest first.\n")

    n_deals = sum(len(g.qualifying) for g in d.groups)
    L.append(f"**{n_deals} qualifying deal(s)** across "
             f"{len([g for g in d.groups if g.qualifying])} item(s).\n")

    for g in d.groups:
        L.append(f"\n## {g.label}")
        L.append(f"\nThreshold: at or below {_money(cur, g.threshold_lb)}/lb\n")
        if not g.qualifying:
            L.append("_No qualifying deals this week._")
            if g.over_threshold:
                cheapest = g.over_threshold[0]
                L.append(f"(Cheapest seen was {_money(cur, cheapest.normalized.price_per_lb)}/lb "
                         f"at {cheapest.normalized.raw.store_name}, above threshold.)")
            continue
        for i, md in enumerate(g.qualifying):
            nd = md.normalized
            star = " ** BEST **" if (g.best is md) else ""
            line = (f"- **{_money(cur, nd.price_per_lb)}/lb** at "
                    f"{nd.raw.store_name}{star} - {_raw_desc(md)}")
            dates = _dates(md)
            if dates:
                line += f" ({dates})"
            if nd.raw.source_url:
                line += f" [source]({nd.raw.source_url})"
            L.append(line)
            if nd.basis:
                L.append(f"    - basis: {nd.basis}")

    # Review section
    L.append("\n## Review (not ranked, verify before you drive)")
    if not d.review_items:
        L.append("\n_Nothing needed review this week._")
    else:
        L.append("")
        for md in d.review_items:
            r = md.normalized.raw
            reason = md.review_reason or "needs review"
            line = (f"- **{md.item_label}** at {r.store_name}: {reason}. "
                    f"As printed: {_raw_desc(md)}")
            if r.source_url:
                line += f" [source]({r.source_url})"
            L.append(line)

    # Store status
    L.append("\n## Stores this week")
    L.append("")
    for s in d.store_statuses:
        mark = "ok" if s.ok else "unavailable"
        L.append(f"- **{s.store_name}**: {mark}, {s.deal_count} candidate(s). {s.note}")

    L.append("\n---\n")
    L.append("Prices are computed from pasted/sourced flyer text. Always confirm "
             "at the store. An item with an unclear unit or unstated lean percent "
             "is flagged for review, never given a guessed per-pound price.")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# HTML (self-contained, theme-aware)
# ---------------------------------------------------------------------------

def _h(s: str) -> str:
    return html.escape(str(s), quote=True)


def _deal_row_html(md: MatchedDeal, cur: str, is_best: bool) -> str:
    nd = md.normalized
    dates = _dates(md)
    src = (f'<a href="{_h(nd.raw.source_url)}" rel="nofollow noopener" '
           f'target="_blank">source</a>') if nd.raw.source_url else ""
    best = '<span class="best">best</span>' if is_best else ""
    return f"""
      <tr class="{'best-row' if is_best else ''}">
        <td class="ppl">{_h(_money(cur, nd.price_per_lb))}<span class="per">/lb</span> {best}</td>
        <td class="store">{_h(nd.raw.store_name)}</td>
        <td class="desc">{_h(_raw_desc(md))}<div class="basis">{_h(nd.basis)}</div></td>
        <td class="dates">{_h(dates)}</td>
        <td class="src">{src}</td>
      </tr>"""


def render_html(d: DigestResult, cfg: Config) -> str:
    cur = cfg.currency
    loc = f" &middot; {_h(d.location_label)}" if d.location_label else ""
    n_deals = sum(len(g.qualifying) for g in d.groups)

    sections = []
    for g in d.groups:
        rows = ""
        if g.qualifying:
            for md in g.qualifying:
                rows += _deal_row_html(md, cur, g.best is md)
            body = f"""<table class="deals">
        <thead><tr><th>Price/lb</th><th>Store</th><th>As printed</th><th>Valid</th><th></th></tr></thead>
        <tbody>{rows}</tbody></table>"""
        else:
            extra = ""
            if g.over_threshold:
                c = g.over_threshold[0]
                extra = (f' Cheapest seen was {_h(_money(cur, c.normalized.price_per_lb))}/lb '
                         f'at {_h(c.normalized.raw.store_name)}, above threshold.')
            body = f'<p class="none">No qualifying deals this week.{extra}</p>'

        sections.append(f"""
      <section class="item {'has-deals' if g.qualifying else 'no-deals'}">
        <h2>{_h(g.label)}</h2>
        <p class="threshold">At or below {_h(_money(cur, g.threshold_lb))}/lb</p>
        {body}
      </section>""")

    # review
    if d.review_items:
        rev_rows = ""
        for md in d.review_items:
            r = md.normalized.raw
            src = (f'<a href="{_h(r.source_url)}" rel="nofollow noopener" '
                   f'target="_blank">source</a>') if r.source_url else ""
            rev_rows += f"""
          <tr><td>{_h(md.item_label)}</td><td>{_h(r.store_name)}</td>
          <td>{_h(md.review_reason or 'needs review')}</td>
          <td>{_h(_raw_desc(md))}</td><td>{src}</td></tr>"""
        review_html = f"""<table class="review">
        <thead><tr><th>Item</th><th>Store</th><th>Why review</th><th>As printed</th><th></th></tr></thead>
        <tbody>{rev_rows}</tbody></table>"""
    else:
        review_html = '<p class="none">Nothing needed review this week.</p>'

    store_rows = ""
    for s in d.store_statuses:
        cls = "ok" if s.ok else "bad"
        store_rows += f"""
        <tr class="{cls}"><td>{_h(s.store_name)}</td>
        <td>{'ok' if s.ok else 'unavailable'}</td>
        <td>{s.deal_count}</td><td>{_h(s.note)}</td></tr>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_h(cfg.site_title)} - {_h(d.week_label)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <header class="top">
    <h1>{_h(cfg.site_title)}</h1>
    <p class="sub">Week of {_h(d.week_label)}{loc}</p>
    <p class="meta">Built {_h(d.generated_at)} &middot; {n_deals} qualifying deal(s) &middot;
       all prices normalized to price per pound &middot;
       <a href="archive.html">all weeks</a></p>
  </header>

  <div class="items">
    {''.join(sections)}
  </div>

  <section class="block">
    <h2>Review</h2>
    <p class="note">Not ranked. Unit unclear or lean percent unstated, so no per-pound
       price was computed. Verify before you drive.</p>
    {review_html}
  </section>

  <section class="block">
    <h2>Stores this week</h2>
    <table class="stores">
      <thead><tr><th>Store</th><th>Status</th><th>Candidates</th><th>Notes</th></tr></thead>
      <tbody>{store_rows}</tbody>
    </table>
  </section>

  <footer>
    <p>Prices are computed from pasted or owner-sourced flyer text and can be wrong or stale.
       Always confirm at the store. Items with an unclear unit or unstated lean percent are
       flagged for review, never given a guessed per-pound price.</p>
  </footer>
</main>
</body>
</html>
"""


_CSS = """
:root{
  --bg:#f7f7f5; --card:#ffffff; --ink:#1a1a1a; --muted:#666; --line:#e4e4e0;
  --accent:#8a1c1c; --good:#1c7a3a; --best-bg:#fff7e6; --best-ink:#8a5a00;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#141414; --card:#1e1e1e; --ink:#ececec; --muted:#9a9a9a;
    --line:#333; --accent:#ff8a8a; --good:#7ad19a; --best-bg:#2a2410; --best-ink:#e8c877; }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}
.top h1{margin:0 0 4px;font-size:1.9rem}
.sub{margin:0;font-weight:600;color:var(--accent)}
.meta{color:var(--muted);font-size:.85rem;margin:.4rem 0 0}
.meta a,.top a{color:var(--accent)}
.items{margin-top:24px;display:grid;gap:16px}
.item{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.item.no-deals{opacity:.72}
.item h2{margin:0 0 2px;font-size:1.2rem}
.threshold{margin:0 0 10px;color:var(--muted);font-size:.85rem}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th{text-align:left;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted);border-bottom:1px solid var(--line);padding:6px 8px}
td{padding:8px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
.ppl{font-weight:700;white-space:nowrap;font-size:1.02rem}
.per{font-weight:400;color:var(--muted);font-size:.8rem}
.store{white-space:nowrap}
.basis{color:var(--muted);font-size:.76rem;margin-top:2px}
.best{background:var(--best-bg);color:var(--best-ink);font-size:.66rem;
  padding:1px 6px;border-radius:999px;text-transform:uppercase;font-weight:700;letter-spacing:.03em}
.best-row td{background:var(--best-bg)}
.none{color:var(--muted);margin:6px 0}
.block{margin-top:28px;background:var(--card);border:1px solid var(--line);
  border-radius:12px;padding:16px 18px}
.block h2{margin:0 0 6px}
.note{color:var(--muted);font-size:.85rem;margin:0 0 10px}
.stores tr.bad td{color:var(--muted)}
footer{margin-top:28px;color:var(--muted);font-size:.8rem}
"""
