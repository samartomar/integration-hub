import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  listCanonicalMappingReadiness,
  type MappingReadinessItem,
  type MappingReadinessSummary,
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
  const [operationFilter, setOperationFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [targetFilter, setTargetFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedItem, setSelectedItem] = useState<MappingReadinessItem | null>(null);

  const filters = useMemo(() => {
    const f: Record<string, string> = {};
    if (operationFilter.trim()) f.operationCode = operationFilter.trim();
    if (sourceFilter.trim()) f.sourceVendor = sourceFilter.trim();
    if (targetFilter.trim()) f.targetVendor = targetFilter.trim();
    if (statusFilter.trim()) f.status = statusFilter.trim();
    return f;
  }, [operationFilter, sourceFilter, targetFilter, statusFilter]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["canonical-mapping-readiness", filters],
    queryFn: () => listCanonicalMappingReadiness(Object.keys(filters).length ? filters : undefined),
  });

  const items = data?.items ?? [];
  const summary: MappingReadinessSummary | null = data?.summary ?? null;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">Mapping Readiness</h1>
      <p className="text-sm text-gray-600">
        Coverage and readiness across operation/vendor-pair mappings. Derived from code-first
        artifacts. Read-only.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
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
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Operation</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Version</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Vendor Pair</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-700">Mapping</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-700">Fixtures</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-700">Cert</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-700">Runtime</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {items.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-4 text-center text-gray-500">
                      No readiness items match filters.
                    </td>
                  </tr>
                )}
                {items.map((item) => (
                  <tr
                    key={`${item.operationCode}-${item.version}-${item.sourceVendor}-${item.targetVendor}`}
                    onClick={() => setSelectedItem(item)}
                    className={`cursor-pointer hover:bg-slate-50 ${
                      selectedItem === item ? "bg-slate-100" : ""
                    }`}
                  >
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

      {data?.notes?.length ? (
        <p className="text-xs text-gray-500 italic">{data.notes[0]}</p>
      ) : null}
    </div>
  );
}
