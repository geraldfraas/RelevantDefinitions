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
        "type": "sections | section | chapter | act | all_statutes | pointer | unparsed",
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

## What the real statute pages show (2026-11-17, from saved pages)

Scope language is not usually "As used in sections X to Y." Observed forms, all handled or flagged by `scripts/nelaws.py`:

| Form | Example | How it resolves |
| --- | --- | --- |
| Named act | 48-602 "For purposes of the Employment Security Law" | The act's own "how cited" section gives the range ("Sections 48-601 to 48-683 shall be known and may be cited as..."). Ranges can be several pieces (the Criminal Code is 28-101 to 28-1358, 28-1601 to 28-1603 and 28-1701). |
| Explicit range | 81-145 "As used in sections 81-145 to 81-161.06" | Direct. |
| Single section | 81-117.01 "As used in section 81-117" | Direct. |
| Global rule | 49-801 "words and phrases in the statutes of Nebraska" | Never mapped to a bill by default; offered as optional general construction. |
| "Definitions, where found" pointer | 49-1403 | The definitions live in the listed sections (49-1404 to 49-1444), which usually state no scope; they inherit the act from the pointer. |
| Single term, scope in prose | 48-114 "Employer, defined." | Term comes from the title; scope from the act named in the text, or flagged. |
| "this act", "this article" | many | "this act" resolves through act ranges. "this article" cannot yet: the chapter index has no article boundaries. Flagged. |

Other findings:

- Terms are introduced as "(1) Term means / shall mean / includes / shall signify ...", sometimes with qualifiers ("Wages, except with respect to ..., means ...", "Domestic when applied to corporations means ..."). Qualifiers are cut from the term and the whole item is kept as the definition text.
- Titles containing "defined" are not always definitions sections (28-107 "Felony or misdemeanor, defined outside of code"). Such sections are flagged, not dropped.
- Statute pages separate the body from "Source" and "Annotations" blocks. Annotations quote case law that uses the same words; they must never be scanned.
- Chapter index rows are in section order and include repealed and transferred sections. Index order, not numeric comparison, is used to resolve ranges.
- Some sections carry "Operative Date" notes (49-1403 shows July 18, 2026). Sections with two versions or future operative dates are not yet handled; to be examined once the full data is in.

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

- **Bill input: PDF upload or pasted text only** (decided 2026-11-17, option (a)). Typing a bill number just opens the Legislature's page so the user can download the PDF and drop it in. No relay and no local tool. Option (c), folding this feature into the local `nebraska-bill-packet` app, stays available as a later extension because both would feed the same plain-text pipeline.

## Open decisions

None at present. Next input needed: `statute_samples.zip` from `scripts/fetch_samples.py`.
