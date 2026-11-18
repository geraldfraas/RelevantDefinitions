# Statute data sources

`data/definitions.json` has not been built yet. When it is, record here for each refresh:

- Date and time range of retrieval (also stored in the file's `meta`)
- Script version
- Counts from `data/build_report.md`: definitions sections, defined terms, sections needing review
- Who reviewed the "needs review" list and what was decided

## Where the data comes from

- Chapter list: `https://nebraskalegislature.gov/laws/browse-statutes.php`
- Chapter indexes: `https://nebraskalegislature.gov/laws/browse-chapters.php?chapter=NN`
- Sections: `https://nebraskalegislature.gov/laws/statutes.php?statute=NN-NNN`

Only the section body is used. The page's Source and Annotations blocks are excluded.

## How candidate sections are chosen

The chapter indexes list every section with its title. The script downloads current sections whose title contains "defin", "how cited", "short title", "where found" or "may be cited". This is a title filter, so a definitions section with an unusual title would be missed. `fetch --all-sections` downloads everything for an audit (many hours); compare its build against the normal one to measure what the filter misses.

## Refreshing

Run on a machine that can reach the site (about one to two hours; resumable):

    python scripts/extract_definitions.py all

or double-click `scripts/extract.bat` on Windows. Then:

    python scripts/validate_definitions.py data/definitions.json --previous data/definitions.previous.json
    python -m unittest discover -s tests/python

Keep the old file as `definitions.previous.json` before rebuilding so the comparison works. Read `data/build_report.md`: every section listed under "Needs manual review" is shown to users as unresolved until it is fixed in the parser. Refresh after each legislative session, once the Revisor has published the updated statutes, and whenever a bill that passed changes a definition you care about.

Raw downloaded pages go in `data/raw/` (not committed).
