#!/usr/bin/env python3
"""Check data/definitions.json for structural problems, and compare with a previous build.

Usage:
  python scripts/validate_definitions.py [data/definitions.json]
  python scripts/validate_definitions.py new.json --previous old.json

Exit code 1 if any hard error is found. Warnings do not fail the run.
Standard library only.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCOPE_TYPES = {"sections", "section", "chapter", "act", "all_statutes", "pointer", "unparsed"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(data):
    errors, warnings = [], []
    for key in ("meta", "acts", "definition_sections", "section_index"):
        if key not in data:
            errors.append(f"missing top-level key: {key}")
    if errors:
        return errors, warnings

    position = {}
    for chapter, rows in data["section_index"].items():
        for i, (section, _status, _title) in enumerate(rows):
            position[section] = (chapter, i)
    if not position:
        errors.append("section_index is empty")

    seen = set()
    for rec in data["definition_sections"]:
        sec = rec.get("section", "?")
        if rec["section"] in seen:
            errors.append(f"{sec}: duplicate definitions section")
        seen.add(rec["section"])
        if rec["section"] not in position:
            errors.append(f"{sec}: not in section_index")
        scope = rec.get("scope", {})
        if scope.get("type") not in SCOPE_TYPES:
            errors.append(f"{sec}: unknown scope type {scope.get('type')!r}")
        for start, end in scope.get("ranges") or []:
            if start not in position or end not in position:
                errors.append(f"{sec}: scope range {start}..{end} has an endpoint missing from section_index")
            elif position[start][0] != position[end][0] or position[start][1] > position[end][1]:
                errors.append(f"{sec}: scope range {start}..{end} is out of order or spans chapters")
        if scope.get("type") in ("sections", "section", "act", "chapter") and not scope.get("ranges"):
            errors.append(f"{sec}: scope type {scope['type']} but no ranges")
        names = set()
        for term in rec.get("terms", []):
            if not term.get("term") or not term.get("text"):
                errors.append(f"{sec}: empty term or text")
            key = term.get("term", "").casefold()
            if key in names:
                warnings.append(f"{sec}: term defined twice in one section: {term.get('term')}")
            names.add(key)
            if term.get("cross_ref") and term["cross_ref"] not in position:
                warnings.append(f"{sec}: cross reference to unknown section {term['cross_ref']}")
        if rec.get("needs_review"):
            warnings.append(f"{sec}: needs review: {'; '.join(rec['needs_review'])}")
    return errors, warnings


def compare(new, old):
    def summary(data):
        return {r["section"]: sorted(t["term"] for t in r["terms"]) for r in data["definition_sections"]}

    a, b = summary(old), summary(new)
    lines = [
        f"definitions sections: {len(a)} -> {len(b)}",
        f"defined terms: {sum(map(len, a.values()))} -> {sum(map(len, b.values()))}",
    ]
    removed, added = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    if removed:
        lines.append("sections no longer present: " + ", ".join(removed))
    if added:
        lines.append("new sections: " + ", ".join(added))
    changed = [s for s in a if s in b and a[s] != b[s]]
    if changed:
        lines.append("sections whose term list changed (spot-check these): " + ", ".join(sorted(changed)))
    if a and len(b) < 0.9 * len(a):
        lines.append("WARNING: definitions sections dropped by more than 10 percent")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=str(ROOT / "data" / "definitions.json"))
    parser.add_argument("--previous", help="earlier definitions.json to compare against")
    args = parser.parse_args()
    data = load(args.path)
    errors, warnings = validate(data)
    print(f"{len(data['definition_sections'])} definitions sections checked")
    print(f"{len(errors)} errors, {len(warnings)} warnings")
    for line in errors:
        print("ERROR  ", line)
    for line in warnings[:50]:
        print("warning", line)
    if len(warnings) > 50:
        print(f"... {len(warnings) - 50} more warnings")
    if args.previous:
        print("\nComparison with previous build:")
        for line in compare(data, load(args.previous)):
            print(" ", line)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
