/**
 * Compare payload schema 1: the contract with `nunatak compare`.
 *
 * The exact JSON the verb prints for a CI is what the page embeds: one
 * payload, two consumers, no drift. Values are in `unit` - "ns" for a
 * clock base, null when the two Runs do not share one (a finding says
 * so); `significant` is computed by the core, never re-derived here.
 */

export interface CompareSide {
  value: number;
  samples: number;
  error: number;
}

export interface CompareDelta {
  function: string;
  file: string | null;
  before: CompareSide | null;
  after: CompareSide | null;
  change: number | null;
  change_fraction: number | null;
  combined_error: number | null;
  significant: boolean;
}

export interface ComparePayload {
  format: { name: string; schema: number; generated_by: string };
  before: { run: string; name: string };
  after: { run: string; name: string };
  unit: string | null;
  findings: { name: string; message: string }[];
  total: CompareDelta;
  deltas: CompareDelta[];
}
