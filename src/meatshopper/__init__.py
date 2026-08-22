"""Meat Shopper: a weekly, per-pound-normalized meat/fish deal digest.

The pipeline is deliberately small and deterministic:

    adapters (per store)  -> RawDeal candidates
    normalize             -> per-pound price, or a review flag (never invented)
    match                 -> assign candidates to watch-list items, or drop
    rank                  -> threshold filter + cheapest-first ordering
    digest                -> markdown + HTML grouped by item

Anti-fabrication is the core rule: every price-per-pound number is computed
from parsed source values. If weight or unit is not confidently known, the
item is flagged for review with its raw price, never given a guessed $/lb.
"""

__version__ = "1.0.0"
