// Turns pasted or PDF-extracted bill text into one plain, flat string.
//
// Every input path ends here, so everything downstream sees the same thing.
// The artifacts removed (line numbers, page numbers, running headers) are the
// ones seen in drafting-system PDFs: 31 numbered lines per page, "-3-" page
// numbers, and a running header such as "LB542 2025" or "AM2839 LB959 DLM - 03/19/2026".
//
// These are heuristics. normalize() reports what it removed so the page can
// show it, and so a surprising count is visible rather than silent.

const HEADER_TOKEN = /^(?:(?:LB|LR|LA|AM)\d+|\d{4}|[A-Z]{2,4}|-|\d{1,2}\/\d{1,2}\/\d{2,4})$/;
const HEADER_ANCHOR = /^(?:LB|LR|LA|AM)\d+$/;

export function isRunningHeader(line) {
  const tokens = line.trim().split(/\s+/).filter(Boolean);
  if (tokens.length === 0 || tokens.length > 8) return false;
  return tokens.every((t) => HEADER_TOKEN.test(t)) && tokens.some((t) => HEADER_ANCHOR.test(t));
}

export function normalize(raw) {
  const stats = { lineNumbersRemoved: 0, pageNumbersRemoved: 0, headersRemoved: 0 };

  let text = String(raw ?? "")
    .replace(/\r\n?/g, "\n")
    .replace(/ /g, " ")
    .replace(/­/g, "")
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[‐-―−]/g, "-");

  let lines = text.split("\n");

  // Page numbers: "-3-"
  lines = lines.filter((line) => {
    if (/^\s*-\s*\d{1,3}\s*-\s*$/.test(line)) {
      stats.pageNumbersRemoved++;
      return false;
    }
    return true;
  });

  // Running headers
  lines = lines.filter((line) => {
    if (isRunningHeader(line)) {
      stats.headersRemoved++;
      return false;
    }
    return true;
  });

  // Line numbers, either as a prefix ("12 text") on most lines, or alone on a line.
  const nonEmpty = lines.filter((l) => l.trim());
  const prefixed = nonEmpty.filter((l) => {
    const m = l.match(/^\s*(\d{1,2})\s+\S/);
    return m && Number(m[1]) <= 31;
  });
  if (prefixed.length >= 8 && prefixed.length >= 0.6 * nonEmpty.length) {
    lines = lines.map((l) => {
      const m = l.match(/^\s*(\d{1,2})\s+(\S.*)$/);
      if (m && Number(m[1]) <= 31) {
        stats.lineNumbersRemoved++;
        return m[2];
      }
      return l;
    });
  }
  const alone = lines.filter((l) => /^\s*\d{1,2}\s*$/.test(l) && Number(l.trim()) <= 31);
  if (alone.length >= 5) {
    lines = lines.filter((l) => {
      if (/^\s*\d{1,2}\s*$/.test(l) && Number(l.trim()) <= 31) {
        stats.lineNumbersRemoved++;
        return false;
      }
      return true;
    });
  }

  // Rejoin a section number broken across a line at its hyphen: "39-" / "1304.02".
  text = lines.join("\n").replace(/(\d{1,3})-[ \t]*\n[ \t]*(\d)/g, "$1-$2");

  text = text.replace(/\s+/g, " ").trim();
  return { text, stats };
}
