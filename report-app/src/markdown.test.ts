/**
 * The advice renderer. The dangerous class of bug here is the model's
 * text reaching the document as markup, so the escaping is pinned first
 * and every other case is read against real answer shapes.
 */

import { expect, test } from "vitest";
import { markdown } from "./markdown";

test("markup in the answer is shown, never executed", () => {
  const html = markdown('<img src=x onerror="alert(1)"> and <b>bold</b>');
  expect(html).not.toContain("<img");
  expect(html).not.toContain("<b>");
  expect(html).toContain("&lt;img");
  expect(html).toContain("&lt;b&gt;bold&lt;/b&gt;");
});

test("markup inside a fenced block is shown too", () => {
  const html = markdown("```html\n<script>alert(1)</script>\n```");
  expect(html).not.toContain("<script>");
  expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
});

test("the model's headings sit below the block's own", () => {
  const html = markdown("### 1. Cache the result of repeated lookups");
  expect(html).toContain(
    '<h5 class="md-head">1. Cache the result of repeated lookups</h5>'
  );
  expect(html).not.toContain("###");
});

test("a fenced block keeps its lines and its indentation", () => {
  const html = markdown("```cpp\nauto it = cache_.find(key);\n  return *it;\n```");
  expect(html).toContain(
    '<pre class="md-code"><code>auto it = cache_.find(key);\n  return *it;</code></pre>'
  );
  expect(html).not.toContain("```");
});

test("an unterminated fence is shown as the code it was", () => {
  const html = markdown("```cpp\nauto x = 1;");
  expect(html).toContain("auto x = 1;");
  expect(html).not.toContain("```");
});

test("inline code, bold and italic", () => {
  const html = markdown("The `find(...)` call is **hot**, not *cold*.");
  expect(html).toContain("<code>find(...)</code>");
  expect(html).toContain("<strong>hot</strong>");
  expect(html).toContain("<em>cold</em>");
});

test("a star inside a code span is not emphasis", () => {
  expect(markdown("`a * b * c`")).toContain("<code>a * b * c</code>");
});

test("both list flavors, and a switch between them", () => {
  const html = markdown("- one\n- two\n\n1. first\n2. second");
  expect(html).toContain('<ul class="md-list"><li>one</li><li>two</li></ul>');
  expect(html).toContain('<ol class="md-list"><li>first</li><li>second</li></ol>');
});

test("blank lines separate paragraphs, single newlines do not", () => {
  const html = markdown("one line\nsame paragraph\n\nsecond paragraph");
  expect(html).toBe("<p>one line same paragraph</p><p>second paragraph</p>");
});

test("an answer with no markdown at all is one paragraph", () => {
  expect(markdown("Just a sentence.")).toBe("<p>Just a sentence.</p>");
});
