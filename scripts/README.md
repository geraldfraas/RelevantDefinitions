# scripts/

Offline statute extraction and validation. Python 3.11+, standard library only.

- `extract_definitions.py` downloads the statute indexes and candidate definitions sections, then builds `data/definitions.json`. Subcommands: `index`, `fetch`, `build`, `all`.
- `nelaws.py` the parsing library (page extraction, scope resolution, term extraction). No network.
- `validate_definitions.py` structural checks on the JSON, and a comparison with a previous build.
- `extract.bat` double-click launcher for Windows (runs `all`).
- `fetch_samples.py` one-off helper that saved the sample pages used as test fixtures.

Run the tests from the repository root: `python -m unittest discover -s tests/python`
