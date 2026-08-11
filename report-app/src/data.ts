/**
 * Payload schema 1: the contract with the Python core.
 *
 * These types mirror `nunatak/report/payload.py` field for field. The
 * app renders the payload, it never computes it: every number arrives
 * with its unit, its Quality and its downgrade reason, and an absent
 * quantity is null next to the reason - never zero, never a blank.
 */

export type Quality = "measured" | "estimated" | "unavailable";

export interface Derived {
  value: number | null;
  unit: string;
  quality: Quality;
  lineage: string[];
  formula: string | null;
  reason: string | null;
}

export interface Ceiling {
  name: string;
  value: number;
  unit: string;
  quality: Quality;
  reason: string | null;
}

export interface Machine {
  system: string;
  kernel: string;
  architecture: string;
  cpu_model: string | null;
  logical_cores: number | null;
  allocation: {
    visible_cores: number | null;
    affinity_mask: number[] | null;
    cpu_quota: number | null;
    memory_limit_bytes: number | null;
  };
  ceilings: Ceiling[];
}

export interface SourceExtract {
  file: string;
  resolved_path: string | null;
  start_line: number | null;
  end_line: number | null;
  text: string | null;
  truncated: boolean;
  reason: string | null;
}

export interface LineShare {
  line: number;
  share: number;
}

export interface InlineFrameShare {
  function: string;
  file: string | null;
  line: number | null;
  share: number;
}

export interface HotspotEntry {
  name: string;
  module: string;
  source_file: string | null;
  resolution_level: string;
  classification: string | null;
  classification_reason: string | null;
  relative_error: number | null;
  share: Derived;
  achieved: Derived;
  attainable: Derived;
  envelope_fraction: Derived;
  dram_intensity: Derived;
  imbalance: Derived;
  source: SourceExtract | null;
  lines: LineShare[];
  inline_frames: InlineFrameShare[];
}

export interface Degradation {
  name: string;
  message: string;
  remedy: string | null;
}

export interface Payload {
  format: { name: string; schema: number; generated_by: string };
  run: { name: string; created: string; command: string[]; exit_code: number };
  machine: Machine;
  provenance: {
    commit: string | null;
    dirty_tree: boolean | null;
    dependencies: Record<string, string>;
    effective_configuration: Record<string, unknown>;
  };
  passes: {
    index: number;
    exit_code: number;
    start: string | null;
    end: string | null;
    collectors: { tool: string; version: string }[];
  }[];
  degradations: Degradation[];
  coverage: {
    time_base: string | null;
    samples: number;
    seconds: number | null;
    loci: number;
  };
  floor_samples: number;
  hotspots: HotspotEntry[];
  others: { count: number; share: number | null } | null;
}

/** Read the payload embedded in the page by `nunatak/report/html.py`. */
export function readPayload(): Payload {
  const node = document.getElementById("nunatak-payload");
  if (!node || !node.textContent) {
    throw new Error("nunatak-payload element missing from the page");
  }
  return JSON.parse(node.textContent) as Payload;
}
