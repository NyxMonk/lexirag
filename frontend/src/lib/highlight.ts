/**
 * Locate a source passage inside a PDF page's text layer, at character level.
 *
 * pdf.js splits text into items that do not follow word or sentence boundaries: Devanagari
 * may be split mid-syllable, while a whole line holding two sentences may be one item. Its
 * spacing also differs from our extracted text, and Devanagari is often emitted in visual
 * order (the ि sign before its consonant).
 *
 * So the page is matched as one string: all items are concatenated with whitespace removed,
 * the passage is normalised the same way, and the result is a list of character ranges per
 * item covering one contiguous match. If no exact match exists, a second pass compares
 * "skeletons" with combining marks removed on both sides. Nothing outside the match is
 * marked, and passages shorter than MIN_MATCH_CHARS are ignored.
 */

// Whitespace, control and format characters (pdf.js emits U+0000 for glyphs it cannot map),
// soft hyphens and zero-width characters differ between extractors.
const IGNORED = /[\s\p{Cc}\p{Cf}\u00ad]/u;
// Combining marks: Indic vowel signs, virama, nukta.
const MARK = /\p{M}/u;
const MIN_MATCH_CHARS = 12;

/** Character ranges [start, end) per item index, in the item's NFC-normalised string. */
export type HighlightRanges = Map<number, [number, number][]>;

interface IndexedPage {
  text: string;
  // For every character of ``text``: the item it came from and its offset in that item's NFC string.
  item: number[];
  offset: number[];
}

const lower = (ch: string) => {
  const l = ch.toLocaleLowerCase();
  return l.length === ch.length ? l : ch; // keep a 1:1 character mapping
};

function indexPage(items: string[], stripMarks: boolean): IndexedPage {
  const page: IndexedPage = { text: "", item: [], offset: [] };
  items.forEach((raw, index) => {
    const str = raw.normalize("NFC");
    for (let i = 0; i < str.length; i++) {
      const ch = str[i];
      if (IGNORED.test(ch) || (stripMarks && MARK.test(ch))) continue;
      page.text += lower(ch);
      page.item.push(index);
      page.offset.push(i);
    }
  });
  return page;
}

function fold(text: string, stripMarks: boolean): string {
  let out = "";
  const str = text.normalize("NFC");
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (IGNORED.test(ch) || (stripMarks && MARK.test(ch))) continue;
    out += lower(ch);
  }
  return out;
}

export function findHighlightRanges(items: string[], passages: string[]): HighlightRanges {
  const exact = indexPage(items, false);
  let skeleton: IndexedPage | null = null;
  const nfc = items.map((s) => s.normalize("NFC"));
  const ranges: HighlightRanges = new Map();

  for (const passage of passages) {
    let page = exact;
    let needle = fold(passage, false);
    if (needle.length < MIN_MATCH_CHARS) continue;
    let start = page.text.indexOf(needle);
    if (start === -1 && MARK.test(passage)) {
      skeleton ??= indexPage(items, true);
      page = skeleton;
      needle = fold(passage, true);
      if (needle.length < MIN_MATCH_CHARS) continue;
      start = page.text.indexOf(needle);
    }
    if (start === -1) continue;

    const end = start + needle.length;
    for (let k = start; k < end; k++) {
      const index = page.item[k];
      const str = nfc[index];
      let from = page.offset[k];
      let to = from + 1;
      // Keep combining marks attached to matched characters. Visual-order signs (ि) sit before
      // their consonant, so leading marks are included except at the very start of the match.
      while (to < str.length && MARK.test(str[to])) to++;
      if (k > start) while (from > 0 && MARK.test(str[from - 1])) from--;
      const list = ranges.get(index) ?? [];
      const last = list[list.length - 1];
      if (last && from <= last[1]) last[1] = Math.max(last[1], to);
      else list.push([from, to]);
      ranges.set(index, list);
    }
  }
  return ranges;
}

const escapeHtml = (text: string) =>
  text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/** HTML for one text-layer item with the given ranges wrapped in <mark>. PDF text is always escaped. */
export function markedHtml(text: string, ranges: [number, number][]): string {
  const str = text.normalize("NFC");
  let html = "";
  let cursor = 0;
  for (const [from, to] of ranges) {
    html += escapeHtml(str.slice(cursor, from)) + `<mark class="lexi-hl">${escapeHtml(str.slice(from, to))}</mark>`;
    cursor = to;
  }
  return html + escapeHtml(str.slice(cursor));
}

/** Passages to look for: a verified quote as-is, otherwise each paragraph of the stored chunk. */
export function highlightPassages(quote: string | null | undefined, chunkContent: string | null | undefined): string[] {
  if (quote) return [quote];
  if (!chunkContent) return [];
  return chunkContent
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}
