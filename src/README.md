# src/

Browser-ready ES modules with no dependencies and no build step. The same files run under Node for tests.

- `normalize.js` turns pasted or PDF-extracted text into one flat string (removes line numbers, page numbers, running headers).
- `sections.js` finds the statute sections a bill cites, split into primary (amended or repealed) and referenced-only.

Still to come: scope mapping (cited section to governing definitions), term matching, and the page. See `docs/DESIGN.md`.
