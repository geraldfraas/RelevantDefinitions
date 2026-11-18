# Gold test set

Aim for 15 to 25 real bills, each in its own folder `tests/gold/<bill>/`:

```
bill.pdf            the file exactly as it would be fed to the tool (or bill.txt)
expected.json       hand-verified expected results
```

## expected.json

```
{
  "cited_sections": ["48-601", "48-604"],
  "governing_definition_sections": ["48-601"],
  "expected_terms": [{ "term": "employee", "source_section": "48-604" }],
  "must_not_surface": [{ "term": "employee", "source_section": "81-1301" }],
  "notes": "e.g. new act, repeal only, renumbering"
}
```

- `cited_sections`: every existing section the bill cites.
- `governing_definition_sections`: which definitions sections should apply.
- `expected_terms`: terms that should surface, each with its source section.
- `must_not_surface`: likely false positives, such as the same word from an unrelated act.
- `notes`: edge cases.

## Mix to collect

Several single-section amendments; 3 to 4 multi-act bills; 2 to 3 new-act bills; 2 to 3 repeal bills; different drafters and years; at least one with poor PDF extraction; both introduced and amended versions of at least one bill.

Final verification of each `expected.json` must be done by a person.

Note: real bills may be legislative working documents. Check whether they are appropriate to commit to a public repository before adding them.
