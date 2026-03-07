/** Syntegris Adoption Workbench - full picture of existing inventory and adoption state. */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  listSyntegrisAdoption,
  getSyntegrisAdoptionSummary,
  type SyntegrisAdoptionItem,
  type SyntegrisAdoptionSummary,
} from "../api/endpoints";

const ADOPTION_STATUS_COLORS: Record<string, string> = {
  LEGACY_ONLY: "bg-slate-100 text-slate-800 border-slate-200",
  CANON_DEFINED: "bg-blue-100 text-blue-800 border-blue-200",
  MAPPING_IN_PROGRESS: "bg-amber-100 text-amber-800 border-amber-200",
  CERTIFIED: "bg-teal-100 text-teal-800 border-teal-200",
  RELEASE_READY: "bg-indigo-100 text-indigo-800 border-indigo-200",
  SYNTEGRIS_READY: "bg-green-100 text-green-800 border-green-200",
  BLOCKED: "bg-red-100 text-red-800 border-red-200",
};

const STATUS_DISPLAY_LABELS: Record<string, string> = {
  SYNTEGRIS_READY: "Ready",
};

function StatusBadge({ status }: { status: string }) {
  const cls = ADOPTION_STATUS_COLORS[status] ?? "bg-gray-100 text-gray-800 border-gray-200";
  const label = STATUS_DISPLAY_LABELS[status] ?? status;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${cls}`}>
      {label}
    </span>
  );
}

function BoolCell({ value }: { value: boolean }) {
  return <span className={value ? "text-green-600" : "text-gray-400"}>{value ? "✓" : "—"}</span>;
}

const DEEP_LINK_ROUTES = [
  { label: "Canonical Mappings", path: "/admin/canonical-mappings" },
  { label: "Mapping Readiness", path: "/admin/canonical-mapping-readiness" },
  { label: "Flow Builder", path: "/admin/flow-builder" },
  { label: "Runtime Preflight", path: "/admin/runtime-preflight" },
  { label: "Canonical Execute", path: "/admin/canonical-execute" },
  { label: "Operator Guide", path: "/admin/syntegris-operator-guide" },
];

function buildDeepLink(path: string, item: SyntegrisAdoptionItem): string {
  const params = new URLSearchParams();
  params.set("operationCode", item.operationCode);
  params.set("version", item.version);
  params.set("sourceVendor", item.sourceVendor);
  params.set("targetVendor", item.targetVendor);
  return `${path}?${params.toString()}`;
}

export function SyntegrisAdoptionWorkbenchPage() {
  const [operationFilter, setOperationFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [targetFilter, setTargetFilter] = useState("");
  const [adoptionStatusFilter, setAdoptionStatusFilter] = useState("");
  const [nextActionFilter, setNextActionFilter] = useState("");
  const [selectedItem, setSelectedItem] = useState<SyntegrisAdoptionItem | null>(null);

  const filters = useMemo(() => {
    const f: Record<string, string> = {};
    if (operationFilter.trim()) f.operationCode = operationFilter.trim();
    if (sourceFilter.trim()) f.sourceVendor = sourceFilter.trim();
    if (targetFilter.trim()) f.targetVendor = targetFilter.trim();
    if (adoptionStatusFilter.trim()) f.adoptionStatus = adoptionStatusFilter.trim();
    if (nextActionFilter.trim()) f.nextAction = nextActionFilter.trim();
    return f;
  }, [operationFilter, sourceFilter, targetFilter, adoptionStatusFilter, nextActionFilter]);

  const { data: adoptionData, isLoading: adoptionLoading } = useQuery({
    queryKey: ["syntegris-adoption", filters],
    queryFn: () => listSyntegrisAdoption(Object.keys(filters).length ? filters : undefined),
  });

  const { data: summaryData } = useQuery({
    queryKey: ["syntegris-adoption-summary"],
    queryFn: getSyntegrisAdoptionSummary,
  });

  const items = adoptionData?.items ?? [];
  const summary: SyntegrisAdoptionSummary | null = summaryData?.summary ?? null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-gray-900">Adoption</h1>
        <Link
          to="/admin/syntegris-operator-guide"
          className="text-xs text-slate-600 hover:text-slate-900 hover:underline"
        >
          Operator Guide →
        </Link>
      </div>
      <p className="text-sm text-gray-600">
        Full picture of existing Integration Hub inventory and adoption state. Read-only.
        Use filters to narrow; select a row for details and deep links.
      </p>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
          <SummaryCard label="Total" value={summary.total} />
          <SummaryCard label="Legacy Only" value={summary.legacyOnly} />
          <SummaryCard label="Canon Defined" value={summary.canonDefined} />
          <SummaryCard label="Mapping In Progress" value={summary.mappingInProgress} />
          <SummaryCard label="Certified" value={summary.certified} />
          <SummaryCard label="Release Ready" value={summary.releaseReady} />
          <SummaryCard label="Ready" value={summary.syntegrisReady} />
          <SummaryCard label="Blocked" value={summary.blocked} />
        </div>
      )}

      {/* Filters */}
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
            Adoption Status
          </label>
          <select
            id="status-filter"
            value={adoptionStatusFilter}
            onChange={(e) => setAdoptionStatusFilter(e.target.value)}
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md"
          >
            <option value="">All</option>
            <option value="LEGACY_ONLY">Legacy Only</option>
            <option value="CANON_DEFINED">Canon Defined</option>
            <option value="MAPPING_IN_PROGRESS">Mapping In Progress</option>
            <option value="CERTIFIED">Certified</option>
            <option value="RELEASE_READY">Release Ready</option>
            <option value="SYNTEGRIS_READY">Ready</option>
            <option value="BLOCKED">Blocked</option>
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
            <option value="READY">Ready</option>
            <option value="GENERATE_SCAFFOLD">Generate scaffold</option>
            <option value="ADD_FIXTURES">Add fixtures</option>
            <option value="RUN_CERTIFICATION">Run certification</option>
            <option value="ONBOARD_CANONICAL">Onboard canonical</option>
          </select>
        </div>
      </div>

      {/* Table + Detail */}
      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1 min-w-0">
          <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
            {adoptionLoading ? (
              <div className="p-8 text-center text-gray-500">Loading...</div>
            ) : items.length === 0 ? (
              <div className="p-8 text-center text-gray-500">No items match filters.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Operation</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Version</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Source</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Target</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Inventory</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Status</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700">Next Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {items.map((item) => (
                      <tr
                        key={`${item.operationCode}|${item.sourceVendor}|${item.targetVendor}`}
                        onClick={() => setSelectedItem(item)}
                        className={`cursor-pointer hover:bg-slate-50 ${
                          selectedItem === item ? "bg-slate-100" : ""
                        }`}
                      >
                        <td className="px-3 py-2 font-mono text-xs">{item.operationCode}</td>
                        <td className="px-3 py-2">{item.version}</td>
                        <td className="px-3 py-2">{item.sourceVendor}</td>
                        <td className="px-3 py-2">{item.targetVendor}</td>
                        <td className="px-3 py-2">
                          <span className="flex gap-1">
                            <BoolCell value={item.inventoryEvidence?.operationExists} />
                            <BoolCell value={item.inventoryEvidence?.allowlistExists} />
                            <BoolCell value={item.inventoryEvidence?.operationContractExists} />
                            <BoolCell value={item.inventoryEvidence?.vendorMappingExists} />
                            <BoolCell value={item.inventoryEvidence?.endpointConfigExists} />
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <StatusBadge status={item.adoptionStatus} />
                        </td>
                        <td className="px-3 py-2 text-xs">{item.nextAction?.title ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Detail panel */}
        {selectedItem && (
          <div className="w-full lg:w-96 shrink-0 border border-gray-200 rounded-lg bg-white p-4 space-y-4">
            <h3 className="font-medium text-gray-900">Detail</h3>
            <div className="space-y-2 text-sm">
              <div>
                <span className="text-gray-500">Operation:</span>{" "}
                <span className="font-mono">{selectedItem.operationCode}</span> v{selectedItem.version}
              </div>
              <div>
                <span className="text-gray-500">Pair:</span> {selectedItem.sourceVendor} →{" "}
                {selectedItem.targetVendor}
              </div>
              <div>
                <span className="text-gray-500">Adoption:</span>{" "}
                <StatusBadge status={selectedItem.adoptionStatus} />
              </div>
              <div>
                <span className="text-gray-500">Next:</span> {selectedItem.nextAction?.title}
              </div>
            </div>

            <div>
              <h4 className="text-xs font-medium text-gray-600 mb-1">Inventory Evidence</h4>
              <ul className="text-xs space-y-0.5">
                <li>Operation: <BoolCell value={selectedItem.inventoryEvidence?.operationExists} /></li>
                <li>Allowlist: <BoolCell value={selectedItem.inventoryEvidence?.allowlistExists} /></li>
                <li>Contract: <BoolCell value={selectedItem.inventoryEvidence?.operationContractExists} /></li>
                <li>Mapping: <BoolCell value={selectedItem.inventoryEvidence?.vendorMappingExists} /></li>
                <li>Endpoint: <BoolCell value={selectedItem.inventoryEvidence?.endpointConfigExists} /></li>
              </ul>
            </div>

            <div>
              <h4 className="text-xs font-medium text-gray-600 mb-1">Adoption Evidence</h4>
              <ul className="text-xs space-y-0.5">
                <li>Canonical: <BoolCell value={selectedItem.syntegrisEvidence?.canonicalDefined} /></li>
                <li>Mapping Ready: <BoolCell value={selectedItem.syntegrisEvidence?.mappingReady} /></li>
                <li>Release Ready: <BoolCell value={selectedItem.syntegrisEvidence?.releaseReady} /></li>
                <li>Runtime: <BoolCell value={selectedItem.syntegrisEvidence?.runtimeIntegrated} /></li>
              </ul>
            </div>

            {selectedItem.notes?.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-600 mb-1">Notes</h4>
                <ul className="text-xs text-gray-600 list-disc list-inside">
                  {selectedItem.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <h4 className="text-xs font-medium text-gray-600 mb-2">Deep Links</h4>
              <div className="flex flex-wrap gap-2">
                <Link
                  to={buildDeepLink(selectedItem.nextAction?.targetRoute ?? "/admin/canonical-mapping-readiness", selectedItem)}
                  className="px-2 py-1 text-xs font-medium bg-slate-600 text-white rounded hover:bg-slate-700"
                >
                  {selectedItem.nextAction?.title ?? "Next Action"}
                </Link>
                {DEEP_LINK_ROUTES.map((r) => (
                  <Link
                    key={r.path}
                    to={buildDeepLink(r.path, selectedItem)}
                    className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
                  >
                    {r.label}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-2 text-center">
      <div className="text-lg font-semibold text-gray-900">{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}
