# Meat Shopper

A weekly digest of meat and fish sales across your local grocers, filtered to
your watch list and normalized to price per pound so the deals are actually
comparable. It runs free on GitHub Actions and publishes to GitHub Pages.

The point is the per-pound comparison. A keyword match alone is noise (it finds
seasoning, pet food, "cream of chicken"). This tool parses each deal, computes
an effective price per pound, and shows only the items at or below the threshold
you set, cheapest first, grouped by item.

## What it does

- Reads your flyer deals (see [Sources](#where-the-deals-come-from) below).
- Normalizes every price to price per pound: per-lb, per-package-with-weight,
  multi-buy ("2 for $6"), BOGO, and "$X off when you buy N".
- Matches deals to your watch list with careful rules (leanness for ground
  beef, plain cut vs breaded for fish, exact cut for steak).
- Ranks qualifying deals cheapest-first and highlights the best price per item.
- Flags anything it cannot price confidently in a Review section, with the raw
  price and a link, instead of guessing.
- Keeps every past week in an archive and publishes the current week to Pages.

### The one rule that matters

Every price-per-pound number is computed from values parsed out of the source
text. If the weight or unit is not clear, the item goes to Review with its raw
price. It never invents a per-pound number. A wrong number could send you
driving for a deal that is not there; a flagged item is safe.

## Quick start (local)

```bash
pip install -e .
meat-shopper                       # builds docs/ and archive/ from inbox/
open docs/index.html
```

The repo ships with example flyers in `inbox/`, so the first build produces a
real page. Replace them with your own.

## Configure it: `config/config.yaml`

This is the only file you edit. It holds:

- **location**: your `postal_code` (not hardcoded anywhere in the code) and an
  optional display label.
- **watchlist**: each item's `label`, its `threshold_lb` (only deals at or below
  this $/lb are surfaced), and the match phrases (`include`, `require_all`,
  `exclude`) plus optional special rules.
- **stores**: the six store adapters and each one's `source`.
- **output**: site title, currency, archive retention.

Starter thresholds (all tunable):

| Item | Threshold $/lb |
|------|----------------|
| Boneless skinless chicken thighs | 3.49 |
| Chicken breast (boneless skinless) | 2.99 |
| Ground beef, 93%+ lean | 8.49 |
| Boneless pork chops | 4.99 |
| Pork loin | 3.99 |
| Salmon | 9.99 |
| Cod | 9.99 |
| Sirloin steak | 12.99 |

The ground beef rule only counts a deal when it states 93% lean or higher. If
lean is not stated it goes to Review, never assumed.

## Where the deals come from

The 2026 investigation ([SOURCES.md](SOURCES.md)) found that **no store offers a
documented, terms-compliant public API** for weekly deal items. Paste is the
first-class path, not a fallback bolted on. A hands-on test of what a plain
fetch actually returns refined the picture: three stores hard-block bots, one
only exposes clearance, and one embeds clean JSON that the opt-in fetch mode can
read.

| Store | Coverage |
|-------|----------|
| ShopRite | Paste (Flipp-style widget; plain fetch returns 403) |
| Stop & Shop | Paste (same) |
| Big Y | Paste (same) |
| Aldi | Paste (print URL exposes only a clearance rail, not the meat ad) |
| Walmart | Paste / manual (no circular at all; copy Rollbacks by hand) |
| The Fresh Market | **Auto via opt-in fetch** (embeds structured JSON), or paste |

### Using paste

Drop any of these into `inbox/<store_id>/` (one folder per store):

- **Text** (`.txt`, `.md`): one deal per line, free text. `#` lines are
  directives (`# valid: 8/20-8/26`, `# url: https://...`) or comments.
- **JSON** (`.json`): precise structured deals. See `inbox/README.md`.
- **Image or PDF** (`.png`, `.jpg`, `.pdf`): read via OCR if the optional extras
  are installed (`pip install -e ".[ocr]"` plus `brew install tesseract
  poppler`). If they are not installed, the file is skipped with a clear note,
  never guessed.

Full format details and examples are in [inbox/README.md](inbox/README.md).

### Optional single fetch

Set a store's `source: fetch` and put one URL in `inbox/<store_id>/source.url`
to have the tool do a single, human-initiated fetch of that specific public
flyer artifact (a direct image, PDF, or simple page) and run the same
extractor. This is deliberately narrow and must not point at store internal
endpoints or an interactive flyer widget. See [SOURCES.md](SOURCES.md).

**The Fresh Market ships pre-wired this way.** Its weekly-features page embeds
its specials as structured JSON, so `config.yaml` sets it to `source: fetch`
with the URL already in `inbox/fresh_market/source.url` and a parser in
`src/meatshopper/sites.py`. It is best-effort: if their markup changes or the
fetch is blocked (a datacenter/CI IP may be blocked where your laptop is not),
that store just reports no deals and you paste instead. The other five stores
are paste, because three of them (ShopRite, Stop & Shop, Big Y) hard-block bots
and Aldi's fetchable page is only a clearance rail, not the meat ad.

## The weekly digest

Grouped by item, cheapest per-pound first, with store, effective $/lb, the raw
price and pack as printed, valid dates, and a source link. The best price per
item is highlighted. Two more sections keep it honest:

- **Review**: items flagged because the unit was unclear or the lean percent was
  unstated. Nothing is silently dropped.
- **Stores this week**: which adapters ran, how many candidates each returned,
  and a note for any store with no data.

Output lands in:

- `docs/index.html` (latest week, served by Pages), `docs/weeks/<date>.html`,
  `docs/archive.html` (all weeks).
- `archive/<date>.md` and `archive/<date>.json` (kept per week).

## Running it on GitHub (free)

1. Push this repo to GitHub.
2. In Settings > Pages, set the source to "GitHub Actions".
3. The workflow in `.github/workflows/weekly-digest.yml` runs every Saturday
   (and on demand from the Actions tab). It builds the digest, commits the new
   archive and site, and deploys Pages.

To feed it each week, commit your flyer files into `inbox/<store_id>/` (or use
the on-demand run after pasting). No secrets or paid APIs are required.

## Adding a store or an automated adapter later

Adapters are pluggable behind one interface (`meatshopper/adapters/base.py`).
Every current store reads paste; a future compliant automated adapter would
register in `meatshopper/adapters/__init__.py` behind the same interface without
touching the pipeline. A flaky adapter can never break the digest: failures are
caught and shown in the "stores this week" section.

## Tests

```bash
python tests/test_normalize.py     # the price-per-pound core
python tests/test_sites.py         # the Fresh Market structured parser (offline)
python tests/test_pipeline.py      # end-to-end against the sample inbox (offline)
```

## Layout

```
config/config.yaml          your watch list, thresholds, location, stores
inbox/<store_id>/           drop flyers here (the primary data path)
src/meatshopper/
  normalize.py              price-per-pound engine (the deterministic core)
  match.py                  careful, non-greedy matching + special rules
  rank.py                   threshold filter + cheapest-first ordering
  digest.py                 markdown + HTML output
  adapters/                 pluggable per-store adapters (paste, fetch)
  sites.py                  structured parsers for fetch mode (Fresh Market)
  build.py                  the pipeline entry point
docs/                       published site (GitHub Pages)
archive/                    per-week markdown + json snapshots
SOURCES.md                  honest per-store data-path report
```

## Terms and scope

No logged-in loyalty coupon clipping. No scraping against any store's terms. If
the only automated option would break a source's terms, the tool uses paste
instead. Coupons are out of scope for v1. Confirm prices at the store; the digest
is computed from what you paste and can be wrong or stale.
