/**
 * Pill for Flow readiness dimensions: Configured, Partial, Missing.
 * Uses shared StatusPill. Labels from getFlowDimensionLabel (readinessModel).
 */

import { StatusPill, type StatusPillVariant } from "frontend-shared";
import {
  getFlowDimensionLabel,
  type FlowDimensionStatus,
} from "../utils/readinessModel";

const VARIANTS: Record<FlowDimensionStatus, StatusPillVariant> = {
  configured: "configured",
  partial: "warning",
  missing: "error",
};

export interface FlowReadinessPillProps {
  status: FlowDimensionStatus;
  className?: string;
  title?: string;
}

export function FlowReadinessPill({ status, className = "", title }: FlowReadinessPillProps) {
  return (
    <StatusPill
      label={getFlowDimensionLabel(status)}
      variant={VARIANTS[status]}
      className={className}
      title={title}
    />
  );
}
