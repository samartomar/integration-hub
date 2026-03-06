/**
 * Reusable status chip for mapping, contract, and endpoint states.
 * Uses StatusChip under the hood for consistent styling.
 * Labels from getMappingStatusChipDisplay (readinessModel).
 */

import { StatusPill } from "frontend-shared";
import { StatusChip } from "./ui/StatusChip";
import type { StatusVariant } from "./ui/StatusChip";
import {
  getMappingStatusChipDisplay,
  type MappingStatusChipStatus,
} from "../utils/readinessModel";

export type { MappingStatusChipStatus };

export interface MappingStatusChipProps {
  status: MappingStatusChipStatus;
  label?: string;
  title?: string;
  /** When true and status is configured (ok), show only the check icon */
  iconOnlyWhenReady?: boolean;
}

const CONFIGURED_STATUSES: MappingStatusChipStatus[] = ["ok", "ok_canonical_passthrough"];

export function MappingStatusChip({ status, label, title, iconOnlyWhenReady = false }: MappingStatusChipProps) {
  const config = getMappingStatusChipDisplay(status);
  const displayLabel = label ?? config.label;
  const isReady = iconOnlyWhenReady && CONFIGURED_STATUSES.includes(status);

  if (isReady) {
    return (
      <StatusPill
        label={displayLabel}
        variant="configured"
        title={title ?? displayLabel}
        className="shrink-0"
        iconOnlyWhenReady
      />
    );
  }

  return (
    <StatusChip
      label={displayLabel}
      variant={config.variant as StatusVariant}
      title={title ?? displayLabel}
      className="shrink-0"
    />
  );
}

/**
 * Map backend mapping status to chip status.
 * requiresMapping=false + hasMapping=false → warning_optional_missing (pass-through)
 * requiresMapping=true + hasMapping=false → error_required_missing
 * hasMapping=true → ok
 * unknown → not_configured
 */
export function toChipStatus(
  mappingStatus: "ok" | "warning_optional_missing" | "error_required_missing" | undefined
): MappingStatusChipStatus {
  if (!mappingStatus) return "not_configured";
  return mappingStatus as MappingStatusChipStatus;
}
