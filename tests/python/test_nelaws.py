"""Tests for scripts/nelaws.py and the build step, run against saved real pages.

Run from the repository root:  python -m unittest discover -s tests/python
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import extract_definitions as ed  # noqa: E402
import nelaws  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "statutes"


def read(*parts):
    return (FIX.joinpath(*parts)).read_text(encoding="utf-8")


def page(section):
    return nelaws.parse_section_page(read("sections", f"statute_{section}.html"))


def all_pages():
    pages = {}
    for path in (FIX / "sections").glob("*.html"):
        p = nelaws.parse_section_page(path.read_text(encoding="utf-8"))
        pages[p["section"]] = p
    return pages


class ChapterIndex(unittest.TestCase):
    def test_counts_and_statuses(self):
        rows = nelaws.parse_chapter_index(read("chapters", "chapter_49.html"))
        self.assertEqual(len(rows), 477)
        self.assertEqual(sum(r["status"] == "repealed" for r in rows), 186)
        self.assertEqual(sum(r["status"] == "transferred" for r in rows), 6)

    def test_comma_and_decimal_sections_and_transfer_target(self):
        rows = {r["section"]: r for r in nelaws.parse_chapter_index(read("chapters", "chapter_49.html"))}
        self.assertIn("49-14,100", rows)
        self.assertIn("49-202.01", rows)
        self.assertEqual(rows["49-703"]["transferred_to"], "24-211.03")


class SectionPage(unittest.TestCase):
    def test_title_and_body(self):
        p = page("48-114")
        self.assertEqual(p["section"], "48-114")
        self.assertEqual(p["title"], "Employer, defined.")
        self.assertTrue(p["paragraphs"][0].startswith("The following shall constitute employers"))

    def test_source_and_annotations_are_excluded(self):
        text = " ".join(page("48-114")["paragraphs"])
        self.assertNotIn("Kaiser", text)
        self.assertNotIn("Laws 1913", text)

    def test_repealed_page_has_no_body(self):
        p = page("48-104")
        self.assertTrue(p["title"].startswith("Repealed"))
        self.assertEqual(p["paragraphs"], [])


class SectionLists(unittest.TestCase):
    def test_mixed_ranges_and_singles(self):
        got = nelaws.parse_section_list("28-101 to 28-1358, 28-1601 to 28-1603, and 28-1701")
        self.assertEqual(got, [["28-101", "28-1358"], ["28-1601", "28-1603"], ["28-1701", "28-1701"]])

    def test_comma_section_number_is_one_token(self):
        self.assertEqual(nelaws.parse_section_list("49-1493 to 49-14,104"), [["49-1493", "49-14,104"]])


class Scope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = all_pages()
        cls.acts = nelaws.build_act_table(cls.pages.values())

    def scope(self, section):
        return nelaws.parse_scope(self.pages[section], self.acts)

    def test_act_table(self):
        self.assertEqual(self.acts["employment security law"]["ranges"], [["48-601", "48-683"]])
        self.assertEqual(len(self.acts["nebraska criminal code"]["ranges"]), 3)

    def test_named_act_resolves_through_act_table(self):
        s = self.scope("48-602")
        self.assertEqual((s["type"], s["resolution"]), ("act", "act_table"))
        self.assertEqual(s["ranges"], [["48-601", "48-683"]])
        self.assertTrue(s["unless_context"])

    def test_explicit_range(self):
        s = self.scope("81-145")
        self.assertEqual((s["type"], s["ranges"]), ("sections", [["81-145", "81-161.06"]]))

    def test_single_section(self):
        s = self.scope("81-117.01")
        self.assertEqual((s["type"], s["ranges"]), ("section", [["81-117", "81-117"]]))

    def test_global_rule_is_not_mapped_to_any_range(self):
        s = self.scope("49-801")
        self.assertEqual(s["type"], "all_statutes")
        self.assertIsNone(s["ranges"])

    def test_where_found_pointer(self):
        s = self.scope("49-1403")
        self.assertEqual(s["type"], "pointer")
        self.assertEqual(s["points_to"], [["49-1404", "49-1444"]])

    def test_unknown_act_is_flagged_not_guessed(self):
        s = self.scope("48-114")
        self.assertEqual(s["type"], "unparsed")
        self.assertEqual(s["act_name"], "Nebraska Workers' Compensation Act")


class Definitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = all_pages()

    def terms(self, section):
        return [t["term"] for t in nelaws.extract_definitions(self.pages[section])["terms"]]

    def test_numbered_list(self):
        d = nelaws.extract_definitions(self.pages["28-109"])
        self.assertEqual((d["kind"], len(d["terms"])), ("list", 24))
        self.assertIn("Serious bodily injury", self.terms("28-109"))

    def test_qualifiers_are_cut_from_terms(self):
        terms = self.terms("48-602")
        self.assertIn("Benefit year", terms)
        self.assertIn("Wages", terms)
        self.assertFalse(any(t.endswith(",") or "with respect to" in t for t in terms))

    def test_when_used_clause_is_cut(self):
        self.assertIn("Acquire", self.terms("49-801"))
        self.assertIn("Domestic", self.terms("49-801"))

    def test_single_term_section_takes_term_from_title(self):
        d = nelaws.extract_definitions(self.pages["48-603"])
        self.assertEqual(d["kind"], "single")
        self.assertEqual([t["term"] for t in d["terms"]], ["Employer"])

    def test_unparsed_item_is_reported_not_dropped(self):
        d = nelaws.extract_definitions(self.pages["81-117.01"])
        self.assertEqual([u["number"] for u in d["unparsed_items"]], [3])

    def test_definition_text_keeps_subdivisions(self):
        d = nelaws.extract_definitions(self.pages["48-602"])
        first = d["terms"][0]
        self.assertEqual(first["term"], "Agricultural labor")
        self.assertIn("(a) On a farm", first["text"])


class Ordering(unittest.TestCase):
    def test_range_membership_uses_index_order(self):
        index = {"48": nelaws.parse_chapter_index(read("chapters", "chapter_48.html"))}
        order = nelaws.SectionOrder(index)
        self.assertTrue(order.in_range("48-604", "48-601", "48-683"))
        self.assertFalse(order.in_range("48-114", "48-601", "48-683"))
        self.assertIsNone(order.in_range("48-604", "48-601", "99-999"))


class Build(unittest.TestCase):
    def test_build_over_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "chapters").mkdir()
            (raw / "sections").mkdir()
            for src in (FIX / "chapters").glob("*.html"):
                (raw / "chapters" / src.name).write_bytes(src.read_bytes())
            for src in (FIX / "sections").glob("*.html"):
                (raw / "sections" / src.name).write_bytes(src.read_bytes())
            data, report = ed.build(raw)
        reviewed = {r["section"] for r in report["needs_review"]}
        self.assertIn("28-107", reviewed)  # 'defined' in the title, but not a definitions section
        self.assertIn("48-114", reviewed)  # act not in the act table
        self.assertNotIn("48-602", reviewed)
        secs = {r["section"]: r for r in data["definition_sections"]}
        self.assertNotIn("48-601", secs)  # a how-cited page feeds the act table only
        self.assertEqual(secs["28-109"]["scope"]["act_name"], "Nebraska Criminal Code")


if __name__ == "__main__":
    unittest.main()
