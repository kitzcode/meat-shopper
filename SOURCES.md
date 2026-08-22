# Sources report: what data path each store can actually use

Investigated 2026-08-22 for a personal, non-commercial weekly meat-deal digest
in the US Northeast (CT/NJ). This is the honest coverage picture, not a wish
list. Bottom line up front:

**None of the six stores offers a documented, terms-compliant public API for
reading weekly circular deal items.** So the tool uses owner-driven paste/upload
as the primary path for every store, and treats any automated fetch as an
optional bonus that must never be a hard dependency. That is why `config.yaml`
ships every store as `source: paste`.

## Per-store coverage

| Store | Realistic data path | Why | Terms caveat |
|-------|--------------------|-----|--------------|
| ShopRite | Paste-only | Circular is published online through a Flipp/Wishabi-style interactive flyer widget. No official public data API. | Programmatic pulls would hit undocumented Flipp endpoints, against Flipp's terms. |
| Stop & Shop | Paste-only | Same pattern: weekly circular online via a flyer widget, no documented feed. | Same Flipp caveat. |
| Big Y | Paste-only | Weekly flyer published online (current plus next week), no documented public API. | Same Flipp caveat. |
| Aldi | Paste-only | Aldi publishes a weekly ad on its own site, often mirrored by aggregators. No documented public API. | Flipp caveat plus Aldi's own site terms restrict automated access. |
| Walmart | Paste-only / manual | No traditional weekly circular at all. Deals show up as Rollbacks/Clearance on a digital, store-personalized page. Official walmart.io affiliate/content APIs are approval-gated, catalog-oriented, and not a circular feed. | Walmart's terms explicitly ban robots, spiders, scraping, data-mining, and AI-training use without written consent. |
| The Fresh Market | Paste-only / partially unavailable | No PDF circular. "Weekly Features" pages render a small, store-selected set dynamically. Not a classic circular and not prominently on Flipp. | Site terms restrict automated access; content is JS-rendered and store-gated. |

Note on "Flipp-powered": the pattern (Northeast grocery circulars served through
Wishabi/Flipp-style flyer widgets) is an observation, not a documented
integration. Do not treat it as a feed you can rely on.

## Flipp terms summary

Flipp (operated by Wishabi) is fundamentally a business-to-business retail-media
platform, not a consumer data provider. Its site markets ingesting merchant
content into Flipp; it does not publish an outbound public developer API for
reading flyer items. Flipp's Terms of Use (last updated June 13, 2023) grant
only a limited license for "personal and non-commercial use" and expressly
prohibit users from downloading, copying, capturing, or scraping the application
content, and from reverse-engineering the application. Endpoints cited in the
wild (for example `backflipp.wishabi.com/...`, `flipp.com/api`) are unofficial,
reverse-engineered endpoints surfaced by community scrapers, not documented or
sanctioned by Flipp. This project does not hardcode or depend on any of them.
They can break without notice, and using them for automated extraction is
contrary to Flipp's terms.

## Walmart terms summary

Walmart no longer runs a classic printed weekly circular; it keeps a digital,
store-personalized "Weekly Circular Ads" page where savings appear as Rollbacks
and Clearance. Its developer platform (walmart.io) offers an affiliate/content
provider API, but it is approval-gated, oriented to catalog data and tracked
monetization links, aimed at commercial traffic-driving use, and a poor and
unlikely-to-be-approved fit for a personal digest. Walmart.com's terms prohibit
using any robot or spider to retrieve, index, scrape, or data-mine materials,
and prohibit using materials to train AI or ML models, absent written consent.
The compliant path is manual paste of the Rollback prices you see in the app or
on that page.

## Why paste is the default architecture

1. It keeps a human in the loop and stays within "personal, non-commercial" use.
2. It sidesteps every terms-of-service scraping ban.
3. It is resilient to the constant endpoint and markup churn that breaks scrapers.
4. It works uniformly, including for stores with no feed at all (Walmart, The Fresh Market).
5. It runs free on GitHub Actions without a datacenter IP getting blocked by anti-bot systems.

The optional `source: fetch` mode (see `config.yaml`) does a single,
human-initiated GET of one specific public artifact you choose and put in
`inbox/<store>/source.url` (a direct flyer image, a PDF, or a simple deals
page). It is deliberately narrow: it is not a crawler and must not be pointed at
a store's internal endpoints or an interactive Flipp flyer widget.

## Hard rule

If a store's only automated option would require logged-in loyalty-account
coupon clipping, or scraping against terms, this tool stops and uses paste
instead. It never violates a source's terms to get a price.

## Pages actually read during the investigation

- Flipp Terms of Use: https://corp.flipp.com/terms-of-use/
- The Fresh Market weekly features: https://www.thefreshmarket.com/features/weekly-features
- Flipp corporate/platform positioning: https://corp.flipp.com/ and https://corp.flipp.com/platforms/
- Evidence of unofficial reverse-engineered Flipp endpoints (community scrapers), reviewed to confirm they are unofficial, not to use them.
- Walmart.com Terms of Use (scraping and AI-training prohibition).
- Walmart developer/affiliate docs: https://www.walmart.io/docs/affiliate/
- Walmart digital "Weekly Circular Ads" page: https://www.walmart.com/c/kp/weekly-circular-ads
- ShopRite circulars: https://www.shoprite.com/circulars

Skeptical caveats for the record: each chain's use of Flipp is inferred from the
flyer-widget pattern, not confirmed from official docs; the Walmart terms clause
was read via search summary and should be re-verified before relying on it;
"personal, non-commercial" use does not make undocumented-endpoint scraping
compliant, because Flipp's terms bar scraping regardless of purpose; and any
third-party endpoint names may already be stale.
