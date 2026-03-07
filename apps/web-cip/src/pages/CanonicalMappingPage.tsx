import { useCallback, useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  listCanonicalMappingOperations,
  previewCanonicalMapping,
  validateCanonicalMapping,
  suggestCanonicalMapping,
  compareCanonicalMapping,
  generateCanonicalMappingProposalPackage,
  generateCanonicalMappingProposalMarkdown,
  generateCanonicalMappingPromotionArtifact,
  generateCanonicalMappingPromotionMarkdown,
  certifyCanonicalMapping,
  generateCanonicalMappingScaffoldBundle,
  generateCanonicalMappingScaffoldMarkdown,
  type CanonicalMappingOperationItem,
  type CanonicalMappingPreviewResponse,
  type CanonicalMappingValidateResponse,
  type CanonicalMappingSuggestResponse,
  type MappingProposalResponse,
  type MappingPromotionResponse,
  type MappingCertificationResponse,
  type MappingScaffoldResponse,
} from "../api/endpoints";

function JsonBlock({
  data,
  label,
}: {
  data: Record<string, unknown> | null;
  label?: string;
}) {
  const text = data ? JSON.stringify(data, null, 2) : "";
  if (!data || Object.keys(data).length === 0) {
    return <p className="text-sm text-gray-500 italic">—</p>;
  }
  return (
    <div>
      {label && <span className="text-xs font-medium text-gray-600 block mb-1">{label}</span>}
      <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-4 overflow-x-auto border border-gray-200 font-mono">
        {text}
      </pre>
    </div>
  );
}

export function CanonicalMappingPage() {
  const [selectedOp, setSelectedOp] = useState<CanonicalMappingOperationItem | null>(null);
  const [sourceVendor, setSourceVendor] = useState("LH001");
  const [targetVendor, setTargetVendor] = useState("LH002");
  const [direction, setDirection] = useState<"CANONICAL_TO_VENDOR" | "VENDOR_TO_CANONICAL">(
    "CANONICAL_TO_VENDOR"
  );
  const [inputJson, setInputJson] = useState("{}");
  const [previewResult, setPreviewResult] = useState<CanonicalMappingPreviewResponse | null>(null);
  const [validateResult, setValidateResult] = useState<CanonicalMappingValidateResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [suggestWithAi, setSuggestWithAi] = useState(false);
  const [suggestResult, setSuggestResult] = useState<CanonicalMappingSuggestResponse | null>(null);
  const [compareResult, setCompareResult] = useState<{
    comparison: { unchanged: unknown[]; added: unknown[]; changed: unknown[] };
    notes: string[];
  } | null>(null);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isComparing, setIsComparing] = useState(false);
  const [proposalPackageResult, setProposalPackageResult] = useState<MappingProposalResponse | null>(null);
  const [proposalMarkdown, setProposalMarkdown] = useState<string | null>(null);
  const [isGeneratingPackage, setIsGeneratingPackage] = useState(false);
  const [isGeneratingMarkdown, setIsGeneratingMarkdown] = useState(false);
  const [promotionArtifactResult, setPromotionArtifactResult] = useState<MappingPromotionResponse | null>(null);
  const [promotionMarkdown, setPromotionMarkdown] = useState<string | null>(null);
  const [isGeneratingPromotionArtifact, setIsGeneratingPromotionArtifact] = useState(false);
  const [isGeneratingPromotionMarkdown, setIsGeneratingPromotionMarkdown] = useState(false);
  const [certificationResult, setCertificationResult] = useState<MappingCertificationResponse | null>(null);
  const [isCertifying, setIsCertifying] = useState(false);
  const [scaffoldResult, setScaffoldResult] = useState<MappingScaffoldResponse | null>(null);
  const [scaffoldMarkdown, setScaffoldMarkdown] = useState<string | null>(null);
  const [isGeneratingScaffoldBundle, setIsGeneratingScaffoldBundle] = useState(false);
  const [isGeneratingScaffoldMarkdown, setIsGeneratingScaffoldMarkdown] = useState(false);

  const { data: opsData, isLoading: opsLoading, error: opsError } = useQuery({
    queryKey: ["canonical-mapping-operations"],
    queryFn: listCanonicalMappingOperations,
  });

  const items = opsData?.items ?? [];
  const hasSelection = !!selectedOp;
  const location = useLocation();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const prefill =
      (location.state as { prefill?: { operationCode?: string; version?: string; sourceVendor?: string; targetVendor?: string } } | null)
        ?.prefill ?? null;
    const opFromQ = searchParams.get("operationCode");
    const srcFromQ = searchParams.get("sourceVendor");
    const tgtFromQ = searchParams.get("targetVendor");
    const verFromQ = searchParams.get("version");
    const fromState = prefill?.operationCode || opFromQ;
    const src = prefill?.sourceVendor || srcFromQ || "";
    const tgt = prefill?.targetVendor || tgtFromQ || "";
    const ver = prefill?.version || verFromQ || "1.0";
    if (fromState && items.length > 0) {
      const opCode = (fromState as string).trim().toUpperCase();
      const op = items.find(
        (o) => (o.operationCode || "").toUpperCase() === opCode && (o.version || "1.0") === (ver || "1.0")
      );
      if (op) {
        setSelectedOp(op);
      }
      if (src) setSourceVendor(src);
      if (tgt) setTargetVendor(tgt);
    }
  }, [location.state, searchParams, items]);

  useEffect(() => {
    const prefill = (location.state as { prefill?: object } | null)?.prefill;
    if (prefill) return;
    if (selectedOp && items.length > 0) {
      const op = items.find(
        (o) => o.operationCode === selectedOp.operationCode && o.version === selectedOp.version
      );
      const pair = op?.vendorPairs?.[0];
      if (pair) {
        setSourceVendor(pair.sourceVendor || "LH001");
        setTargetVendor(pair.targetVendor || "LH002");
      }
    }
  }, [selectedOp, items, location.state]);

  const getExampleForDirection = useCallback(() => {
    if (!selectedOp) return {};
    const pair = selectedOp.vendorPairs?.[0];
    if (!pair) return {};
    if (direction === "CANONICAL_TO_VENDOR") {
      if (selectedOp.operationCode === "GET_VERIFY_MEMBER_ELIGIBILITY") {
        return { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" };
      }
      if (selectedOp.operationCode === "GET_MEMBER_ACCUMULATORS") {
        return { memberIdWithPrefix: "LH001-12345", asOfDate: "2025-03-06" };
      }
    } else {
      if (selectedOp.operationCode === "GET_VERIFY_MEMBER_ELIGIBILITY") {
        return {
          memberIdWithPrefix: "LH001-12345",
          name: "Jane Doe",
          dob: "1990-01-15",
          claimNumber: "CLM-789",
          dateOfService: "2025-03-06",
          status: "ACTIVE",
        };
      }
      if (selectedOp.operationCode === "GET_MEMBER_ACCUMULATORS") {
        return {
          memberIdWithPrefix: "LH001-12345",
          planYear: 2025,
          currency: "USD",
          individualDeductible: { total: 2000, used: 500, remaining: 1500 },
          familyDeductible: { total: 4000, used: 500, remaining: 3500 },
          individualOutOfPocket: { total: 8000, used: 1200, remaining: 6800 },
          familyOutOfPocket: { total: 16000, used: 1200, remaining: 14800 },
        };
      }
    }
    return {};
  }, [selectedOp, direction]);

  useEffect(() => {
    if (hasSelection) {
      setInputJson(JSON.stringify(getExampleForDirection(), null, 2));
    }
  }, [selectedOp?.operationCode, direction, hasSelection]);

  const handlePreview = useCallback(async () => {
    if (!selectedOp) return;
    setIsPreviewing(true);
    setApiError(null);
    setPreviewResult(null);
    setValidateResult(null);
    try {
      const payload = JSON.parse(inputJson);
      const result = await previewCanonicalMapping({
        operationCode: selectedOp.operationCode,
        version: selectedOp.version,
        sourceVendor,
        targetVendor,
        direction,
        inputPayload: payload,
      });
      setPreviewResult(result);
    } catch (err: unknown) {
      if (err instanceof SyntaxError) {
        setApiError("Invalid JSON in input payload");
      } else {
        const msg =
          err && typeof err === "object" && "response" in err
            ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
                ?.error?.message ?? "Preview request failed"
            : String(err);
        setApiError(msg);
      }
    } finally {
      setIsPreviewing(false);
    }
  }, [selectedOp, sourceVendor, targetVendor, direction, inputJson]);

  const handleValidate = useCallback(async () => {
    if (!selectedOp) return;
    setIsValidating(true);
    setApiError(null);
    setValidateResult(null);
    setPreviewResult(null);
    try {
      const payload = JSON.parse(inputJson);
      const result = await validateCanonicalMapping({
        operationCode: selectedOp.operationCode,
        version: selectedOp.version,
        sourceVendor,
        targetVendor,
        direction,
        inputPayload: payload,
      });
      setValidateResult(result);
    } catch (err: unknown) {
      if (err instanceof SyntaxError) {
        setApiError("Invalid JSON in input payload");
      } else {
        const msg =
          err && typeof err === "object" && "response" in err
            ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
                ?.error?.message ?? "Validation request failed"
            : String(err);
        setApiError(msg);
      }
    } finally {
      setIsValidating(false);
    }
  }, [selectedOp, sourceVendor, targetVendor, direction, inputJson]);

  const handleSuggest = useCallback(async () => {
    if (!selectedOp) return;
    setIsSuggesting(true);
    setApiError(null);
    setSuggestResult(null);
    setCompareResult(null);
    setProposalPackageResult(null);
    setProposalMarkdown(null);
    setProposalPackageResult(null);
    setProposalMarkdown(null);
    setProposalPackageResult(null);
    setProposalMarkdown(null);
    try {
      let inputPayload: Record<string, unknown> | undefined;
      try {
        inputPayload = JSON.parse(inputJson) as Record<string, unknown>;
      } catch {
        inputPayload = undefined;
      }
      const result = await suggestCanonicalMapping({
        operationCode: selectedOp.operationCode,
        version: selectedOp.version,
        sourceVendor,
        targetVendor,
        direction,
        suggestWithAi,
        inputPayload,
      });
      setSuggestResult(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Suggest request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsSuggesting(false);
    }
  }, [selectedOp, sourceVendor, targetVendor, direction, suggestWithAi, inputJson]);

  const handleCompare = useCallback(async () => {
    if (!suggestResult?.aiSuggestion?.proposedFieldMappings?.length) {
      setApiError("Run Suggest Mapping with AI enabled first to compare.");
      return;
    }
    setIsComparing(true);
    setApiError(null);
    setCompareResult(null);
    try {
      const definition = suggestResult.existingMappingDefinition ?? {};
      const result = await compareCanonicalMapping({
        definition,
        suggestion: { proposedFieldMappings: suggestResult.aiSuggestion!.proposedFieldMappings },
      });
      setCompareResult(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Compare request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsComparing(false);
    }
  }, [suggestResult]);

  const handleGeneratePackage = useCallback(async () => {
    if (!suggestResult || !selectedOp) return;
    setIsGeneratingPackage(true);
    setApiError(null);
    setProposalPackageResult(null);
    try {
      const result = await generateCanonicalMappingProposalPackage({
        operationCode: selectedOp.operationCode,
        version: selectedOp.version,
        sourceVendor,
        targetVendor,
        direction,
        deterministicBaseline: suggestResult.deterministicBaseline,
        aiSuggestion: suggestResult.aiSuggestion,
        comparison: suggestResult.comparison ?? compareResult?.comparison,
        notes: suggestResult.notes,
      });
      setProposalPackageResult(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Proposal package request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsGeneratingPackage(false);
    }
  }, [suggestResult, compareResult, selectedOp, sourceVendor, targetVendor, direction]);

  const handleGenerateMarkdown = useCallback(async () => {
    if (!suggestResult || !selectedOp) return;
    setIsGeneratingMarkdown(true);
    setApiError(null);
    setProposalMarkdown(null);
    try {
      const result = await generateCanonicalMappingProposalMarkdown({
        operationCode: selectedOp.operationCode,
        version: selectedOp.version,
        sourceVendor,
        targetVendor,
        direction,
        deterministicBaseline: suggestResult.deterministicBaseline,
        aiSuggestion: suggestResult.aiSuggestion,
        comparison: suggestResult.comparison ?? compareResult?.comparison,
        notes: suggestResult.notes,
      });
      setProposalMarkdown(result.markdown ?? "");
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Proposal markdown request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsGeneratingMarkdown(false);
    }
  }, [suggestResult, compareResult, selectedOp, sourceVendor, targetVendor, direction]);

  const handleCopyMarkdown = useCallback(() => {
    if (!proposalMarkdown) return;
    void navigator.clipboard.writeText(proposalMarkdown);
  }, [proposalMarkdown]);

  const handleGeneratePromotionArtifact = useCallback(async () => {
    if (!proposalPackageResult?.proposalPackage) return;
    setIsGeneratingPromotionArtifact(true);
    setApiError(null);
    setPromotionArtifactResult(null);
    try {
      const result = await generateCanonicalMappingPromotionArtifact({
        proposalPackage: proposalPackageResult.proposalPackage,
      });
      setPromotionArtifactResult(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Promotion artifact request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsGeneratingPromotionArtifact(false);
    }
  }, [proposalPackageResult]);

  const handleGeneratePromotionMarkdown = useCallback(async () => {
    if (!proposalPackageResult?.proposalPackage) return;
    setIsGeneratingPromotionMarkdown(true);
    setApiError(null);
    setPromotionMarkdown(null);
    try {
      const result = await generateCanonicalMappingPromotionMarkdown({
        proposalPackage: proposalPackageResult.proposalPackage,
      });
      setPromotionMarkdown(result.markdown ?? "");
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Promotion markdown request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsGeneratingPromotionMarkdown(false);
    }
  }, [proposalPackageResult]);

  const handleCopyPromotionMarkdown = useCallback(() => {
    if (!promotionMarkdown) return;
    void navigator.clipboard.writeText(promotionMarkdown);
  }, [promotionMarkdown]);

  const handleRunCertification = useCallback(async () => {
    if (!selectedOp) return;
    setIsCertifying(true);
    setApiError(null);
    setCertificationResult(null);
    try {
      const result = await certifyCanonicalMapping({
        operationCode: selectedOp.operationCode,
        version: selectedOp.version,
        sourceVendor,
        targetVendor,
        direction,
      });
      setCertificationResult(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Certification request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsCertifying(false);
    }
  }, [selectedOp, sourceVendor, targetVendor, direction]);

  const handleGenerateScaffoldBundle = useCallback(async () => {
    if (!selectedOp) return;
    setIsGeneratingScaffoldBundle(true);
    setApiError(null);
    setScaffoldResult(null);
    try {
      const result = await generateCanonicalMappingScaffoldBundle({
        operationCode: selectedOp.operationCode,
        version: selectedOp.version,
        sourceVendor,
        targetVendor,
        directions: ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"],
      });
      setScaffoldResult(result);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Scaffold bundle request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsGeneratingScaffoldBundle(false);
    }
  }, [selectedOp, sourceVendor, targetVendor]);

  const handleGenerateScaffoldMarkdown = useCallback(async () => {
    if (!selectedOp) return;
    setIsGeneratingScaffoldMarkdown(true);
    setApiError(null);
    setScaffoldMarkdown(null);
    try {
      const result = await generateCanonicalMappingScaffoldMarkdown({
        operationCode: selectedOp.operationCode,
        version: selectedOp.version,
        sourceVendor,
        targetVendor,
        directions: ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"],
      });
      setScaffoldMarkdown(result.markdown ?? "");
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { error?: { message?: string } } } }).response?.data
              ?.error?.message ?? "Scaffold markdown request failed"
          : String(err);
      setApiError(msg);
    } finally {
      setIsGeneratingScaffoldMarkdown(false);
    }
  }, [selectedOp, sourceVendor, targetVendor]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">Canonical Mappings</h1>
      <p className="text-sm text-gray-600">
        Preview and validate deterministic Canonical ↔ Vendor transforms. No runtime execution.
      </p>

      <div className="flex flex-col lg:flex-row gap-4">
        <div className="w-full lg:w-64 shrink-0">
          <h2 className="text-sm font-medium text-gray-700 mb-2">Operations</h2>
          {opsLoading && <p className="text-sm text-gray-500">Loading…</p>}
          {opsError && (
            <p className="text-sm text-red-600">Failed to load operations.</p>
          )}
          {!opsLoading && !opsError && items.length === 0 && (
            <p className="text-sm text-gray-500">No mapping definitions available.</p>
          )}
          {!opsLoading && items.length > 0 && (
            <ul className="border border-gray-200 rounded-lg divide-y divide-gray-200 bg-white">
              {items.map((op) => (
                <li key={`${op.operationCode}-${op.version}`}>
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedOp({
                        operationCode: op.operationCode,
                        version: op.version,
                        title: op.title,
                        vendorPairs: op.vendorPairs,
                      })
                    }
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 ${
                      selectedOp?.operationCode === op.operationCode
                        ? "bg-slate-100 text-slate-900 font-medium"
                        : "text-gray-700"
                    }`}
                  >
                    {op.title || op.operationCode}
                    <span className="block text-xs text-gray-500">
                      {op.operationCode} · {op.version}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex-1 min-w-0 space-y-4">
          {!hasSelection && (
            <div className="border border-gray-200 rounded-lg p-8 bg-gray-50 text-center text-gray-500 text-sm">
              Select an operation to preview or validate mappings.
            </div>
          )}
          {hasSelection && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="source-vendor" className="block text-sm text-gray-700 mb-1">
                    Source Vendor
                  </label>
                  <input
                    id="source-vendor"
                    type="text"
                    value={sourceVendor}
                    onChange={(e) => setSourceVendor(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
                  />
                </div>
                <div>
                  <label htmlFor="target-vendor" className="block text-sm text-gray-700 mb-1">
                    Target Vendor
                  </label>
                  <input
                    id="target-vendor"
                    type="text"
                    value={targetVendor}
                    onChange={(e) => setTargetVendor(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label htmlFor="direction" className="block text-sm text-gray-700 mb-1">
                    Direction
                  </label>
                  <select
                    id="direction"
                    value={direction}
                    onChange={(e) =>
                      setDirection(e.target.value as "CANONICAL_TO_VENDOR" | "VENDOR_TO_CANONICAL")
                    }
                    className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
                  >
                    <option value="CANONICAL_TO_VENDOR">CANONICAL_TO_VENDOR</option>
                    <option value="VENDOR_TO_CANONICAL">VENDOR_TO_CANONICAL</option>
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <label htmlFor="input-payload" className="block text-sm text-gray-700 mb-1">
                    Input payload (JSON)
                  </label>
                  <textarea
                    id="input-payload"
                    value={inputJson}
                    onChange={(e) => setInputJson(e.target.value)}
                    rows={12}
                    className="w-full px-2 py-1.5 text-sm font-mono border border-gray-200 rounded-md"
                    spellCheck={false}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-2 items-center">
                <button
                  type="button"
                  onClick={handlePreview}
                  disabled={isPreviewing || isValidating}
                  className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 disabled:opacity-50 rounded-lg"
                >
                  {isPreviewing ? "Previewing…" : "Preview Mapping"}
                </button>
                <button
                  type="button"
                  onClick={handleValidate}
                  disabled={isPreviewing || isValidating}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isValidating ? "Validating…" : "Validate Mapping"}
                </button>
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={suggestWithAi}
                    onChange={(e) => setSuggestWithAi(e.target.checked)}
                    className="rounded border-gray-300"
                  />
                  Suggest with AI
                </label>
                <button
                  type="button"
                  onClick={handleSuggest}
                  disabled={isSuggesting || isComparing}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isSuggesting ? "Suggesting…" : "Suggest Mapping"}
                </button>
                <button
                  type="button"
                  onClick={handleCompare}
                  disabled={isComparing || isSuggesting || !suggestResult?.aiSuggestion?.proposedFieldMappings?.length}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isComparing ? "Comparing…" : "Compare Suggestion"}
                </button>
                <button
                  type="button"
                  onClick={handleGeneratePackage}
                  disabled={isGeneratingPackage || isGeneratingMarkdown || !suggestResult}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isGeneratingPackage ? "Generating…" : "Generate Proposal Package"}
                </button>
                <button
                  type="button"
                  onClick={handleGenerateMarkdown}
                  disabled={isGeneratingPackage || isGeneratingMarkdown || !suggestResult}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isGeneratingMarkdown ? "Generating…" : "Generate Proposal Markdown"}
                </button>
                <button
                  type="button"
                  onClick={handleGeneratePromotionArtifact}
                  disabled={
                    isGeneratingPromotionArtifact ||
                    isGeneratingPromotionMarkdown ||
                    !proposalPackageResult?.proposalPackage
                  }
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isGeneratingPromotionArtifact ? "Generating…" : "Generate Promotion Artifact"}
                </button>
                <button
                  type="button"
                  onClick={handleGeneratePromotionMarkdown}
                  disabled={
                    isGeneratingPromotionArtifact ||
                    isGeneratingPromotionMarkdown ||
                    !proposalPackageResult?.proposalPackage
                  }
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isGeneratingPromotionMarkdown ? "Generating…" : "Generate Promotion Markdown"}
                </button>
                <button
                  type="button"
                  onClick={handleRunCertification}
                  disabled={isCertifying}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isCertifying ? "Running…" : "Run Certification"}
                </button>
                <button
                  type="button"
                  onClick={handleGenerateScaffoldBundle}
                  disabled={isGeneratingScaffoldBundle || !selectedOp}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isGeneratingScaffoldBundle ? "Generating…" : "Generate Scaffold Bundle"}
                </button>
                <button
                  type="button"
                  onClick={handleGenerateScaffoldMarkdown}
                  disabled={isGeneratingScaffoldMarkdown || !selectedOp}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 rounded-lg border border-slate-300"
                >
                  {isGeneratingScaffoldMarkdown ? "Generating…" : "Generate Scaffold Markdown"}
                </button>
              </div>

              {apiError && (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200">
                  <p className="text-sm text-red-800">{apiError}</p>
                </div>
              )}

              {previewResult && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">Preview Result</h3>
                  <div
                    className={`p-2 rounded ${
                      previewResult.valid ? "bg-green-50 border border-green-200" : "bg-amber-50 border border-amber-200"
                    }`}
                  >
                    <span className="text-sm font-medium">
                      {previewResult.valid ? "Valid" : "Invalid"}
                    </span>
                  </div>
                  {previewResult.mappingDefinitionSummary && (
                    <p className="text-xs text-gray-600">
                      Field mappings: {previewResult.mappingDefinitionSummary.fieldMappings},
                      constants: {previewResult.mappingDefinitionSummary.constants}
                      {previewResult.mappingDefinitionSummary.warnings?.length
                        ? ` · Warnings: ${previewResult.mappingDefinitionSummary.warnings.join(", ")}`
                        : ""}
                    </p>
                  )}
                  <JsonBlock data={previewResult.outputPayload} label="Output payload" />
                  {previewResult.errors?.length ? (
                    <ul className="text-sm text-amber-700 list-disc list-inside">
                      {previewResult.errors.map((e, i) => (
                        <li key={i}>{typeof e === "string" ? e : (e as { message?: string }).message}</li>
                      ))}
                    </ul>
                  ) : null}
                  {previewResult.notes?.length ? (
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {previewResult.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              {validateResult && !previewResult && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">Validation Result</h3>
                  <div
                    className={`p-2 rounded ${
                      validateResult.valid ? "bg-green-50 border border-green-200" : "bg-amber-50 border border-amber-200"
                    }`}
                  >
                    <span className="text-sm font-medium">
                      {validateResult.valid ? "Valid" : "Invalid"}
                    </span>
                    {validateResult.mappingAvailable !== undefined && (
                      <span className="block text-xs">
                        Mapping available: {validateResult.mappingAvailable ? "Yes" : "No"}
                      </span>
                    )}
                  </div>
                  {validateResult.warnings?.length ? (
                    <ul className="text-sm text-amber-700 list-disc list-inside">
                      {validateResult.warnings.map((w, i) => (
                        <li key={i}>{typeof w === "string" ? w : (w as { message?: string }).message}</li>
                      ))}
                    </ul>
                  ) : null}
                  {validateResult.notes?.length ? (
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {validateResult.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              {suggestResult && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">Mapping Suggestion</h3>
                  <div className="space-y-2">
                    <h4 className="text-xs font-medium text-gray-700">Deterministic Baseline</h4>
                    <p className="text-xs text-gray-600">
                      Field mappings: {suggestResult.deterministicBaseline.fieldMappings}, constants:{" "}
                      {suggestResult.deterministicBaseline.constants}
                    </p>
                    {suggestResult.deterministicBaseline.warnings?.length ? (
                      <ul className="text-xs text-amber-700 list-disc list-inside">
                        {suggestResult.deterministicBaseline.warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                  {suggestResult.aiSuggestion && (
                    <div className="space-y-2 pt-2 border-t border-gray-200">
                      <h4 className="text-xs font-medium text-gray-700">AI Suggestion (advisory only)</h4>
                      {suggestResult.aiSuggestion.summary && (
                        <p className="text-xs text-gray-600">{suggestResult.aiSuggestion.summary}</p>
                      )}
                      <p className="text-xs text-gray-500">
                        Confidence: {suggestResult.aiSuggestion.confidence}
                      </p>
                      {suggestResult.aiSuggestion.proposedFieldMappings?.length ? (
                        <ul className="text-xs text-gray-700 list-disc list-inside">
                          {suggestResult.aiSuggestion.proposedFieldMappings.map((m, i) => (
                            <li key={i}>
                              {m.from} → {m.to}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      {suggestResult.aiSuggestion.warnings?.length ? (
                        <ul className="text-xs text-amber-700 list-disc list-inside">
                          {suggestResult.aiSuggestion.warnings.map((w, i) => (
                            <li key={i}>{w}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  )}
                  {suggestResult.comparison && (
                    <div className="space-y-2 pt-2 border-t border-gray-200">
                      <h4 className="text-xs font-medium text-gray-700">Comparison</h4>
                      {suggestResult.comparison.unchanged?.length ? (
                        <p className="text-xs text-gray-600">
                          Unchanged: {suggestResult.comparison.unchanged.length}
                        </p>
                      ) : null}
                      {suggestResult.comparison.added?.length ? (
                        <p className="text-xs text-green-700">Added: {suggestResult.comparison.added.length}</p>
                      ) : null}
                      {suggestResult.comparison.changed?.length ? (
                        <p className="text-xs text-amber-700">Changed: {suggestResult.comparison.changed.length}</p>
                      ) : null}
                    </div>
                  )}
                  {suggestResult.notes?.length ? (
                    <ul className="text-xs text-gray-600 list-disc list-inside pt-2 border-t border-gray-200">
                      {suggestResult.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              {compareResult && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">Compare Result</h3>
                  <div className="space-y-2">
                    {compareResult.comparison.unchanged?.length ? (
                      <div>
                        <h4 className="text-xs font-medium text-gray-700">Unchanged</h4>
                        <ul className="text-xs text-gray-600 list-disc list-inside">
                          {compareResult.comparison.unchanged.map((u, i) => (
                            <li key={i}>
                              {typeof u === "object" && u !== null && "from" in u && "to" in u
                                ? `${(u as { from: string; to: string }).from} → ${(u as { from: string; to: string }).to}`
                                : JSON.stringify(u)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {compareResult.comparison.added?.length ? (
                      <div>
                        <h4 className="text-xs font-medium text-green-700">Added</h4>
                        <ul className="text-xs text-gray-600 list-disc list-inside">
                          {compareResult.comparison.added.map((a, i) => (
                            <li key={i}>
                              {typeof a === "object" && a !== null && "from" in a && "to" in a
                                ? `${(a as { from: string; to: string }).from} → ${(a as { from: string; to: string }).to}`
                                : JSON.stringify(a)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {compareResult.comparison.changed?.length ? (
                      <div>
                        <h4 className="text-xs font-medium text-amber-700">Changed</h4>
                        <ul className="text-xs text-gray-600 list-disc list-inside">
                          {compareResult.comparison.changed.map((c, i) => (
                            <li key={i}>
                              {typeof c === "object" && c !== null
                                ? "suggestedFrom" in c
                                  ? `${(c as { from: string; to: string }).from} → ${(c as { from: string; to: string }).to} (suggested: ${(c as { suggestedFrom?: string }).suggestedFrom})`
                                  : JSON.stringify(c)
                                : JSON.stringify(c)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                  {compareResult.notes?.length ? (
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {compareResult.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              {proposalPackageResult?.proposalPackage && (
                <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">Proposal Package (Review Artifact Only)</h3>
                  <p className="text-xs text-gray-600 italic">
                    No runtime mapping was changed. This is a review artifact for human promotion.
                  </p>
                  <div className="space-y-2">
                    <p className="text-xs text-gray-700">
                      <strong>Proposal ID:</strong> {proposalPackageResult.proposalPackage.proposalId}
                    </p>
                    <p className="text-xs text-gray-700">
                      {proposalPackageResult.proposalPackage.operationCode} v
                      {proposalPackageResult.proposalPackage.version} ·{" "}
                      {proposalPackageResult.proposalPackage.sourceVendor} →{" "}
                      {proposalPackageResult.proposalPackage.targetVendor}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <h4 className="text-xs font-medium text-gray-700">Review Checklist</h4>
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {proposalPackageResult.proposalPackage.reviewChecklist?.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="space-y-1">
                    <h4 className="text-xs font-medium text-gray-700">Promotion Guidance</h4>
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {proposalPackageResult.proposalPackage.promotionGuidance?.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                  {proposalPackageResult.proposalPackage.notes?.length ? (
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {proposalPackageResult.proposalPackage.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              {proposalMarkdown && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-2">
                  <div className="flex justify-between items-center">
                    <h3 className="text-sm font-medium text-gray-900">Proposal Markdown (Export)</h3>
                    <button
                      type="button"
                      onClick={handleCopyMarkdown}
                      className="px-2 py-1 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded border border-slate-300"
                    >
                      Copy
                    </button>
                  </div>
                  <pre className="text-xs text-gray-700 bg-white rounded p-4 overflow-x-auto border border-gray-200 font-mono whitespace-pre-wrap">
                    {proposalMarkdown}
                  </pre>
                </div>
              )}

              {promotionArtifactResult?.promotionArtifact && (
                <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">
                    Promotion Artifact (Review-Only / Manual Apply)
                  </h3>
                  <p className="text-xs text-gray-600 italic">
                    Code-first review artifact. No mapping definition was changed. Apply manually.
                  </p>
                  <div className="space-y-2">
                    <p className="text-xs text-gray-700">
                      <strong>Target Definition File:</strong>{" "}
                      <code className="bg-slate-200 px-1 rounded">
                        {promotionArtifactResult.promotionArtifact.targetDefinitionFile}
                      </code>
                    </p>
                    <div className="space-y-1">
                      <h4 className="text-xs font-medium text-gray-700">Recommended Changes</h4>
                      <p className="text-xs text-gray-600">
                        Unchanged: {promotionArtifactResult.promotionArtifact.recommendedChanges?.unchanged?.length ?? 0}
                        {" · "}
                        Added: {promotionArtifactResult.promotionArtifact.recommendedChanges?.added?.length ?? 0}
                        {" · "}
                        Changed: {promotionArtifactResult.promotionArtifact.recommendedChanges?.changed?.length ?? 0}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-xs font-medium text-gray-700">Review Checklist</h4>
                      <ul className="text-xs text-gray-600 list-disc list-inside">
                        {promotionArtifactResult.promotionArtifact.reviewChecklist?.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="space-y-1">
                      <h4 className="text-xs font-medium text-gray-700">Test Checklist</h4>
                      <ul className="text-xs text-gray-600 list-disc list-inside">
                        {promotionArtifactResult.promotionArtifact.testChecklist?.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                    {promotionArtifactResult.pythonSnippet && (
                      <div className="space-y-1">
                        <h4 className="text-xs font-medium text-gray-700">Python Snippet</h4>
                        <pre className="text-xs text-gray-700 bg-white rounded p-3 overflow-x-auto border border-slate-200 font-mono whitespace-pre-wrap">
                          {promotionArtifactResult.pythonSnippet}
                        </pre>
                      </div>
                    )}
                    {promotionArtifactResult.promotionArtifact.notes?.length ? (
                      <ul className="text-xs text-gray-600 list-disc list-inside">
                        {promotionArtifactResult.promotionArtifact.notes.map((n, i) => (
                          <li key={i}>{n}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                </div>
              )}

              {promotionMarkdown && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-2">
                  <div className="flex justify-between items-center">
                    <h3 className="text-sm font-medium text-gray-900">
                      Promotion Markdown (Review-Only / Manual Apply)
                    </h3>
                    <button
                      type="button"
                      onClick={handleCopyPromotionMarkdown}
                      className="px-2 py-1 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded border border-slate-300"
                    >
                      Copy
                    </button>
                  </div>
                  <pre className="text-xs text-gray-700 bg-white rounded p-4 overflow-x-auto border border-gray-200 font-mono whitespace-pre-wrap">
                    {promotionMarkdown}
                  </pre>
                </div>
              )}

              {scaffoldResult && scaffoldResult.scaffoldBundle && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">
                    Scaffold Bundle (Onboarding / Review-Only — No Automatic Apply)
                  </h3>
                  <p className="text-xs text-gray-600">
                    Artifact for onboarding new vendor-pair mappings. Deterministic mappings remain authoritative.
                  </p>
                  <div className="space-y-2">
                    <h4 className="text-xs font-medium text-gray-700">File Paths</h4>
                    <ul className="text-xs text-gray-600 space-y-1 font-mono">
                      <li>Definition: {scaffoldResult.scaffoldBundle.mappingDefinitionFile}</li>
                      <li>Fixture: {scaffoldResult.scaffoldBundle.fixtureFile}</li>
                      <li>Test: {scaffoldResult.scaffoldBundle.testFile}</li>
                    </ul>
                  </div>
                  {scaffoldResult.mappingDefinitionStub && (
                    <div className="space-y-1">
                      <h4 className="text-xs font-medium text-gray-700">Mapping Definition Stub</h4>
                      <pre className="text-xs text-gray-700 bg-white rounded p-3 overflow-x-auto border border-slate-200 font-mono whitespace-pre-wrap">
                        {scaffoldResult.mappingDefinitionStub}
                      </pre>
                    </div>
                  )}
                  {scaffoldResult.fixtureStub && (
                    <div className="space-y-1">
                      <h4 className="text-xs font-medium text-gray-700">Fixture Stub</h4>
                      <pre className="text-xs text-gray-700 bg-white rounded p-3 overflow-x-auto border border-slate-200 font-mono whitespace-pre-wrap">
                        {scaffoldResult.fixtureStub}
                      </pre>
                    </div>
                  )}
                  {scaffoldResult.testStub && (
                    <div className="space-y-1">
                      <h4 className="text-xs font-medium text-gray-700">Test Stub</h4>
                      <pre className="text-xs text-gray-700 bg-white rounded p-3 overflow-x-auto border border-slate-200 font-mono whitespace-pre-wrap">
                        {scaffoldResult.testStub}
                      </pre>
                    </div>
                  )}
                  {scaffoldResult.scaffoldBundle.reviewChecklist?.length ? (
                    <div className="space-y-1">
                      <h4 className="text-xs font-medium text-gray-700">Review Checklist</h4>
                      <ul className="text-xs text-gray-600 list-disc list-inside">
                        {scaffoldResult.scaffoldBundle.reviewChecklist.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {scaffoldResult.notes?.length ? (
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {scaffoldResult.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              {scaffoldMarkdown && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-2">
                  <h3 className="text-sm font-medium text-gray-900">
                    Scaffold Markdown (Onboarding / Review-Only)
                  </h3>
                  <pre className="text-xs text-gray-700 bg-white rounded p-4 overflow-x-auto border border-gray-200 font-mono whitespace-pre-wrap">
                    {scaffoldMarkdown}
                  </pre>
                </div>
              )}

              {certificationResult && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">
                    Certification (Fixture-Based Verification Only)
                  </h3>
                  <div
                    className={`p-2 rounded ${
                      certificationResult.summary.status === "PASS"
                        ? "bg-green-50 border border-green-200"
                        : certificationResult.summary.status === "WARN"
                          ? "bg-amber-50 border border-amber-200"
                          : "bg-red-50 border border-red-200"
                    }`}
                  >
                    <span className="text-sm font-medium">
                      {certificationResult.summary.status}: Passed {certificationResult.summary.passed}, Failed{" "}
                      {certificationResult.summary.failed}
                      {certificationResult.summary.warnings > 0
                        ? `, Warnings ${certificationResult.summary.warnings}`
                        : ""}
                    </span>
                  </div>
                  <div className="space-y-2">
                    <h4 className="text-xs font-medium text-gray-700">Fixture Results</h4>
                    <ul className="space-y-1">
                      {certificationResult.results?.map((r, i) => (
                        <li
                          key={i}
                          className={`text-xs flex items-center gap-2 ${
                            r.status === "PASS" ? "text-green-700" : "text-red-700"
                          }`}
                        >
                          <span className="font-mono">{r.fixtureId}</span>
                          <span>{r.status}</span>
                          {r.notes?.length ? (
                            <span className="text-gray-600">— {r.notes.join(" ")}</span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                  {certificationResult.notes?.length ? (
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {certificationResult.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              {compareResult && !suggestResult && (
                <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 space-y-3">
                  <h3 className="text-sm font-medium text-gray-900">Compare Result</h3>
                  {compareResult.comparison && (
                    <div className="text-xs space-y-1">
                      <p className="text-green-700">
                        Unchanged: {(compareResult.comparison.unchanged ?? []).length}
                      </p>
                      <p className="text-blue-700">Added: {(compareResult.comparison.added ?? []).length}</p>
                      <p className="text-amber-700">Changed: {(compareResult.comparison.changed ?? []).length}</p>
                    </div>
                  )}
                  {compareResult.notes?.length ? (
                    <ul className="text-xs text-gray-600 list-disc list-inside">
                      {compareResult.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
