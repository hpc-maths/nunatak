/**
 * Level 3: the detail of one Hotspot - and this is where the roofline
 * lives.
 *
 * The detail substitutes the inventory in the same zone; it never sits
 * beside it - side by side does not reduce scrolling, it shrinks both.
 * Two columns as soon as there is room: the roofline and the metrics on
 * the left, the annotated source and the inline ventilation on the
 * right. A Hotspot that cannot be placed says why in the exact spot
 * where the chart was expected, never a blank.
 */

import type { Derived, HotspotEntry, LoopFacts, Payload } from "./data";
import { downgrades, esc, flops, percent, qualityBadge, resolutionBadge, sig } from "./format";
import { rowQuality } from "./inventory";
import { roofline } from "./roofline";

// A source line carrying at least this share of the Hotspot's samples
// is highlighted as hot.
const HOT_LINE = 0.1;

function metric(label: string, value: string): string {
  return `<div class="metric"><span class="eyebrow">${label}</span><span class="num">${value}</span></div>`;
}

function formatted(quantity: Derived, render: (value: number) => string): string {
  if (quantity.value === null) return '<span class="muted">unavailable</span>';
  return render(quantity.value);
}

function metrics(entry: HotspotEntry): string {
  const cells = [
    metric("Share of time", formatted(entry.share, percent)),
    metric("Achieved", formatted(entry.achieved, flops)),
    metric("Attainable", formatted(entry.attainable, flops)),
    metric(
      "DRAM intensity",
      formatted(entry.dram_intensity, (value) => `${sig(value)} flop/byte`)
    ),
    metric("Imbalance", formatted(entry.imbalance, (value) => `x ${sig(value, 2)}`)),
    metric(
      "Inclusive",
      entry.inclusive !== null
        ? percent(entry.inclusive)
        : '<span class="muted">no recorded paths</span>'
    ),
    metric(
      "Relative error",
      entry.relative_error !== null
        ? `± ${percent(entry.relative_error)}`
        : '<span class="muted">unavailable</span>'
    ),
  ];
  return `<div class="metrics">${cells.join("")}</div>`;
}

function plot(payload: Payload, entry: HotspotEntry): string {
  const chart = roofline(payload, entry);
  if (chart !== null) {
    const fraction =
      entry.envelope_fraction.value !== null
        ? `${percent(entry.envelope_fraction.value)} of the envelope at this intensity. `
        : "";
    return `${chart}<div class="small muted plotnote">${fraction}Pale points are the other placeable Hotspots, for scale.</div>`;
  }
  const reason =
    entry.classification_reason ??
    entry.dram_intensity.reason ??
    "this Hotspot carries no placement";
  return `<div class="noplot">
    <span class="eyebrow">Off the roofline</span>
    <span class="small">Without a DRAM intensity and a FLOP/s rate there is no placement: ${esc(reason)}.</span>
  </div>`;
}

function sourceLines(entry: HotspotEntry): string {
  const source = entry.source;
  const shares = new Map(entry.lines.map((line) => [line.line, line.share]));
  if (source?.text != null && source.start_line !== null) {
    const rows = source.text.split("\n").map((text, index) => {
      const number = source.start_line! + index;
      const share = shares.get(number);
      const hot = share !== undefined && share >= HOT_LINE ? " hot" : "";
      const pc = share !== undefined ? percent(share) : "";
      return `<div class="ln${hot}"><span class="no">${number}</span><span class="pc">${pc}</span><span>${esc(text)}</span></div>`;
    });
    const truncated = source.truncated
      ? '<div class="ln"><span class="no"></span><span class="pc"></span><span class="muted">… extract truncated</span></div>'
      : "";
    return `<div class="src">${rows.join("")}${truncated}</div>`;
  }
  if (entry.lines.length > 0) {
    // No embedded text (--no-source, or the file was not found), but the
    // distribution survives: one still sees where the time goes.
    const reason = source?.reason ?? "no source text embedded in this Run";
    const rows = entry.lines.map(
      (line) =>
        `<div class="ln${line.share >= HOT_LINE ? " hot" : ""}"><span class="no">${line.line}</span><span class="pc">${percent(line.share)}</span><span class="muted">···</span></div>`
    );
    return `<div class="noplot"><span class="eyebrow">Source not shown</span>
      <span class="small">${esc(reason)}. Line numbers and the sample distribution remain.</span>
      <div class="src">${rows.join("")}</div></div>`;
  }
  const reason = source?.reason ?? "attribution did not reach a source line";
  return `<div class="small muted">No source to show: ${esc(reason)}.</div>`;
}

function loopFact(label: string, value: string): string {
  return `<div class="iframe-row"><span>${label}</span><span></span><span class="num pc-right">${value}</span></div>`;
}

function loop(entry: HotspotEntry): string {
  const facts: LoopFacts | null = entry.loop;
  if (facts === null) return "";
  const rows: string[] = [];
  if (facts.vector_ratio !== null) {
    const width =
      facts.vector_width_bits !== null ? ` at ${facts.vector_width_bits} bits` : "";
    rows.push(
      loopFact(
        "Vectorized FP instructions",
        `${percent(facts.vector_ratio)}${width}`
      )
    );
  }
  rows.push(
    loopFact("FLOPs per iteration", sig(facts.flops_per_iteration)),
    loopFact(
      "Bytes per iteration",
      `${facts.loaded_bytes} loaded, ${facts.stored_bytes} stored`
    )
  );
  if (facts.gathers > 0) {
    rows.push(loopFact("Indirect accesses (gather)", String(facts.gathers)));
  }
  if (facts.l1_intensity !== null && facts.l1_intensity.value !== null) {
    rows.push(
      loopFact("L1 intensity", `${sig(facts.l1_intensity.value)} flop/byte`)
    );
  }
  const bounds =
    facts.cycle_bounds !== null
      ? `<div class="small">Cycle bounds per iteration: ${sig(facts.cycle_bounds.ports)} on the ports, ${sig(
          facts.cycle_bounds.steady_state
        )} in steady state - the gap is the dependency chains. <span class="muted">${esc(
          facts.cycle_bounds.reason
        )}.</span></div>`
      : facts.bounds_reason !== null
        ? `<div class="small muted">No cycle bounds: ${esc(facts.bounds_reason)}.</div>`
        : "";
  return `<div><div class="eyebrow blockhead">Hot loop, from the machine code</div>
    <div class="iframe-list">${rows.join("")}</div>
    ${bounds}
    <div class="small muted blocknote">Static analysis of the instruction stream: insensitive to cache reuse, estimated at best - never measured. The L1 intensity is what the code demands; the DRAM intensity beside it is what memory actually served.</div>
  </div>`;
}

function callers(entry: HotspotEntry): string {
  if (entry.callers.length === 0) return "";
  const rows = entry.callers
    .slice(0, 6)
    .map(
      (caller) => `<div class="iframe-row">
        <span class="mono">${esc(caller.name)}</span>
        <span class="bar"><i style="width:${Math.round(caller.share * 100)}%"></i></span>
        <span class="num pc-right">${percent(caller.share)}</span>
      </div>`
    )
    .join("");
  return `<div><div class="eyebrow blockhead">Called from</div>
    <div class="iframe-list">${rows}</div>
    <div class="small muted blocknote">Immediate callers over the recorded paths - what attaches a library leaf to the code that called it. Callers never enter the Hotspot identity.</div>
  </div>`;
}

function inlineFrames(entry: HotspotEntry): string {
  if (entry.inline_frames.length < 2) return "";
  const rows = entry.inline_frames
    .map((frame) => {
      const where =
        frame.file !== null
          ? `${frame.file.split("/").pop()}${frame.line !== null ? `:${frame.line}` : ""}`
          : "";
      return `<div class="iframe-row">
        <span class="mono">${esc(frame.function)} <span class="muted">${esc(where)}</span></span>
        <span class="bar"><i style="width:${Math.round(frame.share * 100)}%"></i></span>
        <span class="num pc-right">${percent(frame.share)}</span>
      </div>`;
    })
    .join("");
  return `<div><div class="eyebrow blockhead">Ventilation by inline frame</div>
    <div class="iframe-list">${rows}</div>
    <div class="small muted blocknote">An inline frame is a line come from another file: detail inside the Hotspot, never a unit of analysis.</div>
  </div>`;
}

/** The full level-3 section for one Hotspot, as HTML. */
export function detail(payload: Payload, entry: HotspotEntry): string {
  const quality = rowQuality(entry);
  const reasons = downgrades(
    entry.share,
    entry.dram_intensity,
    entry.achieved,
    entry.attainable,
    entry.envelope_fraction
  );
  const why = reasons.length
    ? `<div class="why">Downgraded to estimated: ${esc(reasons.join("; "))}.</div>`
    : "";
  const position =
    entry.source_file !== null
      ? `<span class="small mono muted dhead-src">${esc(entry.source_file.split("/").pop() ?? "")}</span>`
      : "";
  return `
  <div class="dhead">
    <button class="back" data-back>← Inventory</button>
    <span class="dname mono">${esc(entry.name)}</span>
    ${resolutionBadge(entry.resolution_level)} ${qualityBadge(quality)}
    ${position}
  </div>
  <div class="dbody">
    <div class="dcol">
      ${why}
      <div>${plot(payload, entry)}</div>
      ${metrics(entry)}
    </div>
    <div class="dcol">
      <div><div class="eyebrow blockhead">Source, samples per line</div>${sourceLines(entry)}</div>
      ${loop(entry)}
      ${callers(entry)}
      ${inlineFrames(entry)}
    </div>
  </div>`;
}
