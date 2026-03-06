/**
 * Persist time range per operation for Flow Details.
 * Key: flowTimeRange:{operationCode}, Value: "24h" | "7d" | "30d"
 * Aligns with FLOWS_TIME_RANGES_M3 indices (0=24h, 1=7d, 2=30d).
 */

const STORAGE_PREFIX = "flowTimeRange:";
const VALID_RANGES = ["24h", "7d", "30d"] as const;
export type FlowTimeRangeLabel = (typeof VALID_RANGES)[number];

export const TIME_RANGE_INDEX_TO_LABEL: Record<number, FlowTimeRangeLabel> = {
  0: "24h",
  1: "7d",
  2: "30d",
};

export function getStoredFlowTimeRange(
  operationCode: string
): FlowTimeRangeLabel | null {
  if (!operationCode?.trim()) return null;
  try {
    const key = `${STORAGE_PREFIX}${operationCode}`;
    const v = localStorage.getItem(key);
    if (v && VALID_RANGES.includes(v as FlowTimeRangeLabel)) {
      return v as FlowTimeRangeLabel;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function setStoredFlowTimeRange(
  operationCode: string,
  range: FlowTimeRangeLabel
): void {
  if (!operationCode?.trim()) return;
  try {
    const key = `${STORAGE_PREFIX}${operationCode}`;
    localStorage.setItem(key, range);
  } catch {
    /* ignore */
  }
}
