#!/usr/bin/env python3
"""Build data/definitions.json from the Revised Statutes of Nebraska.

Standard library only. Three steps, each safe to re-run:

  index   download the chapter list and every chapter's section index
  fetch   download the candidate definitions sections (resumable)
  build   parse the saved pages into data/definitions.json and a report

  all     index + fetch + build

Raw pages are cached under data/raw/ (not committed). The network steps need a
machine that can reach nebraskalegislature.gov. `build` needs no network.

Examples:
  python scripts/extract_definitions.py all
  python scripts/extract_definitions.py fetch --chapters 48 49
  python scripts/extract_definitions.py fetch --all-sections   # audit mode, very slow
  python scripts/extract_definitions.py build
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nelaws  # noqa: E402

SCRIPT_VERSION = "0.1.0"
BASE = "https://nebraskalegislature.gov/laws/"
USER_AGENT = "RelevantDefinitions-extract/0.1 (legislative office tool)"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "data" / "raw"
DEFAULT_OUT = ROOT / "data" / "definitions.json"
CANDIDATE_TITLE_RE = re.compile(r"defin|how cited|short title|where found|may be cited", re.I)


# ------------------------------------------------------------------ network


class Blocked(Exception):
    pass


def http_get(url, retries=3):
    delay = 5
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                raise Blocked(f"HTTP {exc.code} from {url}") from exc
            if exc.code < 500 or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 3


class Fetcher:
    def __init__(self, raw_dir, delay):
        self.raw = Path(raw_dir)
        self.delay = delay
        (self.raw / "chapters").mkdir(parents=True, exist_ok=True)
        (self.raw / "sections").mkdir(parents=True, exist_ok=True)
        self.log_path = self.raw / "fetch_log.jsonl"
        self.failures = []

    def get_to(self, url, path, refresh=False):
        if path.exists() and not refresh:
            return path.read_bytes()
        time.sleep(self.delay)
        try:
            status, body = http_get(url)
        except Blocked:
            raise
        except Exception as exc:  # noqa: BLE001 - record and continue
            self.failures.append((url, str(exc)))
            print("FAIL", url, exc)
            return None
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
        with self.log_path.open("a", encoding="utf-8") as log:
            record = {"url": url, "status": status, "bytes": len(body),
                      "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            log.write(json.dumps(record) + "\n")
        return body


def safe_name(section):
    return re.sub(r"[^A-Za-z0-9.,_-]+", "_", section)


def cmd_index(args):
    fetcher = Fetcher(args.raw, args.delay)
    listing = fetcher.get_to(BASE + "browse-statutes.php", Path(args.raw) / "browse-statutes.html", args.refresh)
    labels = args.chapters or []
    if not labels:
        if listing is None:
            sys.exit("Could not download the chapter list.")
        labels = nelaws.parse_chapter_links(listing.decode("utf-8", errors="replace"))
        if len(labels) < 40:
            sys.exit(f"Found only {len(labels)} chapter links; expected 80 or more. "
                     "Send data/raw/browse-statutes.html so the parser can be fixed, "
                     "or pass --chapters explicitly.")
    print(f"{len(labels)} chapters")
    for label in labels:
        url = BASE + "browse-chapters.php?chapter=" + urllib.parse.quote(label)
        fetcher.get_to(url, Path(args.raw) / "chapters" / f"chapter_{safe_name(label)}.html", args.refresh)
    report_failures(fetcher)


def load_index(raw_dir):
    """{chapter: rows}, chapters in the order of the chapter list when available."""
    chapters = {}
    for path in sorted((Path(raw_dir) / "chapters").glob("chapter_*.html")):
        label = path.stem[len("chapter_"):]
        rows = nelaws.parse_chapter_index(path.read_text(encoding="utf-8", errors="replace"))
        chapters[label] = rows
    return chapters


def cmd_fetch(args):
    index = load_index(args.raw)
    if not index:
        sys.exit("No chapter indexes found. Run the index step first.")
    wanted = []
    for chapter, rows in index.items():
        if args.chapters and chapter not in args.chapters:
            continue
        for row in rows:
            if row["status"] != "current":
                continue
            if args.all_sections or CANDIDATE_TITLE_RE.search(row["title"]):
                wanted.append(row["section"])
    fetcher = Fetcher(args.raw, args.delay)
    todo = [s for s in wanted if not (Path(args.raw) / "sections" / f"{safe_name(s)}.html").exists() or args.refresh]
    print(f"{len(wanted)} candidate sections, {len(todo)} still to download "
          f"(about {len(todo) * args.delay / 60:.0f} minutes)")
    try:
        for n, section in enumerate(todo, 1):
            url = BASE + "statutes.php?statute=" + urllib.parse.quote(section, safe=",.-")
            fetcher.get_to(url, Path(args.raw) / "sections" / f"{safe_name(section)}.html", args.refresh)
            if n % 25 == 0:
                print(f"  {n}/{len(todo)}")
    except Blocked as exc:
        sys.exit(f"Stopped: {exc}. The site is refusing requests. Wait a while and run fetch again; "
                 "finished pages are kept.")
    report_failures(fetcher)


def report_failures(fetcher):
    if fetcher.failures:
        print(f"\n{len(fetcher.failures)} downloads failed. Run the same command again to retry:")
        for url, why in fetcher.failures[:20]:
            print("  ", url, why)


# -------------------------------------------------------------------- build


def retrieval_window(raw_dir):
    path = Path(raw_dir) / "fetch_log.jsonl"
    if not path.exists():
        return None, None
    times = [json.loads(line)["at"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return (min(times), max(times)) if times else (None, None)


def build(raw_dir):
    """Parse cached pages. Returns (data, report)."""
    index = load_index(raw_dir)
    order = nelaws.SectionOrder(index)
    status_of = {row["section"]: row for rows in index.values() for row in rows}

    pages, unreadable = {}, []
    for path in sorted((Path(raw_dir) / "sections").glob("*.html")):
        page = nelaws.parse_section_page(path.read_text(encoding="utf-8", errors="replace"))
        if page is None:
            unreadable.append(path.name)
            continue
        pages[page["section"]] = page

    acts = nelaws.build_act_table(pages.values())
    scopes = {s: nelaws.parse_scope(p, acts) for s, p in pages.items()}
    nelaws.inherit_pointer_scopes(pages, scopes)

    sections, review = [], []
    for section, page in sorted(pages.items(), key=lambda kv: nelaws.section_sort_key(kv[0])):
        defs = nelaws.extract_definitions(page)
        title_says_defined = bool(re.search(r"defin", page["title"], re.I))
        if defs["kind"] == "none" and not title_says_defined:
            continue  # a how-cited page or other non-definitions section
        scope = scopes[section]

        # "this act": find the act whose ranges contain this section
        if scope["resolution"] == "this_act":
            for entry in acts.values():
                if entry["ranges"] and any(order.in_range(section, a, b) for a, b in entry["ranges"]):
                    scope.update(type="act", act_name=entry["name"], ranges=entry["ranges"], resolution="act_table")
                    break
            else:
                scope.update(type="unparsed")
                scope["notes"].append("'this act' could not be matched to an act range")

        # chapter-wide scope: fill the range from the section index
        if scope["type"] == "chapter":
            span = order.chapter_range(scope.get("chapter", ""))
            if span:
                scope["ranges"] = [span]

        # every range endpoint must exist in the section index
        missing = []
        for start, end in scope["ranges"] or []:
            for endpoint in (start, end):
                if endpoint not in order.pos:
                    missing.append(endpoint)
        if missing:
            scope["notes"].append("range endpoints not in section index: " + ", ".join(sorted(set(missing))))

        problems = []
        if scope["type"] == "unparsed":
            problems.append("scope not understood")
        if missing:
            problems.append("range endpoint not in section index")
        if scope["type"] == "pointer":
            if not scope["ranges"]:
                problems.append("'definitions found in' pointer: act not resolved")
        elif defs["kind"] == "none":
            problems.append("no definitions recognized")
        if defs["unparsed_items"]:
            problems.append(f"{len(defs['unparsed_items'])} numbered item(s) not parsed")
        if defs["kind"] == "single" and scope["type"] == "unparsed":
            problems.append("single term taken from title, scope unknown")
        problems += [n for n in defs["notes"] if n.startswith(("gaps", "item numbers", "item numbering"))]

        record = {
            "section": section,
            "title": page["title"],
            "chapter": order.chapter_of.get(section, section.split("-")[0]),
            "scope": scope,
            "kind": defs["kind"],
            "terms": defs["terms"],
            "unparsed_items": defs["unparsed_items"],
            "needs_review": problems,
        }
        sections.append(record)
        if problems:
            review.append({"section": section, "title": page["title"], "problems": problems, "notes": scope["notes"]})

    first, last = retrieval_window(raw_dir)
    data = {
        "meta": {
            "script_version": SCRIPT_VERSION,
            "source": BASE,
            "retrieved_first": first,
            "retrieved_last": last,
            "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "Candidate sections were chosen by title; see data/SOURCES.md for limits.",
        },
        "acts": [{"name": v["name"], "ranges": v["ranges"], "source_section": v["source_section"]}
                 for v in sorted(acts.values(), key=lambda v: v["name"])],
        "definition_sections": sections,
        "section_index": {
            chapter: [[r["section"], r["status"], r["title"] if r["status"] == "current" else ""] for r in rows]
            for chapter, rows in index.items()
        },
    }

    scope_types = Counter(s["scope"]["type"] for s in sections)
    resolution = Counter(s["scope"]["resolution"].split(":")[0] for s in sections)
    report = {
        "chapters_indexed": len(index),
        "sections_in_index": sum(len(r) for r in index.values()),
        "current_sections": sum(1 for r in status_of.values() if r["status"] == "current"),
        "pages_parsed": len(pages),
        "pages_unreadable": unreadable,
        "acts_found": len(acts),
        "definition_sections": len(sections),
        "definition_terms": sum(len(s["terms"]) for s in sections),
        "scope_types": dict(scope_types),
        "scope_resolution": dict(resolution),
        "clean_sections": len(sections) - len(review),
        "needs_review": review,
    }
    return data, report


def render_report(report):
    lines = [
        "# Extraction report",
        "",
        f"- Chapters indexed: {report['chapters_indexed']}",
        f"- Sections in index: {report['sections_in_index']} (current: {report['current_sections']})",
        f"- Section pages parsed: {report['pages_parsed']}",
        f"- Acts with a citation section: {report['acts_found']}",
        f"- Definitions sections: {report['definition_sections']} "
        f"(clean: {report['clean_sections']}, needs review: {len(report['needs_review'])})",
        f"- Defined terms: {report['definition_terms']}",
        f"- Scope types: {report['scope_types']}",
        f"- Scope resolution: {report['scope_resolution']}",
    ]
    if report["pages_unreadable"]:
        lines += ["", "## Pages that could not be read", *[f"- {n}" for n in report["pages_unreadable"]]]
    lines += ["", "## Needs manual review", ""]
    if not report["needs_review"]:
        lines.append("None.")
    for item in report["needs_review"]:
        lines.append(f"- {item['section']} {item['title']}: {'; '.join(item['problems'])}"
                     + (f" ({'; '.join(item['notes'])})" if item["notes"] else ""))
    return "\n".join(lines) + "\n"


def cmd_build(args):
    data, report = build(args.raw)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    report_path = out.with_name("build_report.md")
    report_path.write_text(render_report(report), encoding="utf-8")
    print(render_report(report))
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB) and {report_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["index", "fetch", "build", "all"])
    parser.add_argument("--raw", default=str(DEFAULT_RAW), help="folder for cached pages")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    parser.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    parser.add_argument("--chapters", nargs="*", help="limit to these chapter labels")
    parser.add_argument("--all-sections", action="store_true", help="fetch every current section (audit)")
    parser.add_argument("--refresh", action="store_true", help="download again even if cached")
    args = parser.parse_args()
    if args.command in ("index", "all"):
        cmd_index(args)
    if args.command in ("fetch", "all"):
        cmd_fetch(args)
    if args.command in ("build", "all"):
        cmd_build(args)


if __name__ == "__main__":
    main()
