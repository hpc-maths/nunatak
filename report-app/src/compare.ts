/**
 * The comparison view: the report's three levels applied to a diff.
 *
 * A synthesis of the deltas opens the page, the inventory lists every
 * compared entity - the logical function, inlining included - and the
 * detail of one delta substitutes the inventory in the same zone. The
 * two spec rules are visible everywhere: each displayed difference
 * carries its own sampling error and its verdict, and what is not
 * comparable is declared above the diff, never masked.
 */

import type { CompareDelta, ComparePayload, CompareSide } from "./compare-data";
import { esc, percent } from "./format";

function quantity(value: number, unit: string | null): string {
  if (unit === "ns") return `${(value / 1e9).toPrecision(3).replace(/\.?0+$/, "")} s`;
  const bare = value.toPrecision(3);
  return unit !== null ? `${bare} ${unit}` : bare;
}

function direction(delta: CompareDelta): string {
  if (delta.change === null || !delta.significant) return "cmp-flat";
  return delta.change > 0 ? "cmp-up" : "cmp-down";
}

function changeCell(delta: CompareDelta, unit: string | null): string {
  if (delta.before === null) {
    return `<span class="cmp-flat">appeared at ${quantity(delta.after!.value, unit)}</span>`;
  }
  if (delta.after === null) {
    return `<span class="cmp-flat">vanished (was ${quantity(delta.before.value, unit)})</span>`;
  }
  const fraction =
    delta.change_fraction !== null
      ? `${delta.change_fraction >= 0 ? "+" : "-"}${percent(Math.abs(delta.change_fraction))}`
      : quantity(delta.change!, unit);
  return `<span class="${direction(delta)}">${fraction}</span>`;
}

function verdictCell(delta: CompareDelta): string {
  if (delta.change === null) return '<span class="muted">one side only</span>';
  const error =
    delta.before!.value > 0 && delta.combined_error !== null
      ? percent(delta.combined_error / delta.before!.value)
      : null;
  if (delta.significant) {
    return `significant${error !== null ? ` <span class="muted">(error ±${error})</span>` : ""}`;
  }
  return `<span class="muted">within ±${error ?? "?"}: not a difference</span>`;
}

function findings(payload: ComparePayload): string {
  if (payload.findings.length === 0) return "";
  const rows = payload.findings
    .map((finding) => `<li>${esc(finding.message)}</li>`)
    .join("");
  return `<div class="why">Declared not directly comparable:<ul class="cmp-findings">${rows}</ul></div>`;
}

/** Level 1: the synthesis of the deltas, total first. */
export function compareSynthesis(payload: ComparePayload): string {
  const total = payload.total;
  let sentence: string;
  if (total.before === null || total.after === null || total.change === null) {
    sentence = "the two Runs have no common time base to total";
  } else {
    const fraction =
      total.before.value > 0
        ? ` (${total.change >= 0 ? "+" : ""}${percent(total.change / total.before.value)})`
        : "";
    const verdict = total.significant
      ? "a significant difference"
      : "within the sampling error: not a difference";
    sentence =
      `total sampled time ${quantity(total.before.value, payload.unit)} → ` +
      `${quantity(total.after.value, payload.unit)}${fraction} - ${verdict}`;
  }
  const moved = payload.deltas.filter((delta) => delta.significant);
  const regressed = moved.filter((delta) => (delta.change ?? 0) > 0).length;
  const improved = moved.length - regressed;
  const oneSided = payload.deltas.filter((delta) => delta.change === null).length;
  const counts = [
    `${improved} improved`,
    `${regressed} regressed`,
    `${payload.deltas.length - moved.length - oneSided} unchanged within their error`,
    oneSided > 0 ? `${oneSided} appeared or vanished` : null,
  ]
    .filter((part) => part !== null)
    .join(" · ");
  return `
  <div class="syn">
    <div class="eyebrow">Comparison · ${esc(payload.before.name)} → ${esc(payload.after.name)}</div>
    <div class="headline">${sentence}</div>
    <div class="small muted">${counts}</div>
    ${findings(payload)}
  </div>`;
}

/** Level 2: every compared entity, heaviest first, verdict attached. */
export function compareInventory(payload: ComparePayload): string {
  const rows = payload.deltas
    .map((delta, index) => {
      const where = delta.file !== null ? delta.file.split("/").pop() : "";
      const before =
        delta.before !== null
          ? quantity(delta.before.value, payload.unit)
          : '<span class="muted">-</span>';
      const after =
        delta.after !== null
          ? quantity(delta.after.value, payload.unit)
          : '<span class="muted">-</span>';
      return `
      <tr class="row" data-row="${index}">
        <td><span class="fn">${esc(delta.function)}</span><span class="mod">${esc(where ?? "")}</span></td>
        <td class="r num">${before}</td>
        <td class="r num">${after}</td>
        <td class="r num">${changeCell(delta, payload.unit)}</td>
        <td>${verdictCell(delta)}</td>
      </tr>`;
    })
    .join("");
  return `
  <div class="inv">
    <div class="filters">
      <span class="eyebrow">Compared entities · ${payload.deltas.length} · by logical function, inlining included</span>
    </div>
    <table class="tab">
      <thead><tr><th class="unsortable">Function</th><th class="r unsortable">Before</th><th class="r unsortable">After</th><th class="r unsortable">Change</th><th class="unsortable">Verdict</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="tabfoot small muted">
      <span>Entities below 1% of both Runs are folded away: inlining makes symbols come and go.</span>
    </div>
  </div>`;
}

function side(label: string, one: CompareSide | null, unit: string | null): string {
  if (one === null) {
    return `<div class="metric"><span class="eyebrow">${label}</span><span class="num muted">absent</span></div>`;
  }
  return `<div class="metric"><span class="eyebrow">${label}</span><span class="num">${quantity(
    one.value,
    unit
  )}</span><span class="small muted">${one.samples} samples · sampling error ±${quantity(one.error, unit)}</span></div>`;
}

/** Level 3: one delta, its two sides and the arithmetic of its verdict. */
export function compareDetail(payload: ComparePayload, delta: CompareDelta): string {
  const where = delta.file !== null ? `<span class="small mono muted dhead-src">${esc(delta.file)}</span>` : "";
  let verdict: string;
  if (delta.change === null) {
    verdict =
      delta.before === null
        ? "This entity only exists in the second Run - appeared, which inlining alone can cause."
        : "This entity only exists in the first Run - vanished, which inlining alone can cause.";
  } else {
    const change = quantity(Math.abs(delta.change), payload.unit);
    const error = quantity(delta.combined_error!, payload.unit);
    verdict = delta.significant
      ? `The difference (${change}) exceeds the combined sampling error of its two sides (±${error}): significant.`
      : `The difference (${change}) is smaller than the combined sampling error of its two sides (±${error}): not a difference.`;
  }
  return `
  <div class="dhead">
    <button class="back" data-back>← Compared entities</button>
    <span class="dname mono">${esc(delta.function)}</span>
    ${where}
  </div>
  <div class="dbody">
    <div class="dcol">
      <div class="metrics">
        ${side(`Before (${esc(payload.before.name)})`, delta.before, payload.unit)}
        ${side(`After (${esc(payload.after.name)})`, delta.after, payload.unit)}
      </div>
      <div class="small">${verdict}</div>
    </div>
  </div>`;
}

let view: number | null = null;

function zone(payload: ComparePayload): string {
  const delta = view !== null ? payload.deltas[view] : undefined;
  if (delta !== undefined) return `<div class="det">${compareDetail(payload, delta)}</div>`;
  return compareInventory(payload);
}

function render(payload: ComparePayload): void {
  const root = document.getElementById("nunatak-report");
  if (!root) throw new Error("nunatak-report element missing from the page");
  document.title = `nunatak - ${payload.before.name} vs ${payload.after.name}`;
  root.innerHTML =
    `<div class="shell">${compareSynthesis(payload)}</div>` +
    `${zone(payload)}<div class="shell foot muted small">${esc(
      payload.format.generated_by
    )} · self-contained report, no request leaves this page</div>`;
  for (const opener of document.querySelectorAll<HTMLElement>("[data-row]")) {
    opener.onclick = () => {
      view = Number(opener.dataset.row);
      render(payload);
    };
  }
  for (const button of document.querySelectorAll<HTMLButtonElement>("[data-back]")) {
    button.onclick = () => {
      view = null;
      render(payload);
    };
  }
}

/** Take over the page for a comparison payload. */
export function mountComparison(payload: ComparePayload): void {
  addEventListener("keydown", (event) => {
    if (event.key === "Escape" && view !== null) {
      view = null;
      render(payload);
    }
  });
  render(payload);
}
