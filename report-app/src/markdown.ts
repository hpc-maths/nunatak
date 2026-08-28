/**
 * The small markdown the model is asked for, rendered.
 *
 * The system prompt asks for "compact markdown, no top-level heading",
 * and the model answers with headings, fenced code and lists. Showing
 * that as plain text puts `###` and ``` in front of the reader, on what
 * is the most read block of the page.
 *
 * The subset is deliberately the one the prompt asks for, and nothing
 * more: an unrecognized construct stays the literal text the model
 * wrote, which is the honest failure - never a guess at what it meant.
 * Links are left literal on purpose: the report promises that no
 * request leaves the page, and an anchor would be one.
 *
 * Every input crosses `esc` before any markup is produced, so no HTML
 * the model emits can reach the document - the transforms below only
 * ever run on already-escaped text.
 */

import { esc } from "./format";

// Code spans are lifted out before emphasis runs and put back after,
// so `a * b` inside a code span is never read as emphasis. The sentinel
// is a control character: the model's text reaches here escaped, and a
// literal one in it would already have been harmless text.
const SLOT = "\u0000";

/** Inline spans, applied to already-escaped text. */
function inline(escaped: string): string {
  const code: string[] = [];
  let text = escaped.replace(/`([^`]+)`/g, (_, body: string) => {
    code.push(body);
    return `${SLOT}${code.length - 1}${SLOT}`;
  });
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  return text.replace(
    new RegExp(`${SLOT}(\\d+)${SLOT}`, "g"),
    (_, index: string) => `<code>${code[Number(index)]}</code>`
  );
}

/** Rows of a list block, already escaped, as one `<ul>` or `<ol>`. */
function list(items: string[], ordered: boolean): string {
  const tag = ordered ? "ol" : "ul";
  const rows = items.map((item) => `<li>${inline(item)}</li>`).join("");
  return `<${tag} class="md-list">${rows}</${tag}>`;
}

/**
 * Render `text` as the markdown subset above.
 *
 * Returns HTML safe to insert: the source is escaped before anything
 * else happens, so the only tags in the result are the ones produced
 * here.
 */
export function markdown(text: string): string {
  const lines = esc(text).split("\n");
  const out: string[] = [];
  let paragraph: string[] = [];
  let items: string[] = [];
  let ordered = false;
  let fence: string[] | null = null;

  const flushParagraph = (): void => {
    if (paragraph.length === 0) return;
    out.push(`<p>${inline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const flushList = (): void => {
    if (items.length === 0) return;
    out.push(list(items, ordered));
    items = [];
  };
  const flush = (): void => {
    flushParagraph();
    flushList();
  };

  for (const line of lines) {
    if (fence !== null) {
      if (/^\s*```/.test(line)) {
        out.push(`<pre class="md-code"><code>${fence.join("\n")}</code></pre>`);
        fence = null;
      } else {
        fence.push(line);
      }
      continue;
    }
    const opening = line.match(/^\s*```/);
    if (opening) {
      flush();
      fence = [];
      continue;
    }
    if (line.trim() === "") {
      flush();
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flush();
      // The block already has a heading of its own, so the model's own
      // levels start below it rather than competing with it.
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level} class="md-head">${inline(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const wanted = numbered !== null;
      if (items.length > 0 && wanted !== ordered) flushList();
      flushParagraph();
      ordered = wanted;
      items.push((bullet ?? numbered)![1]);
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  if (fence !== null) {
    // An unterminated fence is what the model wrote: show it as code
    // rather than losing the block.
    out.push(`<pre class="md-code"><code>${fence.join("\n")}</code></pre>`);
  }
  flush();
  return out.join("");
}
