# Design (Phase 1 draft, for review)

## Pipeline

Every input converges on plain text before any detection logic runs.

```
PDF / pasted text / fetched bill -> normalize() -> detectSections() -> mapScopes() -> matchTerms() -> render()
```

- `normalize()` strips line numbers, headers, footers, page numbers and hyphenation.
- Matching logic is plain JS modules shared by the page and the tests, so there is one implementation.
- Tests run with Node's built-in test runner.

## Inputs

1. **Pasted text.** Straight to `normalize()`.
2. **PDF upload.** Parsed in the browser. Candidate: reuse the PDF reader from `geraldfraas/NE-Redliner` (no library, already knows the drafting-system layout of 31 numbered lines per page). It was tested on one bill and one amendment, so extraction is its own test layer.
3. **Bill number.** The browser cannot fetch Legislature pages (CORS). The existing `geraldfraas/nebraska-bill-packet` tool already retrieves the introduced-bill PDF from `https://nebraskalegislature.gov/FloorDocs/{legislature}/PDF/Intro/LB{number}.pdf`. Proposed: that local tool supplies the PDF, and this page treats it like an upload. Decision pending.

## Statute data

- Source: nebraskalegislature.gov. Chapter index pages (`laws/browse-chapters.php?chapter=NN`) give every section number, title and status (repealed, transferred). Individual sections: `laws/statutes.php?statute=NN-NNN`.
- Plan: scrape chapter indexes into `section_index`; fetch sections whose titles suggest definitions; confirm each by its "As used in" text; optionally run a full-text audit scrape.
- Section numbers include decimals and commas (`49-202.01`, `49-14,100`). Both must work in citation detection and range ordering.
- The scraper runs on the owner's machine. The development sandbox cannot reach the site.

## Data model

```
{
  "meta": { "statute_year", "retrieved", "source_url", "script_version" },
  "definition_sections": [
    {
      "section": "48-601",
      "chapter": "48",
      "act_name": "...",
      "scope": {
        "type": "range | article | chapter | act | unparsed",
        "raw_text": "As used in sections 48-601 to 48-669, ...",
        "from": "48-601", "to": "48-669",
        "unless_context_otherwise_requires": true
      },
      "terms": [
        { "term": "employee", "variants": ["employees"],
          "text": "...", "cross_ref": null,
          "status": "current | repealed | transferred" }
      ]
    }
  ],
  "section_index": { "48-601": { "title": "...", "status": "current" } }
}
```

`section_index` is ordered. Ranges can only be resolved against the real ordering because numbering has suffixes and gaps. `raw_text` is kept on every scope so a reviewer can see what the parser read.

## Matching rules

- Case-insensitive, whole-word, simple plural and variant handling.
- Longest terms first, consumed on match, so "state employee" does not also surface "employee".
- Only definitions from acts the bill cites. The same word from unrelated acts is shown under separate headings, never blended.
- Distinctive terms first; ubiquitous ones ("person," "department," "board") collapsed below, not hidden.
- "Show all definitions in governing sections" toggle, off by default.

## Edge cases to handle explicitly

Range, article and chapter-wide scopes; cross-reference definitions ("has the same meaning as in section X"); bills citing several acts; new sections or a new act; repealed or renumbered sections; PDF extraction artifacts.

## Risks that could mislead a senator

- Context-dependent definitions: display says "governing definition for the cited sections," never "this term means."
- Stale statute data: statute year and retrieval date on every result.
- Amendment bills: matches include stricken language; a visible note says so.
- Chapter-wide definitions can produce long lists, hence distinctive-first sorting.
- Unparsed scope: shown as needs manual review, never silently dropped.

## Decisions

- **Hosting: GitHub Pages** (decided 2026-11-17).
- **Output: shown in the browser, with a print-ready view that can be saved as PDF** (decided). Proposed implementation: a print stylesheet plus the browser's own "Save as PDF", which needs no PDF library. A generated PDF would need a library or a hand-written writer.
- **PDF reader: lift from NE-Redliner, test-driven** (tentative). Replace it if it fails on real bills.

## Open decisions

- **Bill-number path.** The owner does not want a separate local tool in the loop. A page on GitHub Pages cannot fetch nebraskalegislature.gov directly (CORS). Options: (a) PDF upload and pasted text only, with bill-number entry just opening the Legislature's page so the user can download the PDF; (b) a small free proxy (for example a Cloudflare Worker) that relays the bill PDF, which is new infrastructure and would need an allowlist like `nebraska-bill-packet` has; (c) fold the definitions page into the local `nebraska-bill-packet` app instead of GitHub Pages. Needs the owner's choice.
