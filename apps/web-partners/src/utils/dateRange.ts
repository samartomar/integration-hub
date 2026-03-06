/**
 * Utility for stable date ranges. Compute from/to strings only when range changes.
 */

const isoSlice = (d: Date) => d.toISOString().slice(0, 19) + "Z";

export function toISORange(to: Date, rangeHours: number): { fromStr: string; toStr: string } {
  const from = new Date(to.getTime() - rangeHours * 60 * 60 * 1000);
  return { fromStr: isoSlice(from), toStr: isoSlice(to) };
}

export function toISORangeDays(to: Date, rangeDays: number): { fromStr: string; toStr: string } {
  const from = new Date(to);
  from.setDate(from.getDate() - rangeDays);
  return { fromStr: isoSlice(from), toStr: isoSlice(to) };
}

/** Preset time ranges for Flows/transactions list. */
export const FLOWS_TIME_RANGES = [
  { label: "Last 15 minutes", getRange: (to: Date) => toISORange(to, 15 / 60) },
  { label: "Last hour", getRange: (to: Date) => toISORange(to, 1) },
  { label: "Last 24 hours", getRange: (to: Date) => toISORange(to, 24) },
  { label: "Last 7 days", getRange: (to: Date) => toISORangeDays(to, 7) },
] as const;

/** Preset time ranges for Flows list (Milestone 3): 24h default, 7d, 30d. */
export const FLOWS_TIME_RANGES_M3 = [
  { label: "Last 24h", getRange: (to: Date) => toISORange(to, 24) },
  { label: "Last 7d", getRange: (to: Date) => toISORangeDays(to, 7) },
  { label: "Last 30d", getRange: (to: Date) => toISORangeDays(to, 30) },
] as const;
