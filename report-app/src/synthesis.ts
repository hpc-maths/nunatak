/**
 * Level 1: the written synthesis - where to start.
 *
 * Findings ordered by decreasing share of the sampled time, each with
 * its quantified evidence, closed by "what this report does not say".
 * The synthesis contains no chart: it states and cites its numbers, the
 * roofline lives in the Hotspot detail (level 3). Sampling coverage is
 * stated at the head, never relegated to an appendix.
 */

import type { HotspotEntry, Payload, RankRow, RanksSection } from "./data";
import { downgrades, esc, flops, percent, resolutionBadge, sig } from "./format";

// Beyond this many rank rows the table stops and says so: a
// thousand-rank table reads as noise, the extremes carry the story.
const MAX_RANK_ROWS = 32;

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

function ranksSentence(section: RanksSection): string {
  const sampled = section.rows.filter((row) => row.sampled).length;
  const world = section.rows.length === 1 ? "1 rank" : `${section.rows.length} ranks`;
  let sentence = `${world} (${sampled} sampled)`;
  if (section.imbalance.value !== null) {
    sentence += `; the busiest rank runs <strong>${section.imbalance.value.toFixed(2)}x</strong> the mean`;
  }
  if (section.mpi_fraction.value !== null) {
    sentence += `; MPI holds <strong>${percent(section.mpi_fraction.value)}</strong> of the time`;
  }
  return sentence + ".";
}

function rankRow(row: RankRow): string {
  const seconds = row.time.value !== null ? sig(row.time.value / 1e9) : "unavailable";
  const share =
    row.mpi_time.value !== null && row.time.value
      ? percent(Math.min(row.mpi_time.value / row.time.value, 1))
      : "unavailable";
  const layer = row.sampled ? "sampled" : "counted";
  return `
    <tr>
      <td class="r">${row.rank}</td>
      <td class="mono">${esc(row.node)}</td>
      <td class="r">${seconds}</td>
      <td class="r">${share}</td>
      <td>${layer}</td>
    </tr>`;
}

function ranksBlock(payload: Payload): string {
  const section = payload.ranks;
  if (section === null) {
    return "";
  }
  const ordered = [...section.rows].sort(
    (a, b) => (b.time.value ?? -1) - (a.time.value ?? -1)
  );
  const shown = ordered.slice(0, MAX_RANK_ROWS);
  const more =
    ordered.length > shown.length
      ? `<p class="muted">... and ${ordered.length - shown.length} more ranks, ordered by time.</p>`
      : "";
  return `
  <div class="ranks">
    <h2>Ranks</h2>
    <p>${ranksSentence(section)}</p>
    <table class="tab">
      <thead>
        <tr>
          <th class="r unsortable">Rank</th>
          <th class="unsortable">Node</th>
          <th class="r unsortable">Time (s)</th>
          <th class="r unsortable">MPI share</th>
          <th class="unsortable">Layer</th>
        </tr>
      </thead>
      <tbody>${shown.map(rankRow).join("")}</tbody>
    </table>
    ${more}
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
  if (payload.ranks !== null && payload.ranks.unsampled.length > 0) {
    const listed = payload.ranks.unsampled.slice(0, 8).join(", ");
    const ellipsis = payload.ranks.unsampled.length > 8 ? ", ..." : "";
    const count =
      payload.ranks.unsampled.length === 1
        ? "1 rank was"
        : `${payload.ranks.unsampled.length} ranks were`;
    items.push(
      `<strong>${count} not sampled</strong> (${listed}${ellipsis}): their Hotspot measurements are unavailable, never extrapolated.`
    );
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
    ${findings}${ranksBlock(payload)}${negativeSpace}
  </div>`;
}
