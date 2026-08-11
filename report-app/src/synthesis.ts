/**
 * Level 1: the written synthesis - where to start.
 *
 * Findings ordered by decreasing share of the sampled time, each with
 * its quantified evidence, closed by "what this report does not say".
 * The synthesis contains no chart: it states and cites its numbers, the
 * roofline lives in the Hotspot detail (level 3). Sampling coverage is
 * stated at the head, never relegated to an appendix.
 */

import type { HotspotEntry, Payload } from "./data";
import { downgrades, esc, flops, percent, resolutionBadge, sig } from "./format";

// The Ceilings the roofline envelope is built from - the only ones
// whose uncertainty belongs in the synthesis.
const ENVELOPE_CEILINGS = ["flops_dp", "dram_bandwidth"];

function coverageSentence(payload: Payload): string {
  const coverage = payload.coverage;
  if (coverage.time_base === null) {
    return "This Run carries no time-base counter: shares of time cannot be stated.";
  }
  let sentence = `${coverage.samples} samples of ${esc(coverage.time_base)}`;
  if (coverage.seconds !== null) {
    sentence += ` over ${sig(coverage.seconds)} s`;
  }
  const loci = coverage.loci === 1 ? "1 locus" : `${coverage.loci} loci`;
  return `${sentence}, across ${loci}.`;
}

function headline(payload: Payload): string {
  const hotspots = payload.hotspots;
  if (hotspots.length === 0) {
    return `No Hotspot rises above the statistical floor of ${payload.floor_samples} samples.`;
  }
  const covered = hotspots.reduce((sum, entry) => sum + (entry.share.value ?? 0), 0);
  const count = hotspots.length === 1 ? "1 Hotspot" : `${hotspots.length} Hotspots`;
  const verb = hotspots.length === 1 ? "holds" : "hold";
  return `${count} above the statistical floor ${verb} ${percent(Math.min(covered, 1))} of the sampled time.`;
}

function verdict(entry: HotspotEntry): string {
  const name = `<span class="mono">${esc(entry.name)}</span>`;
  if (entry.classification !== null) {
    return `${name} is ${esc(entry.classification)}.`;
  }
  return `${name} cannot be placed on the roofline: ${esc(entry.classification_reason ?? "no placement")}.`;
}

function evidence(entry: HotspotEntry): string[] {
  const lines: string[] = [];
  if (entry.achieved.value !== null && entry.attainable.value !== null) {
    let line = `Achieved <strong>${flops(entry.achieved.value)}</strong> of ${flops(entry.attainable.value)} attainable`;
    if (entry.envelope_fraction.value !== null) {
      line += `: ${percent(entry.envelope_fraction.value)} of the envelope`;
    }
    lines.push(line + ".");
  }
  if (entry.dram_intensity.value !== null) {
    lines.push(`DRAM intensity ${sig(entry.dram_intensity.value)} flop/byte.`);
  }
  if (entry.classification === "imbalance" && entry.imbalance.value !== null) {
    lines.push(
      `The most-loaded Locus carries <strong>${entry.imbalance.value.toFixed(1)}x</strong> the least-loaded.`
    );
  }
  const hottest = entry.lines.reduce(
    (top, line) => (line.share > (top?.share ?? 0) ? line : top),
    null as { line: number; share: number } | null
  );
  if (hottest !== null && entry.source_file !== null && hottest.share >= 0.5) {
    const file = entry.source_file.split("/").pop() ?? entry.source_file;
    lines.push(
      `Line ${hottest.line} of <span class="mono">${esc(file)}</span> concentrates <strong>${percent(hottest.share)}</strong> of its samples.`
    );
  }
  return lines;
}

function finding(entry: HotspotEntry, rank: number): string {
  const shareLabel =
    entry.share.value !== null ? ` · ${percent(entry.share.value)} of the sampled time` : "";
  const evidenceLines = evidence(entry)
    .map((line) => `<div>${line}</div>`)
    .join("");
  const reasons = downgrades(
    entry.share,
    entry.dram_intensity,
    entry.achieved,
    entry.attainable,
    entry.envelope_fraction
  );
  const downgrade = reasons.length
    ? `<div class="why">Downgraded to estimated: ${esc(reasons.join("; "))}.</div>`
    : "";
  return `
  <div class="finding">
    <span class="rank">Finding ${rank}${shareLabel}</span>
    <div class="verdict">${verdict(entry)} ${resolutionBadge(entry.resolution_level)}</div>
    <div class="ev">${evidenceLines}${downgrade}</div>
    <button class="golink" data-go="${rank - 1}">Open the Hotspot and its roofline →</button>
  </div>`;
}

function admissions(payload: Payload): string[] {
  const items: string[] = [];
  if (payload.others !== null) {
    const spread = payload.others.count === 1 ? "1 Hotspot" : `${payload.others.count} Hotspots`;
    const share =
      payload.others.share !== null ? `<strong>${percent(payload.others.share)} of the sampled time</strong> sits` : "An unknown share of the time sits";
    items.push(
      `${share} below the statistical floor of ${payload.floor_samples} samples: ${spread}, aggregated as "others". Totals are preserved, the detail is not.`
    );
  }
  const unresolved = payload.hotspots
    .filter((entry) => entry.resolution_level === "unresolved")
    .reduce((sum, entry) => sum + (entry.share.value ?? 0), 0);
  if (unresolved > 0) {
    items.push(
      `<strong>${percent(unresolved)} of the sampled time is attributed to no name</strong>: addresses that no symbol claims.`
    );
  }
  for (const ceiling of payload.machine.ceilings) {
    if (ENVELOPE_CEILINGS.includes(ceiling.name) && ceiling.quality === "estimated") {
      items.push(
        `<strong>The ${esc(ceiling.name)} Ceiling is estimated</strong>: ${esc(ceiling.reason ?? "no reason recorded")}.`
      );
    }
  }
  for (const degradation of payload.degradations) {
    let item = `<strong>Degraded [${esc(degradation.name)}]</strong>: ${esc(degradation.message)}.`;
    if (degradation.remedy) item += ` ${esc(degradation.remedy)}.`;
    items.push(item);
  }
  return items;
}

/** The full level-1 section, as HTML. */
export function synthesis(payload: Payload): string {
  const findings = payload.hotspots
    .map((entry, index) => finding(entry, index + 1))
    .join("");
  const admitted = admissions(payload);
  const negativeSpace = admitted.length
    ? `
  <div class="neg">
    <h2>What this report does not say</h2>
    <div class="ev ev-negative">${admitted.map((item) => `<div>${item}</div>`).join("")}</div>
  </div>`
    : "";
  return `
  <div class="syn">
    <div>
      <span class="eyebrow">Synthesis</span>
      <h1>${headline(payload)}</h1>
      <p class="muted coverage">${coverageSentence(payload)}</p>
    </div>
    ${findings}${negativeSpace}
  </div>`;
}
