// Finds the existing statute sections a bill cites. Pure functions on plain text.
//
// Input is normalized text (see normalize.js). Output separates how a section is cited:
//
//   amended / repealed / outright_repealed   named in the title or in an operative clause
//                                            ("Section 14-2113, Reissue Revised Statutes of Nebraska,
//                                            is amended to read", "Original section ... is repealed")
//   referenced                               mentioned only inside the text of the bill
//                                            ("as defined in section 86-5,104")
//
// The first group is what defines which acts a bill touches. The second is secondary:
// a bill that quotes "section 18-2201" has not changed that section.
//
// Not done here (see docs/DESIGN.md): telling struck-out text from new text. A section
// mentioned only in text the bill deletes is still reported as referenced.

export const SECTION_PATTERN =
  String.raw`(?<![\d-])\d{1,3}-\d{1,4}(?:,\d{1,4}(?![\d-]))?(?:\.\d{1,3})?(?![\d-])`;

const EDITION_PATTERN =
  /Reissue\s+Revised\s+Statutes\s+of\s+Nebraska|Revised\s+Statutes\s+Cumulative\s+Supplement,?\s*(\d{4})|Revised\s+Statutes\s+Supplement,?\s*(\d{4})|Revised\s+Statutes\s+of\s+Nebraska/gi;

// A number counts as a citation in running text only if it follows the word "section(s)",
// possibly as part of a list ("sections 39-1361 and 39-1362", "sections 81-101 to 81-105").
// This keeps "$1-5 million", "10-12 members" and "2-1 vote" out.
const CITED_RUN = new RegExp(
  String.raw`\bsections?\s+(?:${SECTION_PATTERN})(?:\s*(?:,|;|,?\s+and|,?\s+or|\s+to|\s+through)\s*(?:${SECTION_PATTERN}))*`,
  "gi"
);

export function findCitedTokens(text) {
  const seen = new Set();
  const out = [];
  for (const run of text.matchAll(CITED_RUN)) {
    for (const t of findTokens(run[0])) {
      const index = run.index + t.index;
      if (seen.has(index)) continue;
      seen.add(index);
      out.push({ section: t.section, index, end: index + t.section.length });
    }
  }
  return out.sort((a, b) => a.index - b.index);
}

const BILL_SECTION_HEADER = /\bSec(?:tion|\.)\s+\d{1,3}\.\s/g;

export function findTokens(text) {
  const tokens = [];
  for (const m of text.matchAll(new RegExp(SECTION_PATTERN, "g"))) {
    const chapter = Number(m[0].split("-")[0]);
    if (chapter < 1 || chapter > 90) continue; // statutes run from chapter 1 to 90
    tokens.push({ section: m[0], index: m.index, end: m.index + m[0].length });
  }
  return tokens;
}

function findEditions(text) {
  const out = [];
  for (const m of text.matchAll(EDITION_PATTERN)) {
    let kind = "revised";
    let year = null;
    if (/^Reissue/i.test(m[0])) kind = "reissue";
    else if (/Cumulative/i.test(m[0])) [kind, year] = ["cumulative_supplement", Number(m[1])];
    else if (/Supplement/i.test(m[0])) [kind, year] = ["supplement", Number(m[2])];
    out.push({ kind, year, index: m.index, end: m.index + m[0].length });
  }
  return out;
}

// Pairs of consecutive tokens joined by "to" / "through" are ranges.
function findRanges(text, tokens) {
  const ranges = [];
  for (let i = 0; i + 1 < tokens.length; i++) {
    const between = text.slice(tokens[i].end, tokens[i + 1].index).trim().toLowerCase();
    if (between === "to" || between === "through") {
      ranges.push({ from: tokens[i].section, to: tokens[i + 1].section });
    }
  }
  return ranges;
}

// Each section takes the edition named after it ("sections A and B, Reissue ..., and section C, Supplement, 2025").
function editionFor(token, editions) {
  const next = editions.find((e) => e.index >= token.end);
  return next ? { kind: next.kind, year: next.year } : null;
}

class Collector {
  constructor() {
    this.map = new Map();
    this.ranges = [];
  }
  add(section, role, source, edition, inRange = false) {
    let entry = this.map.get(section);
    if (!entry) {
      entry = { section, roles: new Set(), sources: new Set(), editions: [], mentions: 0, inRange: false };
      this.map.set(section, entry);
    }
    entry.roles.add(role);
    entry.sources.add(source);
    entry.mentions++;
    if (inRange) entry.inRange = true;
    if (edition && !entry.editions.some((e) => e.kind === edition.kind && e.year === edition.year)) {
      entry.editions.push(edition);
    }
  }
}

function addSegment(collector, segment, role, source) {
  const tokens = findTokens(segment);
  const editions = findEditions(segment);
  const ranges = findRanges(segment, tokens);
  const inRange = new Set(ranges.flatMap((r) => [r.from, r.to]));
  for (const t of tokens) collector.add(t.section, role, source, editionFor(t, editions), inRange.has(t.section));
  for (const r of ranges) collector.ranges.push({ ...r, role, source });
}

// The text of an operative clause runs from the bill-section header ("Sec. 3.") to its verb phrase.
function clauseBefore(text, verbIndex) {
  const window = text.slice(Math.max(0, verbIndex - 700), verbIndex);
  let start = -1;
  for (const h of window.matchAll(BILL_SECTION_HEADER)) start = h.index + h[0].length;
  if (start < 0) {
    for (const h of window.matchAll(/\bSections?\s+\d{1,3}-/gi)) start = h.index;
  }
  return start < 0 ? "" : window.slice(start);
}

function clauseAfter(text, verbEnd) {
  const rest = text.slice(verbEnd, verbEnd + 4000);
  const next = rest.search(BILL_SECTION_HEADER);
  return next < 0 ? rest : rest.slice(0, next);
}

// ------------------------------------------------------------------ title

export function extractTitle(text) {
  const m = text.match(/A BILL FOR AN ACT([\s\S]*?)(?:Be it enacted by the people of the State of Nebraska|Section 1\.\s)/i);
  return m ? m[1].trim() : null;
}

function titleFlags(title) {
  const flags = {
    definesTerms: /\bto define\b|\bdefinitions?\b/i.test(title),
    repealsOriginal: /\bto repeal the original\b/i.test(title),
    outrightRepeal: /\bto outright repeal\b/i.test(title),
    adoptedActs: [],
  };
  for (const m of title.matchAll(/\bto (?:adopt|enact|create|establish) the ([A-Z][^;]*?(?:Act|Law|Code|Compact|Program|Plan))\b/g)) {
    flags.adoptedActs.push(m[1].trim());
  }
  return flags;
}

function addTitleClauses(collector, title) {
  for (const clause of title.split(";")) {
    const c = clause.trim();
    let role = null;
    if (/^to amend\b/i.test(c)) role = "amended";
    else if (/^to outright repeal\b/i.test(c)) role = "outright_repealed";
    else if (/^to repeal\b/i.test(c)) role = "repealed";
    if (role) addSegment(collector, c, role, "title");
  }
}

// ------------------------------------------------------------------- main

export function detectBill(text) {
  const head = text.slice(0, 400);
  if (/A BILL FOR AN ACT/i.test(text)) return { type: "bill" };
  const am = head.match(/AMENDMENTS?\s+TO\s+((?:LB|LR)\s?\d+)/i);
  if (am) return { type: "amendment", target: am[1].replace(/\s/g, "").toUpperCase() };
  return { type: "unknown" };
}

export function detectCitations(text) {
  const collector = new Collector();
  const warnings = [];
  const bill = detectBill(text);

  const title = extractTitle(text);
  const flags = title ? titleFlags(title) : { definesTerms: false, repealsOriginal: false, outrightRepeal: false, adoptedActs: [] };
  if (title) addTitleClauses(collector, title);
  else if (bill.type === "bill") warnings.push("Could not isolate the title paragraph; relying on the operative clauses.");

  // "... is/are amended to read"
  for (const m of text.matchAll(/\b(?:is|are)\s+amended\s+to\s+read\b/gi)) {
    addSegment(collector, clauseBefore(text, m.index), "amended", "clause");
  }
  // "Original section(s) ..., is/are repealed"
  for (const m of text.matchAll(/\b(?:is|are)\s+(?:hereby\s+)?repealed\b/gi)) {
    addSegment(collector, clauseBefore(text, m.index), "repealed", "clause");
  }
  // "... outright repealed"
  for (const m of text.matchAll(/\boutright\s+repealed\b/gi)) {
    const before = clauseBefore(text, m.index);
    const segment = findTokens(before).length ? before : clauseAfter(text, m.index + m[0].length);
    addSegment(collector, segment, "outright_repealed", "clause");
  }

  const operative = new Set(collector.map.keys());

  // Everything else in the text, outside the title, that looks like a section number.
  const titleStart = title ? text.indexOf(title) : -1;
  const body = title ? text.slice(0, titleStart) + " " + text.slice(titleStart + title.length) : text;
  const tokens = findCitedTokens(body);
  const bodyRanges = findRanges(body, tokens);
  const inRange = new Set(bodyRanges.flatMap((r) => [r.from, r.to]));
  const contexts = new Map();
  for (const t of tokens) {
    if (operative.has(t.section)) continue;
    collector.add(t.section, "referenced", "body", null, inRange.has(t.section));
    if (!contexts.has(t.section)) {
      contexts.set(t.section, body.slice(Math.max(0, t.index - 70), Math.min(body.length, t.end + 40)).trim());
    }
  }
  for (const r of bodyRanges) {
    if (!(operative.has(r.from) && operative.has(r.to) && collector.ranges.some((x) => x.from === r.from && x.to === r.to))) {
      collector.ranges.push({ ...r, role: "referenced", source: "body" });
    }
  }

  const rangeMap = new Map();
  for (const r of collector.ranges) {
    const key = `${r.from}|${r.to}|${r.role}`;
    const prior = rangeMap.get(key);
    if (prior) prior.sources = [...new Set([...prior.sources, r.source])];
    else rangeMap.set(key, { from: r.from, to: r.to, role: r.role, sources: [r.source] });
  }

  const cited = [...collector.map.values()].map((e) => ({
    section: e.section,
    roles: [...e.roles],
    sources: [...e.sources],
    editions: e.editions,
    mentions: e.mentions,
    inRange: e.inRange,
    context: contexts.get(e.section) ?? null,
  }));

  const primary = cited.filter((c) => c.roles.some((r) => r !== "referenced"));
  const referencedOnly = cited.filter((c) => c.roles.every((r) => r === "referenced"));

  // Sections in the title should also appear in an operative clause, and the reverse.
  const titleSet = new Set(cited.filter((c) => c.sources.includes("title")).map((c) => c.section));
  const clauseSet = new Set(cited.filter((c) => c.sources.includes("clause")).map((c) => c.section));
  if (bill.type === "bill" && titleSet.size && clauseSet.size) {
    for (const s of titleSet) if (!clauseSet.has(s)) warnings.push(`${s} is in the title but no operative clause was found for it.`);
    for (const s of clauseSet) if (!titleSet.has(s)) warnings.push(`${s} has an operative clause but is not in the title.`);
  }

  return {
    bill,
    title,
    titleFlags: flags,
    primary,
    referencedOnly,
    ranges: [...rangeMap.values()],
    summary: summarize(bill, flags, primary, referencedOnly),
    warnings,
  };
}

function summarize(bill, flags, primary, referencedOnly) {
  if (primary.length) return { kind: "amends_existing", sections: primary.length };
  if (flags.adoptedActs.length) return { kind: "new_act", acts: flags.adoptedActs };
  if (referencedOnly.length) return { kind: "references_only", sections: referencedOnly.length };
  return { kind: "none_found" };
}
