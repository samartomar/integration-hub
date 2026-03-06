export interface ExecuteCatalogOperation {
  operationCode: string;
  description?: string;
  canonicalVersion?: string;
  aiPresentationMode?: string;
}

export interface ExecuteSupportedOperation {
  operationCode: string;
  isActive?: boolean;
}

export interface ExecuteAllowlistOutbound {
  sourceVendor: string;
  targetVendor: string;
  operation: string;
}

export interface ExecuteReadinessItem {
  operationCode: string;
  partnerVendorCode: string;
  direction: "outbound" | "inbound";
  status: "ready" | "needs_setup" | "needs_attention" | "admin_pending";
}

export interface ExecuteSelectionInput {
  activeVendorCode: string;
  catalog: ExecuteCatalogOperation[];
  supportedOperations: ExecuteSupportedOperation[];
  outboundAllowlist: ExecuteAllowlistOutbound[];
  outboundReadiness: ExecuteReadinessItem[];
  allVendorCodes: string[];
}

export interface ExecuteSelectionResult {
  operations: ExecuteCatalogOperation[];
  targetsByOperation: Record<string, string[]>;
}

function toCode(value: string | undefined | null): string {
  return String(value ?? "").trim().toUpperCase();
}

export function buildExecuteSelectionModel(input: ExecuteSelectionInput): ExecuteSelectionResult {
  const activeVendor = toCode(input.activeVendorCode);

  const supportedSet = new Set(
    input.supportedOperations
      .filter((s) => s.isActive !== false)
      .map((s) => toCode(s.operationCode))
      .filter(Boolean)
  );

  const outboundRules = input.outboundAllowlist
    .map((r) => ({
      sourceVendor: toCode(r.sourceVendor),
      targetVendor: toCode(r.targetVendor),
      operation: toCode(r.operation),
    }))
    .filter((r) => r.sourceVendor === activeVendor && !!r.operation);

  const opTargetMap = new Map<string, Set<string>>();
  for (const row of outboundRules) {
    if (!opTargetMap.has(row.operation)) opTargetMap.set(row.operation, new Set<string>());
    opTargetMap.get(row.operation)!.add(row.targetVendor);
  }

  const readinessMap = new Map<string, Set<string>>();
  for (const row of input.outboundReadiness) {
    const op = toCode(row.operationCode);
    const partner = toCode(row.partnerVendorCode);
    if (!op || !partner) continue;
    if (String(row.direction || "").toLowerCase() !== "outbound") continue;
    if (String(row.status || "").toLowerCase() !== "ready") continue;
    if (!readinessMap.has(op)) readinessMap.set(op, new Set<string>());
    readinessMap.get(op)!.add(partner);
  }

  const ops: ExecuteCatalogOperation[] = [];
  const targetsByOperation: Record<string, string[]> = {};

  for (const op of input.catalog) {
    const opCode = toCode(op.operationCode);
    if (!opCode || !supportedSet.has(opCode)) continue;
    if (!opTargetMap.has(opCode)) continue;

    const allowedTargets = Array.from(opTargetMap.get(opCode) ?? []).filter(
      (v) => !!v && v !== activeVendor
    );

    const readyTargets = allowedTargets
      .filter((target) => readinessMap.get(opCode)?.has(target))
      .sort();

    if (readyTargets.length === 0) continue;

    ops.push(op);
    targetsByOperation[opCode] = readyTargets;
  }

  return { operations: ops, targetsByOperation };
}
