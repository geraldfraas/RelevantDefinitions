"""Parsing helpers for Nebraska Revised Statutes pages (nebraskalegislature.gov).

Standard library only. Everything here is a pure function of page text, so it
can be tested against saved HTML without network access.

Layer map (so failures can be assigned to the right layer):
  extraction  parse_chapter_index, parse_section_page
  scope       parse_scope, build_act_table, resolve_ranges
  terms       extract_definitions
"""
import html
import re

# A statute section number: 28-101, 49-14,100, 81-161.06, 48-1,110, 48-628.13
SECTION = r"\d{1,3}-\d{1,4}(?:,\d{1,4})?(?:\.\d{1,3})?"
SECTION_RE = re.compile(SECTION)

# ---------------------------------------------------------------- extraction

_ROW_RE = re.compile(
    r'<td class="row">\s*<span[^>]*><a href="/laws/statutes\.php\?statute=([^"&]+)">.*?</a></span>'
    r"\s*<span[^>]*>(.*?)</span>",
    re.S,
)


def clean_text(fragment):
    """Strip tags (without inserting spaces), unescape, normalize whitespace."""
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:])", r"\1", text)


def classify_title(title):
    """Return (status, transferred_to) from an index title."""
    if title.startswith("Repealed"):
        return "repealed", None
    if title.startswith("Transferred"):
        found = SECTION_RE.search(title)
        return "transferred", found.group(0) if found else None
    if title.startswith(("Expired", "Omitted", "Reserved", "Renumbered", "Obsolete")):
        return "other_inactive", None
    return "current", None


def parse_chapter_index(page_html):
    """List of {section, title, status, transferred_to} in page order."""
    rows = []
    for section, raw_title in _ROW_RE.findall(page_html):
        title = clean_text(raw_title)
        status, moved_to = classify_title(title)
        rows.append(
            {
                "section": html.unescape(section),
                "title": title,
                "status": status,
                "transferred_to": moved_to,
            }
        )
    return rows


def parse_chapter_links(page_html):
    """Chapter labels from the Revised Statutes by Chapter page."""
    labels = re.findall(r"browse-chapters\.php\?chapter=([^\"&]+)", page_html)
    seen, out = set(), []
    for label in labels:
        label = html.unescape(label)
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def parse_section_page(page_html):
    """Return {section, title, paragraphs, has_body} or None if not a statute page.

    paragraphs excludes the Source and Annotations blocks.
    """
    head = re.search(
        r'<div class="statute">\s*<h2>\s*([^<]+?)\.?\s*</h2>\s*<h3>(.*?)</h3>', page_html, re.S
    )
    if not head:
        return None
    section = clean_text(head.group(1)).rstrip(".")
    title = clean_text(head.group(2))
    body = page_html[head.end():]
    stop = re.search(r'<div>\s*<h2>Source</h2>|<h2>Source</h2>|<div class="statute_source">', body)
    if stop:
        body = body[: stop.start()]
    paragraphs = [clean_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)]
    paragraphs = [p for p in paragraphs if p]
    return {"section": section, "title": title, "paragraphs": paragraphs, "has_body": bool(paragraphs)}


# ------------------------------------------------------------------- ordering


def section_sort_key(section):
    """Fallback numeric key; the chapter index order is authoritative."""
    chapter, _, rest = section.partition("-")
    nums = [int(n) for n in re.findall(r"\d+", rest)]
    return (int(chapter) if chapter.isdigit() else 0, *nums)


class SectionOrder:
    """Position of every indexed section, for resolving ranges like 48-601 to 48-683."""

    def __init__(self, index_by_chapter):
        self.pos = {}
        self.chapter_of = {}
        self.by_chapter = {}
        for chapter, rows in index_by_chapter.items():
            self.by_chapter[chapter] = [r["section"] for r in rows]
            for i, row in enumerate(rows):
                self.pos[row["section"]] = (chapter, i)
                self.chapter_of[row["section"]] = chapter

    def chapter_range(self, chapter):
        sections = self.by_chapter.get(chapter)
        return [sections[0], sections[-1]] if sections else None

    def in_range(self, section, start, end):
        if section not in self.pos or start not in self.pos or end not in self.pos:
            return None  # cannot tell
        c1, i1 = self.pos[start]
        c2, i2 = self.pos[end]
        c, i = self.pos[section]
        return c == c1 == c2 and i1 <= i <= i2


# ---------------------------------------------------------------------- scope

_RANGE_CONNECT = re.compile(r"\s*(to|through|and|or|,|;)\s*", re.I)
_LIST_RE = re.compile(
    rf"(?:{SECTION})(?:\s*(?:,|;|,?\s+and|,?\s+or|\s+to|\s+through)\s*(?:{SECTION}))*", re.I
)


def parse_section_list(text):
    """'28-101 to 28-1358, 28-1601 to 28-1603, and 28-1701' -> [[a,b],[c,d],[e,e]]"""
    tokens = list(SECTION_RE.finditer(text))
    ranges, i = [], 0
    while i < len(tokens):
        start = tokens[i].group(0)
        end = start
        if i + 1 < len(tokens):
            between = text[tokens[i].end(): tokens[i + 1].start()].strip().lower()
            if between in ("to", "through", "to and including"):
                end = tokens[i + 1].group(0)
                i += 1
        ranges.append([start, end])
        i += 1
    return ranges


_NAME_WORD = r"(?:[A-Z][\w’'\-\.]*|of|and|for|on|the|in|to)"
_ACT_NAME_RE = re.compile(
    rf"\bthe\s+((?:{_NAME_WORD}\s+){{0,11}}?(?:Act|Law|Code|Compact|Program|Plan|Agreement|Contract)(?:\s+of\s+\d{{4}})?)"
)


def norm_act_name(name):
    name = name.replace("’", "'").strip().rstrip(".,;:")
    name = re.sub(r"^the\s+", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).casefold()


_CITED_AS_RE = re.compile(
    r"(?:^|\.\s+)(?P<lead>.*?)\bshall\s+be\s+known\s+(?:and\s+(?:may\s+be\s+)?cited\s+)?as\s+the\s+"
    r"(?P<name>[^.]+?)\s*\.?\s*$|"
    r"(?P<lead2>.*?)\bmay\s+be\s+cited\s+as\s+the\s+(?P<name2>[^.]+?)\s*\.?\s*$",
    re.S,
)


def build_act_table(pages):
    """Map normalized act name -> {name, ranges, source_section} from 'how cited' pages.

    pages: iterable of parsed section pages. Only the first paragraph is read.
    Acts whose citation sentence has no section list get ranges=None.
    """
    table = {}
    for page in pages:
        if not page["paragraphs"]:
            continue
        sentence = page["paragraphs"][0]
        match = _CITED_AS_RE.search(sentence)
        if not match:
            continue
        name = (match.group("name") or match.group("name2") or "").strip()
        lead = match.group("lead") if match.group("name") else match.group("lead2")
        if not name or len(name) > 120:
            continue
        ranges = parse_section_list(lead or "") or None
        table[norm_act_name(name)] = {
            "name": name,
            "ranges": ranges,
            "source_section": page["section"],
        }
    return table


_UNLESS_RE = re.compile(r"unless the context (?:clearly |otherwise )?(?:otherwise )?(?:requires|indicates|is shown)", re.I)
_INTRO_RE = re.compile(
    r"\b(as used in|as used throughout|for purposes of|for the purposes of|when used in|"
    r"for purposes of the definitions in|used in)\b",
    re.I,
)
_WHERE_FOUND_RE = re.compile(
    rf"definitions found in sections?\s+(?P<list>{_LIST_RE.pattern})", re.I
)
_GLOBAL_RE = re.compile(r"words and phrases in the statutes of nebraska", re.I)


def parse_scope(page, act_table):
    """Work out which sections a definitions section governs.

    Returns {type, ranges, act_name, raw_text, unless_context, resolution, notes}
    type is one of: sections, section, chapter, act, all_statutes, pointer, unparsed
    """
    section = page["section"]
    lead = " ".join(page["paragraphs"][:2])[:700]
    result = {
        "type": "unparsed",
        "ranges": None,
        "act_name": None,
        "raw_text": lead[:300],
        "unless_context": bool(_UNLESS_RE.search(lead)),
        "resolution": "none",
        "notes": [],
    }

    if _GLOBAL_RE.search(lead):
        result.update(type="all_statutes", resolution="explicit")
        return result

    pointer = _WHERE_FOUND_RE.search(lead)
    if pointer:
        result["points_to"] = parse_section_list(pointer.group("list"))
        act = _ACT_NAME_RE.search(lead)
        if act:
            result["act_name"] = act.group(1)
            entry = act_table.get(norm_act_name(act.group(1)))
            if entry and entry["ranges"]:
                result["ranges"] = entry["ranges"]
                result["resolution"] = "act_table"
            else:
                result["notes"].append("act not found in act table")
        result["type"] = "pointer"
        return result

    # Use the sentence that carries the introducing phrase, not the whole lead.
    intro = _INTRO_RE.search(lead)
    window = lead[intro.start(): intro.start() + 400] if intro else lead

    explicit = re.search(rf"\bsections?\s+(?P<list>{_LIST_RE.pattern})", window, re.I)
    if intro and explicit and explicit.start() < 60:
        ranges = parse_section_list(explicit.group("list"))
        single = len(ranges) == 1 and ranges[0][0] == ranges[0][1]
        result.update(type="section" if single else "sections", ranges=ranges, resolution="explicit")
        return result

    if intro and re.search(r"\bthis section\b", window[:80], re.I):
        result.update(type="section", ranges=[[section, section]], resolution="explicit")
        return result

    if intro and re.search(r"\bthis chapter\b", window[:80], re.I):
        result.update(type="chapter", resolution="explicit")
        result["chapter"] = section.split("-")[0]
        return result

    if intro and re.search(r"\bthis article\b", window[:80], re.I):
        result["notes"].append("scope is 'this article'; article boundaries are not in the section index")
        return result

    act = _ACT_NAME_RE.search(window if intro else lead) or _ACT_NAME_RE.search(lead)
    if act:
        name = act.group(1)
        result["act_name"] = name
        entry = act_table.get(norm_act_name(name))
        if entry and entry["ranges"]:
            result.update(type="act", ranges=entry["ranges"], resolution="act_table")
        elif entry:
            result["notes"].append("act found but its citation section lists no ranges")
        else:
            result["notes"].append("act name not found in act table")
        return result

    if intro and re.search(r"\bthis act\b|\bthe act\b", window[:80], re.I):
        result["notes"].append("scope is 'this act'; resolved later from act ranges")
        result["type"] = "act"
        result["resolution"] = "this_act"
        return result

    result["notes"].append("no recognizable scope phrase")
    return result


def inherit_pointer_scopes(definition_pages, scopes):
    """Sections inside a 'definitions found in sections X to Y' range inherit its scope."""
    for sec, scope in scopes.items():
        if scope["type"] != "pointer":
            continue
        for start, end in scope.get("points_to", []):
            for other, other_scope in scopes.items():
                if other_scope["type"] == "unparsed" and _in_range_loose(other, start, end):
                    other_scope.update(
                        type="act" if scope["ranges"] else "unparsed",
                        ranges=scope["ranges"],
                        act_name=scope["act_name"],
                        resolution="pointer:" + sec,
                    )
                    other_scope["notes"] = [n for n in other_scope["notes"] if n != "no recognizable scope phrase"]


def _in_range_loose(section, start, end):
    return section_sort_key(start) <= section_sort_key(section) <= section_sort_key(end)


# ---------------------------------------------------------------------- terms

_VERB_RE = re.compile(
    r"\b(shall\s+mean\s+and\s+include|means\s+and\s+includes|shall\s+mean|shall\s+include|"
    r"shall\s+refer\s+to|shall\s+be\s+construed\s+to\s+mean|shall\s+have\s+the\s+same\s+meaning|"
    r"has\s+the\s+same\s+meaning|have\s+the\s+same\s+meaning|has\s+the\s+meaning|"
    r"shall\s+signify|signif(?:y|ies)|means|includes|include|refers\s+to|is\s+defined\s+as|are\s+defined\s+as)\b"
)
_CUT_RE = re.compile(
    r"\s+(?:when|as)\s+(?:used|applied|it\s+is)\b.*$|\s+used\s+in\b.*$|\s+as\s+used\b.*$"
    r"|,?\s+(?:with\s+respect\s+to|except|other\s+than|not\s+including|excluding)\b.*$"
    r"|,\s+(?:when|if|for|in|within|unless|including)\b.*$",
    re.I,
)
_ITEM_RE = re.compile(r"^\((\d{1,3})\)\s+(.*)$", re.S)
_CROSS_RE = re.compile(r"(?:has|have|shall have) the same meaning as (?:in )?(?:section|sections)\s+(" + SECTION + ")", re.I)


def _term_from_item(first_line):
    """Split '(n) Term shall mean ...' into (term, remainder) or None."""
    verb = _VERB_RE.search(first_line)
    if not verb:
        return None
    term = first_line[: verb.start()].strip()
    term = _CUT_RE.sub("", term).strip().strip('"“”\'').strip()
    if not term or len(term.split()) > 8 or term[0].islower() and term.split()[0] in ("the", "a", "an", "any"):
        return None
    if term.lower().startswith(("the term ", "term ")):
        term = re.sub(r"^(the )?terms? ", "", term, flags=re.I)
    return term, first_line[verb.start():]


def extract_definitions(page):
    """Return {kind, terms, unparsed_items, notes}.

    kind: 'list' (numbered terms), 'single' (one term from the title), 'none'
    """
    paragraphs = page["paragraphs"]
    title = page["title"]
    items, lead, current = [], [], None
    for paragraph in paragraphs:
        match = _ITEM_RE.match(paragraph)
        if match:
            current = {"number": int(match.group(1)), "paragraphs": [match.group(2)]}
            items.append(current)
        elif current is not None:
            current["paragraphs"].append(paragraph)
        else:
            lead.append(paragraph)

    terms, unparsed, repealed = [], [], 0
    parsed_items = []
    for item in items:
        first = item["paragraphs"][0]
        if first.startswith("Repealed"):
            repealed += 1
            continue
        parsed = _term_from_item(first)
        parsed_items.append((item, parsed))

    good = [p for p in parsed_items if p[1]]
    lead_open = bool(lead) and lead[-1].rstrip().endswith(":") and re.search(
        r"\b(shall mean|means|shall include|includes)\s*:$", lead[-1].strip(), re.I
    )

    if items and good and len(good) >= max(1, int(0.6 * len(parsed_items))) and not lead_open:
        for item, parsed in parsed_items:
            if parsed:
                term, _ = parsed
                entry = {"term": term, "number": item["number"], "text": "\n".join(item["paragraphs"])}
                cross = _CROSS_RE.search(entry["text"])
                if cross:
                    entry["cross_ref"] = cross.group(1)
                terms.append(entry)
            else:
                unparsed.append({"number": item["number"], "text": item["paragraphs"][0][:160]})
        numbers = [i["number"] for i in items]
        notes = []
        if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
            notes.append("item numbers are not strictly increasing")
        elif numbers and numbers[0] != 1:
            notes.append(f"item numbering starts at {numbers[0]}")
        elif numbers != list(range(numbers[0], numbers[-1] + 1)):
            notes.append("gaps in item numbering")
        return {"kind": "list", "terms": terms, "unparsed_items": unparsed, "repealed_items": repealed, "notes": notes}

    single = re.match(r"^(.+?),?\s+defined\b", title, re.I)
    if single:
        names = [n.strip() for n in re.split(r",\s*|\s+and\s+", single.group(1)) if n.strip()]
        names = [n for n in names if len(n.split()) <= 6]
        if names:
            body = "\n".join(paragraphs)
            return {
                "kind": "single",
                "terms": [{"term": n, "number": None, "text": body, "from_title": True} for n in names],
                "unparsed_items": [],
                "repealed_items": repealed,
                "notes": ["term(s) taken from the section title"],
            }
    return {"kind": "none", "terms": [], "unparsed_items": unparsed, "repealed_items": repealed, "notes": ["no definitions recognized"]}
