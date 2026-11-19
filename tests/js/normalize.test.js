import { test } from "node:test";
import assert from "node:assert/strict";
import { normalize, isRunningHeader } from "../../src/normalize.js";

test("running headers are recognized, ordinary text is not", () => {
  assert.equal(isRunningHeader("LB542 2025"), true);
  assert.equal(isRunningHeader("AM2839 LB959 DLM - 03/19/2026"), true);
  assert.equal(isRunningHeader("LB542"), true);
  assert.equal(isRunningHeader("Sections 71-1908 to 71-1923.03"), false);
  assert.equal(isRunningHeader("Section 1. LB542 is amended"), false);
});

test("page numbers and headers are removed and counted", () => {
  const { text, stats } = normalize("LB542 2025\nSection 1. Text one\n-2-\nLB542 2025\nmore text");
  assert.equal(text, "Section 1. Text one more text");
  assert.equal(stats.pageNumbersRemoved, 1);
  assert.equal(stats.headersRemoved, 2);
});

test("line numbers are stripped when most lines carry one", () => {
  const raw = Array.from({ length: 12 }, (_, i) => `${i + 1} word${i}`).join("\n");
  const { text, stats } = normalize(raw);
  assert.equal(text.startsWith("word0 word1"), true);
  assert.equal(stats.lineNumbersRemoved, 12);
});

test("a stray leading number is kept when lines are not numbered", () => {
  const { text, stats } = normalize("Section 1. Text\n2 of this act applies\nmore");
  assert.match(text, /2 of this act/);
  assert.equal(stats.lineNumbersRemoved, 0);
});

test("line numbers on their own lines are removed", () => {
  const raw = ["1", "text a", "2", "text b", "3", "text c", "4", "text d", "5", "text e"].join("\n");
  assert.equal(normalize(raw).text, "text a text b text c text d text e");
});

test("a section number split at its hyphen is rejoined", () => {
  assert.equal(normalize("section 39-\n1304.02, Reissue").text, "section 39-1304.02, Reissue");
});

test("non-breaking spaces, curly quotes and en dashes are normalized", () => {
  assert.equal(normalize("71-1908 (1) “x” 48–1").text, '71-1908 (1) "x" 48-1');
});
