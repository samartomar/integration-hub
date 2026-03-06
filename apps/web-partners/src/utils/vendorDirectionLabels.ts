/**
 * Vendor-specific direction helpers.
 * Single vocabulary: OUTBOUND / INBOUND only. No "I send" / "I receive".
 */

import { READY_FOR_TRAFFIC_LABEL, type FlowReadinessRow } from "./readinessModel";

/** Table row direction label: raw OUTBOUND or INBOUND */
export function getDirectionLabelWithPolicy(
  direction: "Inbound" | "Outbound",
  _directionPolicy?: string
): string {
  return direction === "Outbound" ? "OUTBOUND" : "INBOUND";
}

/** Tooltip for Direction cell: flow direction only */
export function getDirectionCellTooltip(
  direction: "Inbound" | "Outbound",
  _directionPolicy?: string
): string {
  return direction === "Outbound" ? "OUTBOUND" : "INBOUND";
}

/** Ready-for-traffic label (no direction suffix). */
export function getReadyForTrafficLabel(_rows: FlowReadinessRow[]): string {
  return READY_FOR_TRAFFIC_LABEL;
}

/** Augment mapReadinessToDisplay label when "Ready for traffic" with direction context. */
export function augmentReadyLabel(
  baseLabel: string,
  baseVariant: string,
  baseTooltip: string | undefined,
  rows: FlowReadinessRow[]
): { label: string; variant: string; tooltip?: string } {
  if (baseLabel !== READY_FOR_TRAFFIC_LABEL) {
    return { label: baseLabel, variant: baseVariant, tooltip: baseTooltip };
  }
  return {
    label: getReadyForTrafficLabel(rows),
    variant: baseVariant,
    tooltip: baseTooltip,
  };
}

export { getDirectionPolicyLabel, getDirectionPolicyConstraintTooltip } from "frontend-shared";
