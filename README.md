# RelevantDefinitions

A small tool for the Nebraska Legislature. Given a bill, it works out which sections of the Revised Statutes of Nebraska the bill cites, finds the definitions sections that govern those sections, and shows the defined terms that actually appear in the bill, each with its full definition and section citation.

**Status:** Phase 2 (statute extraction): extractor written and tested on saved pages; the full statute build has not been run yet. Phase 3 (section detection): bill text normalization and citation detection written and tested on excerpts of two real documents; not yet tested on whole real bills or PDFs. The page is not started. See `docs/DESIGN.md`.

## What it does

- Accepts a bill as an uploaded PDF or pasted text. Typing a bill number only opens the Legislature's page so the PDF can be downloaded and dropped in (the page cannot fetch bills itself).
- Detects existing statute sections cited in the bill (title and enacting clause).
- Maps each cited section to the definitions section(s) whose scope covers it.
- Scans the bill text for those defined terms and displays only the ones that appear, grouped by source act or chapter.
- If the bill cites no existing statute, or creates a new act, it says so plainly instead of returning nothing.

## What it does not do

- It does not parse, diff or interpret strike-and-insert markup. Terms that appear only in struck text will still match.
- It does not identify or evaluate new definitions proposed in the bill.
- It does not give legal advice or claim a term is used in its defined sense. It shows which definitions govern the cited sections, nothing more. Many Nebraska definitions apply "unless the context otherwise requires."

## Design principles

- Deterministic. Section detection, scope mapping and term matching are pattern matching against structured data. No model sits in the core pipeline.
- Static front end, no server, minimal dependencies, deployable on free static hosting.
- Statute data is extracted offline into a versioned JSON file bundled with the page. Every result screen shows the statute year and retrieval date.
- Anything the parser cannot read is flagged for manual review, never guessed.

## Layout

```
README.md          this file
docs/DESIGN.md     architecture, data model, matching rules, risks
data/              extracted statute JSON and SOURCES.md (provenance)
scripts/           offline statute extraction and validation (Python, standard library)
src/               page, bill normalization, section detection, matching
tests/             unit tests and the gold test set (tests/gold/README.md)
```

## Tests

    node --test "tests/js/*.test.js"        # bill text and citation detection (Node 20+)
    python -m unittest discover -s tests/python   # statute parsing

## Rebuilding the statute data

Needs a machine that can reach nebraskalegislature.gov, and Python 3.11 or newer (no packages to install):

    python scripts/extract_definitions.py all

On Windows you can double-click `scripts/extract.bat`. It takes roughly one to two hours, can be stopped and restarted, and writes `data/definitions.json` and `data/build_report.md`. Then run the checks:

    python scripts/validate_definitions.py
    python -m unittest discover -s tests/python

See `data/SOURCES.md` for the full refresh procedure.
