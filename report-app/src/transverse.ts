/**
 * The transverse view: time by inline frame, all Hotspots combined.
 *
 * Secondary by design - it sits under the inventory and never replaces
 * it. Its value is what no Hotspot shows alone: the header routine
 * inlined into twelve of them, and a keying by (function, file) that a
 * recompilation cannot move, unlike every view built on the compiler's
 * inlining choices. Absent from the payload, the block does not exist:
 * a run where nothing was inlined has nothing transverse to say.
 */

import type { Payload } from "./data";
import { esc, percent } from "./format";

const SHOWN = 20;

export function transverse(payload: Payload): string {
  const rows = payload.inline_view;
  if (!rows || rows.length === 0) return "";
  const shown = rows.slice(0, SHOWN);
  const body = shown
    .map((row) => {
      const where =
        row.file !== null
          ? `${esc(row.file)}${row.line !== null ? `:${row.line}` : ""}`
          : "";
      const sites =
        row.sites >= 2 ? `<span class="res">in ${row.sites} hotspots</span>` : "";
      return `<tr>
        <td class="mono">${esc(row.function)} ${sites}</td>
        <td class="small muted">${where}</td>
        <td class="num">${percent(row.share)}</td>
      </tr>`;
    })
    .join("");
  const more =
    rows.length > shown.length
      ? `<div class="small muted">and ${rows.length - shown.length} more below ${percent(
          shown[shown.length - 1].share
        )}</div>`
      : "";
  return `<div class="shell trans">
    <span class="eyebrow">By inline frame</span>
    <div class="small muted">Innermost inline frame, all Hotspots combined -
    the only view stable across a recompilation.</div>
    <table class="tab">
      <thead><tr><th>frame</th><th>declared at</th><th class="num">share of time</th></tr></thead>
      <tbody>${body}</tbody>
    </table>
    ${more}
  </div>`;
}
