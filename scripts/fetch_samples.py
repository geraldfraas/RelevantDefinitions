#!/usr/bin/env python3
"""Fetch raw sample pages from nebraskalegislature.gov for parser development.

Why: the statute parsers must be tested against the real HTML, and the
development sandbox cannot reach the site. Run this on a machine that can,
then send back the zip file it produces.

Usage: double-click, or `python fetch_samples.py`
Output: statute_samples/ and statute_samples.zip next to this script.

Standard library only. About 40 requests, one every 1.5 seconds.
"""
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

BASE = "https://nebraskalegislature.gov/laws/"
USER_AGENT = "RelevantDefinitions-sample-fetch/0.1 (legislative office tool)"
DELAY_SECONDS = 1.5
CHAPTERS = ["28", "48", "49", "81"]
# Sections chosen to cover different shapes. If one does not exist the
# manifest records the failure and the run continues.
FIXED_SECTIONS = [
    "48-601", "48-602", "48-603", "48-604", "48-606",
    "28-101", "28-109",
    "49-101", "49-14,100", "49-202.01",
]
MAX_DISCOVERED_PER_KIND = 2

OUT_DIR = Path(__file__).resolve().parent / "statute_samples"
ZIP_PATH = Path(__file__).resolve().parent / "statute_samples.zip"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read()


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9.,_-]+", "_", text)


def statute_url(section, print_view=False):
    url = BASE + "statutes.php?statute=" + urllib.parse.quote(section, safe=",.-")
    return url + "&print=true" if print_view else url


def discover(chapter_html):
    """Best-effort: find sections marked Repealed, Transferred, or defined."""
    found = {"repealed": [], "transferred": [], "defined": []}
    seen = set()
    for chunk in re.split(r"statutes\.php\?statute=", chapter_html)[1:]:
        match = re.match(r"([^\"'&<>\s]+)", chunk)
        if not match:
            continue
        section = urllib.parse.unquote(match.group(1))
        if section in seen:
            continue
        seen.add(section)
        window = chunk[:500]
        if "Repealed" in window:
            found["repealed"].append(section)
        elif "Transferred" in window:
            found["transferred"].append(section)
        elif re.search(r"defin", window, re.IGNORECASE):
            found["defined"].append(section)
    return found


def main():
    OUT_DIR.mkdir(exist_ok=True)
    manifest = [f"Retrieved {datetime.now().isoformat(timespec='seconds')}"]
    sections = list(FIXED_SECTIONS)

    def get_and_save(url, filename):
        time.sleep(DELAY_SECONDS)
        try:
            status, body = fetch(url)
            (OUT_DIR / filename).write_bytes(body)
            manifest.append(f"OK   {status} {len(body):>8} bytes  {filename}  {url}")
            print("ok  ", filename)
            return body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            manifest.append(f"FAIL {exc}  {filename}  {url}")
            print("FAIL", filename, exc)
            return None

    for chapter in CHAPTERS:
        body = get_and_save(
            BASE + f"browse-chapters.php?chapter={chapter}", f"chapter_{chapter}.html"
        )
        if body:
            html = body.decode("utf-8", errors="replace")
            for kind, items in discover(html).items():
                for section in items[:MAX_DISCOVERED_PER_KIND]:
                    if section not in sections:
                        sections.append(section)
                        manifest.append(f"NOTE discovered {kind}: {section}")

    for section in sections:
        get_and_save(statute_url(section), f"statute_{safe_name(section)}.html")
    get_and_save(statute_url("48-602", True), "statute_48-602_print.html")

    (OUT_DIR / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT_DIR.iterdir()):
            archive.write(path, path.name)

    print()
    print(f"Done. Attach this file to the chat: {ZIP_PATH}")


if __name__ == "__main__":
    main()
    if sys.stdin is not None and sys.stdin.isatty():
        input("Press Enter to close...")
