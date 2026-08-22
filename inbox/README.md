# inbox/ - drop your flyers here

This is the paste-fallback, and it is the primary, always-works path. The 2026
source investigation (see ../SOURCES.md) found no store offers a documented,
terms-compliant deal API, so you feed the tool by dropping flyer data here.

There is one folder per store id (matching `stores[].id` in
`../config/config.yaml`):

    inbox/shoprite/   inbox/stop_and_shop/   inbox/big_y/
    inbox/aldi/       inbox/walmart/         inbox/fresh_market/

Put any of these in a store's folder. Everything supported is read and merged:

## 1. Plain text (easiest) - `something.txt`

One deal per line. Free text is fine; the parser pulls out price, pack size,
promo, dates and links. Lines starting with `#` are directives or comments.

    # valid: 8/20-8/26
    # url: https://www.shoprite.com/circulars
    Boneless Skinless Chicken Thighs family pack $2.29/lb
    93% Lean Ground Beef $6.99/lb
    Wild Caught Cod Fillet $8.99/lb

For precision you can use the pipe format (any field may be blank):

    title | price | pack | promo | url | valid_from | valid_to
    Boneless Chicken Breast | $4.99 | 16 oz | | | 8/20 | 8/26

## 2. Structured JSON (most precise) - `something.json`

    {
      "source_url": "https://www.bigy.com/circular",
      "valid_from": "8/22", "valid_to": "8/28",
      "deals": [
        {"title": "Boneless Skinless Chicken Thighs",
         "price_text": "$3.49/lb", "pack_text": "family pack"}
      ]
    }

## 3. Flyer image or PDF - `flyer.png`, `ad.pdf`

Read via OCR IF you installed the optional extras:

    pip install -r ../requirements-ocr.txt
    brew install tesseract        # and: brew install poppler   (for PDFs)

If those are not installed, the file is skipped with a clear note in the
digest. Nothing is guessed from an unreadable scan.

## What NOT to worry about

You do not have to compute price per pound. The tool does that from what you
paste. If a line has no clear weight or unit, it lands in the digest's Review
section with its raw price, never a made-up per-pound number.

## The example files

Each folder ships with `example.txt` (or `.json`) so the first build produces a
real page. Delete or overwrite them with your actual flyers whenever you like.
