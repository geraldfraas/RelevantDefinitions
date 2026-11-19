import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { normalize } from "../../src/normalize.js";
import { detectCitations, findTokens, findCitedTokens } from "../../src/sections.js";

const fixture = (name) =>
  normalize(readFileSync(new URL(`../fixtures/bills/${name}`, import.meta.url), "utf8")).text;
const detect = (text) => detectCitations(normalize(text).text);
const names = (list) => list.map((c) => c.section).sort();
const get = (result, section) => [...result.primary, ...result.referencedOnly].find((c) => c.section === section);

test("LB542: amended and repealed sections come from the title and clauses", () => {
  const r = detectCitations(fixture("lb542_excerpt.txt"));
  assert.equal(r.bill.type, "bill");
  assert.deepEqual(names(r.primary), ["14-2113", "39-1304.02"]);
  const s = get(r, "14-2113");
  assert.deepEqual(s.roles.sort(), ["amended", "repealed"]);
  assert.deepEqual(s.sources.sort(), ["clause", "title"]);
  assert.deepEqual(s.editions, [{ kind: "reissue", year: null }]);
  assert.equal(r.summary.kind, "amends_existing");
  assert.deepEqual(r.warnings, []);
});

test("LB542: sections only mentioned in the text are 'referenced', not amended", () => {
  const r = detectCitations(fixture("lb542_excerpt.txt"));
  assert.deepEqual(names(r.referencedOnly), ["18-2201", "39-1361", "39-1362", "86-5,104"]);
  assert.match(get(r, "86-5,104").context, /as defined in section 86-5,104/);
});

test("LB542: a section's own heading and a later cite of it are not double-reported", () => {
  const r = detectCitations(fixture("lb542_excerpt.txt"));
  assert.equal(r.referencedOnly.some((c) => c.section === "39-1304.02"), false);
});

test("LB542: title says 'to define terms'", () => {
  assert.equal(detectCitations(fixture("lb542_excerpt.txt")).titleFlags.definesTerms, true);
});

test("AM2839: an amendment has no title, clauses still work, target bill is found", () => {
  const r = detectCitations(fixture("am2839_excerpt.txt"));
  assert.deepEqual(r.bill, { type: "amendment", target: "LB959" });
  assert.deepEqual(names(r.primary), ["71-1908"]);
  assert.deepEqual(get(r, "71-1908").editions, [{ kind: "supplement", year: 2025 }]);
});

test("AM2839: 'section 2 of this act' is not a statute; the range is reported as a range", () => {
  const r = detectCitations(fixture("am2839_excerpt.txt"));
  assert.deepEqual(r.ranges.map((x) => [x.from, x.to, x.role]), [["71-1908", "71-1923.03", "referenced"]]);
  assert.equal(get(r, "71-1923.03").inRange, true);
});

test("mixed editions in one title are assigned to the right sections", () => {
  const r = detect(
    "A BILL FOR AN ACT relating to taxes; to amend sections 77-101 and 77-102, Reissue Revised Statutes of Nebraska, and section 77-2701, Revised Statutes Cumulative Supplement, 2024; and to repeal the original sections. Be it enacted by the people of the State of Nebraska, Section 1. Section 77-101, Reissue Revised Statutes of Nebraska, is amended to read: 77-101 x"
  );
  assert.deepEqual(get(r, "77-101").editions, [{ kind: "reissue", year: null }]);
  assert.deepEqual(get(r, "77-2701").editions, [{ kind: "cumulative_supplement", year: 2024 }]);
});

test("section numbers with a comma or a decimal stay whole", () => {
  assert.deepEqual(findTokens("sections 48-1,110, 49-14,100 and 49-202.01.").map((t) => t.section), ["48-1,110", "49-14,100", "49-202.01"]);
});

test("a list with no spaces is not mistaken for a comma section number", () => {
  assert.deepEqual(findTokens("sections 28-101,28-102").map((t) => t.section), ["28-101", "28-102"]);
});

test("numbers that cannot be statutes are ignored", () => {
  assert.deepEqual(findTokens("Laws 2025-2026, page 99-100, section 12-3456").map((t) => t.section), ["12-3456"]);
});

test("outright repeal with the list after the verb", () => {
  const r = detect(
    "A BILL FOR AN ACT relating to labor; to outright repeal sections 48-101 and 48-102, Reissue Revised Statutes of Nebraska. Be it enacted by the people of the State of Nebraska, Section 1. The following sections are outright repealed: Sections 48-101 and 48-102, Reissue Revised Statutes of Nebraska."
  );
  assert.deepEqual(names(r.primary), ["48-101", "48-102"]);
  assert.deepEqual(get(r, "48-101").roles, ["outright_repealed"]);
});

test("a new act with no existing sections says so", () => {
  const r = detect(
    "A BILL FOR AN ACT relating to energy; to adopt the Nebraska Solar Easement Act; to provide duties. Be it enacted by the people of the State of Nebraska, Section 1. Sections 1 to 5 of this act shall be known as the Nebraska Solar Easement Act."
  );
  assert.equal(r.primary.length, 0);
  assert.deepEqual(r.summary, { kind: "new_act", acts: ["Nebraska Solar Easement Act"] });
});

test("a bill citing nothing reports none_found", () => {
  const r = detect("A BILL FOR AN ACT relating to nothing. Be it enacted by the people of the State of Nebraska, Section 1. Text.");
  assert.equal(r.summary.kind, "none_found");
});

test("a title section with no matching clause is warned about", () => {
  const r = detect(
    "A BILL FOR AN ACT relating to labor; to amend section 48-101, Reissue Revised Statutes of Nebraska; and to repeal the original section. Be it enacted by the people of the State of Nebraska, Section 1. Section 48-102, Reissue Revised Statutes of Nebraska, is amended to read: 48-102 x"
  );
  assert.equal(r.warnings.length, 2);
});

test("PDF-style artifacts do not change the result", () => {
  const clean = fixture("lb542_excerpt.txt");
  const noisy = [
    "LB542", "2025",
    "1 A BILL FOR AN ACT relating to roads; to amend sections 14-2113 and 39-",
    "2 1304.02, Reissue Revised Statutes of Nebraska; to define terms; and to repeal the original section.",
    "3 Be it enacted by the people of the State of Nebraska,",
    "-2-", "LB542 2025",
    "4 Section 1. Section 14-2113, Reissue Revised Statutes of Nebraska, is amended to read:",
    "5 14-2113 [body omitted] sections 39-1361 and 39-1362,",
    "6 Sec. 2. Section 39-1304.02, Reissue Revised Statutes of Nebraska, is amended to read:",
    "7 39-1304.02 x", "8 Sec. 3. Original sections 14-2113 and 39-1304.02, Reissue Revised Statutes of Nebraska,", "9 are repealed.",
  ].join("\n");
  const a = detectCitations(clean);
  const b = detectCitations(normalize(noisy).text);
  assert.deepEqual(names(b.primary), names(a.primary));
  assert.deepEqual(names(b.referencedOnly), ["39-1361", "39-1362"]);
});

test("figures and counts in the text are not read as references", () => {
  const r = detect(
    "A BILL FOR AN ACT relating to money; to amend section 77-101, Reissue Revised Statutes of Nebraska. Be it enacted by the people of the State of Nebraska, Section 1. Section 77-101, Reissue Revised Statutes of Nebraska, is amended to read: 77-101 Fiscal year 2025-26, $1-5 million, 10-12 members, a 2-1 vote, chapter 99-100. See sections 81-101 and 81-102. Sec. 2. Original section 77-101, Reissue Revised Statutes of Nebraska, is repealed."
  );
  assert.deepEqual(names(r.primary), ["77-101"]);
  assert.deepEqual(names(r.referencedOnly), ["81-101", "81-102"]);
});

test("a list of references after the word 'sections' is followed to its end", () => {
  assert.deepEqual(
    findCitedTokens("under sections 48-1,110, 48-1,111 and 48-1,112 to 48-1,115, but not 10-12").map((t) => t.section),
    ["48-1,110", "48-1,111", "48-1,112", "48-1,115"]
  );
});

test("a range named in both the title and a clause is reported once", () => {
  const r = detect(
    "A BILL FOR AN ACT relating to child care; to amend sections 71-1908 to 71-1910, Revised Statutes Supplement, 2025; and to repeal the original sections. Be it enacted by the people of the State of Nebraska, Section 1. Sections 71-1908 to 71-1910, Revised Statutes Supplement, 2025, are amended to read: 71-1908 x"
  );
  assert.equal(r.ranges.filter((x) => x.role === "amended").length, 1);
  assert.deepEqual(r.ranges[0].sources.sort(), ["clause", "title"]);
});
