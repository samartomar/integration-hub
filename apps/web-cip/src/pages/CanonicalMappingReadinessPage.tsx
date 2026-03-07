import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  listCanonicalMappingOnboardingActions,
  generateCanonicalMappingReleaseReport,
  generateCanonicalMappingReleaseMarkdown,
  generateCanonicalReleaseBundle,
  generateCanonicalReleaseBundleMarkdown,
  type MappingOnboardingActionItem,
  type MappingReadinessSummary,
  type MappingReleaseReadinessReport,
  type MappingReleaseBundle,
} from "../api/endpoints";

const STATUS_COLORS: Record<string, string> = {
  READY: "bg-green-100 text-green-800 border-green-200",
  IN_PROGRESS: "bg-amber-100 text-amber-800 border-amber-200",
  MISSING: "bg-red-100 text-red-800 border-red-200",
  WARN: "bg-amber-100 text-amber-800 border-amber-200",
};

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? "bg-gray-100 text-gray-800 border-gray-200";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${cls}`}
    >
      {status}
    </span>
  );
}

function BoolCell({ value }: { value: boolean }) {
  return (
    <span className={value ? "text-green-600" : "text-gray-400"}>
      {value ? "✓" : "—"}
    </span>
  );
}

export function CanonicalMappingReadinessPage() {
  const [searchParams] = useSearchParams();
  const [operationFilter, setOperationFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [targetFilter, setTargetFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [nextActionFilter, setNextActionFilter] = useState("");
  const [selectedItem, setSelectedItem] = useState<MappingOnboardingActionItem | null>(null);
  const [reportResult, setReportResult] = useState<MappingReleaseReadinessReport | null>(null);
  const [markdownResult, setMarkdownResult] = useState<string | null>(null);
  const [selectedForBundle, setSelectedForBundle] = useState<Set<string>>(() => new Set());
  const [bundleResult, setBundleResult] = useState<MappingReleaseBundle | null>(null);
  const [bundleMarkdown, setBundleMarkdown] = useState<string | null>(null);
  const navigate = useNavigate();

  const itemKey = (item: MappingOnboardingActionItem) =>
    `${item.operationCode}|${item.version}|${item.sourceVendor}|${item.targetVendor}`;

  useEffect(() => {
    const op = searchParams.get("operationCode");
    const src = searchParams.get("sourceVendor");
    const tgt = searchParams.get("targetVendor");
    if (op) setOperationFilter(op);
    if (src) setSourceFilter(src);
    if (tgt) setTargetFilter(tgt);
  }, [searchParams]);

  const toggleBundleSelection = (item: MappingOnboardingActionItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const key = itemKey(item);
    setSelectedForBundle((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const reportMutation = useMutation({
    mutationFn: generateCanonicalMappingReleaseReport,
    onSuccess: (res) => {
      setReportResult(res.report ?? null);
      setMarkdownResult(res.markdown ?? null);
    },
    onError: () => {
      setReportResult(null);
      setMarkdownResult(null);
    },
  });

  const markdownMutation = useMutation({
    mutationFn: generateCanonicalMappingReleaseMarkdown,
    onSuccess: (res) => {
      setMarkdownResult(res.markdown ?? null);
    },
    onError: () => setMarkdownResult(null),
  });

  const bundleMutation = useMutation({
    mutationFn: generateCanonicalReleaseBundle,
    onSuccess: (res) => {
      setBundleResult(res.bundle ?? null);
      setBundleMarkdown(res.markdown ?? null);
    },
    onError: () => {
      setBundleResult(null);
      setBundleMarkdown(null);
    },
  });

  const bundleMarkdownMutation = useMutation({
    mutationFn: generateCanonicalReleaseBundleMarkdown,
    onSuccess: (res) => {
      if (res.valid && res.markdown) setBundleMarkdown(res.markdown);
    },
    onError: () => {},
  });

  const clearReport = () => {
    setReportResult(null);
    setMarkdownResult(null);
  };

  const clearBundle = () => {
    setBundleResult(null);
    setBundleMarkdown(null);
  };

  useEffect(() => {
    const op = searchParams.get("operationCode");
    const src = searchParams.get("sourceVendor");
    const tgt = searchParams.get("targetVendor");
    if (op) setOperationFilter(op);
    if (src) setSourceFilter(src);
    if (tgt) setTargetFilter(tgt);
  }, [searchParams]);

  const filters = useMemo(() => {
    const f: Record<string, string> = {};
    if (operationFilter.trim()) f.operationCode = operationFilter.trim();
    if (sourceFilter.trim()) f.sourceVendor = sourceFilter.trim();
    if (targetFilter.trim()) f.targetVendor = targetFilter.trim();
    if (statusFilter.trim()) f.status = statusFilter.trim();
    if (nextActionFilter.trim()) f.nextAction = nextActionFilter.trim();
    return f;
  }, [operationFilter, sourceFilter, targetFilter, statusFilter, nextActionFilter]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["canonical-mapping-onboarding-actions", filters],
    queryFn: () =>
      listCanonicalMappingOnboardingActions(Object.keys(filters).length ? filters : undefined),
  });

  const items = data?.items ?? [];
  const summary: MappingReadinessSummary | null = data?.summary ?? null;

  const selectedItems = useMemo(
    () => items.filter((item) => selectedForBundle.has(itemKey(item))),
    [items, selectedForBundle]
  );

  const runGenerateBundle = () => {
    const bundleName = `Release Candidate ${new Date().toISOString().slice(0, 10)}`;
    const payload = {
      bundleName,
      items: selectedItems.map((i) => ({
        operationCode: i.operationCode,
        version: i.version,
        sourceVendor: i.sourceVendor,
        targetVendor: i.targetVendor,
      })),
    };
    bundleMutation.mutate(payload);
  };

  const runGenerateBundleMarkdown = () => {
    runGenerateBundle();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-gray-900">Mapping Readiness</h1>
        <Link
          to="/admin/syntegris-operator-guide"
          className="text-xs text-slate-600 hover:text-slate-900 hover:underline"
        >
          Operator Guide →
        </Link>
      </div>
      <p className="text-sm text-gray-600">
        Coverage and readiness across operation/vendor-pair mappings. Derived from code-first
        artifacts. Read-only.{" "}
        <Link to="/admin/syntegris-operator-guide" className="text-slate-600 hover:underline">
          Operator Guide
        </Link>
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <div>
          <label htmlFor="op-filter" className="block text-xs font-medium text-gray-700 mb-1">
            Operation
          </label>
          <input
            id="op-filter"
            type="text"
            placeholder="e.g. GET_VERIFY_MEMBER_ELIGIBILITY"
            value={operationFilter}
            onChange={(e) => setOperationFilter(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
          />
        </div>
        <div>
          <label htmlFor="src-filter" className="block text-xs font-medium text-gray-700 mb-1">
            Source Vendor
          </label>
          <input
            id="src-filter"
            type="text"
            placeholder="e.g. LH001"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
          />
        </div>
        <div>
          <label htmlFor="tgt-filter" className="block text-xs font-medium text-gray-700 mb-1">
            Target Vendor
          </label>
          <input
            id="tgt-filter"
            type="text"
            placeholder="e.g. LH002"
            value={targetFilter}
            onChange={(e) => setTargetFilter(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
          />
        </div>
        <div>
          <label htmlFor="status-filter" className="block text-xs font-medium text-gray-700 mb-1">
            Status
          </label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
          >
            <option value="">All</option>
            <option value="READY">READY</option>
            <option value="IN_PROGRESS">IN_PROGRESS</option>
            <option value="MISSING">MISSING</option>
            <option value="WARN">WARN</option>
          </select>
        </div>
        <div>
          <label htmlFor="next-action-filter" className="block text-xs font-medium text-gray-700 mb-1">
            Next Action
          </label>
          <select
            id="next-action-filter"
            value={nextActionFilter}
            onChange={(e) => setNextActionFilter(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
          >
            <option value="">All</option>
            <option value="GENERATE_SCAFFOLD">Generate scaffold</option>
            <option value="ADD_FIXTURES">Add fixtures</option>
            <option value="RUN_CERTIFICATION">Run certification</option>
            <option value="COMPLETE_MAPPING_DEFINITION">Complete mapping</option>
            <option value="INVESTIGATE_WARN">Investigate</option>
            <option value="REVIEW_PROMOTION_ARTIFACT">Review promotion</option>
            <option value="READY">Ready</option>
          </select>
        </div>
      </div>

      {summary && (
        <div className="flex flex-wrap gap-4 p-3 rounded-lg bg-slate-50 border border-slate-200">
          <span className="text-sm text-gray-700">
            <strong>Total:</strong> {summary.total}
          </span>
          <span className="text-sm text-green-700">
            <strong>Ready:</strong> {summary.ready}
          </span>
          <span className="text-sm text-amber-700">
            <strong>In Progress:</strong> {summary.inProgress}
          </span>
          <span className="text-sm text-red-700">
            <strong>Missing:</strong> {summary.missing}
          </span>
          <span className="text-sm text-amber-700">
            <strong>Warn:</strong> {summary.warn}
          </span>
        </div>
      )}

      {!isLoading && !error && selectedForBundle.size > 0 && (
        <div className="flex flex-wrap gap-2 p-2 rounded-lg border border-slate-200 bg-white">
          <span className="text-xs text-gray-600 self-center">
            {selectedForBundle.size} selected for bundle
          </span>
          <button
            type="button"
            onClick={runGenerateBundle}
            disabled={bundleMutation.isPending}
            className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-gray-700 disabled:opacity-50"
          >
            {bundleMutation.isPending ? "Generating…" : "Generate Release Bundle"}
          </button>
          <button
            type="button"
            onClick={runGenerateBundleMarkdown}
            disabled={bundleMutation.isPending}
            className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-gray-700 disabled:opacity-50"
          >
            {bundleMarkdownMutation.isPending ? "Generating…" : "Generate Release Bundle Markdown"}
          </button>
        </div>
      )}

      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {error && (
        <p className="text-sm text-red-600">
          Failed to load readiness. Check your connection.
        </p>
      )}

      {!isLoading && !error && (
        <div className="flex flex-col lg:flex-row gap-4">
          <div className="flex-1 min-w-0 overflow-x-auto">
            <table className="min-w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
              <thead className="bg-slate-100">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-700 w-8">Bundle</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Operation</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Version</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Vendor Pair</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-700">Mapping</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-700">Fixtures</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-700">Cert</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-700">Runtime</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Status</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Next Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {items.length === 0 && (
                  <tr>
                    <td colSpan={10} className="px-3 py-4 text-center text-gray-500">
                      No readiness items match filters.
                    </td>
                  </tr>
                )}
                {items.map((item) => (
                  <tr
                    key={`${item.operationCode}-${item.version}-${item.sourceVendor}-${item.targetVendor}`}
                    onClick={() => {
                      setSelectedItem(item);
                      setReportResult(null);
                      setMarkdownResult(null);
                    }}
                    className={`cursor-pointer hover:bg-slate-50 ${
                      selectedItem === item ? "bg-slate-100" : ""
                    }`}
                  >
                    <td className="px-3 py-2" onClick={(e) => toggleBundleSelection(item, e)}>
                      <input
                        type="checkbox"
                        checked={selectedForBundle.has(itemKey(item))}
                        onChange={() => {}}
                        className="rounded border-gray-300"
                      />
                    </td>
                    <td className="px-3 py-2 font-mono text-gray-900">{item.operationCode}</td>
                    <td className="px-3 py-2 text-gray-700">{item.version}</td>
                    <td className="px-3 py-2 font-mono text-gray-700">
                      {item.sourceVendor} → {item.targetVendor}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <BoolCell value={item.mappingDefinition} />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <BoolCell value={item.fixtures} />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <BoolCell value={item.certification} />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <BoolCell value={item.runtimeReady} />
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          const route = item.nextAction?.targetRoute ?? "/admin/canonical-mappings";
                          navigate(route, { state: { prefill: item.nextAction?.prefill } });
                        }}
                        className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-gray-700"
                      >
                        {item.nextAction?.title ?? item.nextAction?.code ?? "—"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selectedItem && (
            <div className="w-full lg:w-80 shrink-0 p-4 rounded-lg border border-slate-200 bg-slate-50 space-y-2">
              <h3 className="text-sm font-medium text-gray-900">Details</h3>
              <p className="text-xs text-gray-700 font-mono">
                {selectedItem.operationCode} v{selectedItem.version}
              </p>
              <p className="text-xs text-gray-700">
                {selectedItem.sourceVendor} → {selectedItem.targetVendor}
              </p>
              <StatusBadge status={selectedItem.status} />
              {selectedItem.nextAction && (
                <div>
                  <h4 className="text-xs font-medium text-gray-700 mb-1">Next Action</h4>
                  <p className="text-xs text-gray-600 mb-1">{selectedItem.nextAction.title}</p>
                  <button
                    type="button"
                    onClick={() =>
                      navigate(selectedItem.nextAction!.targetRoute, {
                        state: { prefill: selectedItem.nextAction!.prefill },
                      })
                    }
                    className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-gray-700"
                  >
                    Take action
                  </button>
                </div>
              )}
              {selectedItem.status === "READY" && (
                <div className="space-y-1">
                  <h4 className="text-xs font-medium text-gray-700 mb-1">Release Report</h4>
                  <div className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        reportMutation.mutate({
                          operationCode: selectedItem.operationCode,
                          version: selectedItem.version,
                          sourceVendor: selectedItem.sourceVendor,
                          targetVendor: selectedItem.targetVendor,
                        });
                      }}
                      disabled={reportMutation.isPending}
                      className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-gray-700 disabled:opacity-50"
                    >
                      {reportMutation.isPending ? "Generating…" : "Generate Release Report"}
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        markdownMutation.mutate({
                          operationCode: selectedItem.operationCode,
                          version: selectedItem.version,
                          sourceVendor: selectedItem.sourceVendor,
                          targetVendor: selectedItem.targetVendor,
                        });
                      }}
                      disabled={markdownMutation.isPending}
                      className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-gray-700 disabled:opacity-50"
                    >
                      {markdownMutation.isPending ? "Generating…" : "Generate Markdown"}
                    </button>
                  </div>
                </div>
              )}
              {selectedItem.notes?.length ? (
                <div>
                  <h4 className="text-xs font-medium text-gray-700 mb-1">Notes</h4>
                  <ul className="text-xs text-gray-600 list-disc list-inside space-y-0.5">
                    {selectedItem.notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </div>
      )}

      {(reportResult || markdownResult) && (
        <div className="p-4 rounded-lg border border-slate-200 bg-white space-y-3">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-medium text-gray-900">Release Readiness Report</h3>
            <button
              type="button"
              onClick={clearReport}
              className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-gray-700"
            >
              Close
            </button>
          </div>
          {reportResult && (
            <>
              <div className="flex flex-wrap gap-2 text-xs">
                <span
                  className={
                    reportResult.readyForPromotion
                      ? "text-green-700 font-medium"
                      : "text-amber-700 font-medium"
                  }
                >
                  Ready for promotion: {reportResult.readyForPromotion ? "Yes" : "No"}
                </span>
                {reportResult.blockers?.length ? (
                  <div className="w-full">
                    <strong className="text-gray-700">Blockers:</strong>
                    <ul className="list-disc list-inside text-gray-600 mt-0.5">
                      {reportResult.blockers.map((b, i) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
              {reportResult.evidence && (
                <div className="text-xs">
                  <strong className="text-gray-700">Evidence:</strong>
                  <span className="ml-2 text-gray-600">
                    Mapping {reportResult.evidence.mappingDefinition ? "✓" : "✗"} | Fixtures{" "}
                    {reportResult.evidence.fixtures ? "✓" : "✗"} | Cert{" "}
                    {reportResult.evidence.certification ? "✓" : "✗"} | Runtime{" "}
                    {reportResult.evidence.runtimeReady ? "✓" : "✗"}
                  </span>
                </div>
              )}
              {reportResult.releaseChecklist?.length ? (
                <div className="text-xs">
                  <strong className="text-gray-700">Checklist:</strong>
                  <ul className="list-disc list-inside text-gray-600 mt-0.5">
                    {reportResult.releaseChecklist.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <p className="text-xs text-gray-600">
                <strong>Next step:</strong> {reportResult.recommendedNextStep}
              </p>
              {reportResult.notes?.length ? (
                <p className="text-xs text-gray-500 italic">{reportResult.notes[0]}</p>
              ) : null}
            </>
          )}
          {markdownResult && (
            <details className="text-xs">
              <summary className="cursor-pointer text-gray-700 font-medium">Markdown artifact</summary>
              <pre className="mt-2 p-3 rounded bg-slate-100 overflow-x-auto text-xs whitespace-pre-wrap">
                {markdownResult}
              </pre>
            </details>
          )}
        </div>
      )}

      {bundleResult && (
        <div className="p-4 rounded-lg border border-slate-200 bg-white space-y-3">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-medium text-gray-900">Release Bundle</h3>
            <button
              type="button"
              onClick={clearBundle}
              className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-gray-700"
            >
              Close
            </button>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span
              className={
                bundleResult.summary?.status === "READY"
                  ? "text-green-700 font-medium"
                  : "text-amber-700 font-medium"
              }
            >
              Status: {bundleResult.summary?.status ?? "N/A"} (included: {bundleResult.summary?.included ?? 0}, ready: {bundleResult.summary?.ready ?? 0}, blocked: {bundleResult.summary?.blocked ?? 0})
            </span>
          </div>
          {bundleResult.items?.length ? (
            <div className="text-xs">
              <strong className="text-gray-700">Included:</strong>
              <ul className="list-disc list-inside text-gray-600 mt-0.5">
                {bundleResult.items.map((it, i) => (
                  <li key={i}>
                    {it.operationCode} v{it.version} {it.sourceVendor} → {it.targetVendor}{" "}
                    {it.readyForPromotion ? "✓" : "✗"}
                    {it.blockers?.length ? ` (${it.blockers.join("; ")})` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {bundleResult.impactedFiles?.length ? (
            <div className="text-xs">
              <strong className="text-gray-700">Impacted files:</strong>
              <ul className="list-disc list-inside text-gray-600 mt-0.5 font-mono">
                {bundleResult.impactedFiles.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {bundleResult.verificationChecklist?.length ? (
            <div className="text-xs">
              <strong className="text-gray-700">Verification checklist:</strong>
              <ul className="list-disc list-inside text-gray-600 mt-0.5">
                {bundleResult.verificationChecklist.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {bundleResult.notes?.length ? (
            <p className="text-xs text-gray-500 italic">{bundleResult.notes[0]}</p>
          ) : null}
          {bundleMarkdown && (
            <details className="text-xs" open>
              <summary className="cursor-pointer text-gray-700 font-medium">Markdown artifact</summary>
              <pre className="mt-2 p-3 rounded bg-slate-100 overflow-x-auto text-xs whitespace-pre-wrap">
                {bundleMarkdown}
              </pre>
            </details>
          )}
        </div>
      )}

      {data?.notes?.length ? (
        <p className="text-xs text-gray-500 italic">{data.notes[0]}</p>
      ) : null}
    </div>
  );
}
