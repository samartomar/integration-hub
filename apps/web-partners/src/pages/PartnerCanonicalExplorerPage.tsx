import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getActiveVendorCode } from "frontend-shared";
import {
  listPartnerSyntegrisCanonicalOperations,
  getPartnerSyntegrisCanonicalOperation,
  type CanonicalOperationItem,
  type CanonicalOperationDetail,
} from "../api/endpoints";
import {
  isSupportedCanonicalSlice,
  SUPPORTED_SOURCE_VENDOR,
  SUPPORTED_TARGET_VENDOR,
} from "frontend-shared";

type TabId = "overview" | "request-schema" | "response-schema" | "examples";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "request-schema", label: "Request schema" },
  { id: "response-schema", label: "Response schema" },
  { id: "examples", label: "Examples" },
];

function JsonBlock({
  data,
  label,
  onCopy,
}: {
  data: Record<string, unknown> | null;
  label?: string;
  onCopy?: () => void;
}) {
  const text = data ? JSON.stringify(data, null, 2) : "";
  const handleCopy = useCallback(() => {
    if (text && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      onCopy?.();
    }
  }, [text, onCopy]);

  if (!data || Object.keys(data).length === 0) {
    return <p className="text-sm text-gray-500 italic">—</p>;
  }
  return (
    <div className="relative group">
      {label && (
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-gray-600">{label}</span>
          {onCopy !== undefined && (
            <button
              type="button"
              onClick={handleCopy}
              className="text-xs text-slate-600 hover:text-slate-900 px-2 py-1 rounded hover:bg-slate-100"
            >
              Copy
            </button>
          )}
        </div>
      )}
      <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-4 overflow-x-auto border border-gray-200 font-mono">
        {text}
      </pre>
    </div>
  );
}

/** Vendor-facing Canonical Explorer. Read-only, no sourceVendor input. */
export function PartnerCanonicalExplorerPage() {
  const [selectedOp, setSelectedOp] = useState<CanonicalOperationItem | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [search, setSearch] = useState("");

  const { data: opsData, isLoading: opsLoading, error: opsError } = useQuery({
    queryKey: ["partner-syntegris-canonical-operations"],
    queryFn: listPartnerSyntegrisCanonicalOperations,
  });

  const { data: opDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["partner-syntegris-canonical-operation", selectedOp?.operationCode, selectedOp?.latestVersion],
    queryFn: () =>
      getPartnerSyntegrisCanonicalOperation(selectedOp!.operationCode, selectedOp!.latestVersion),
    enabled: !!selectedOp,
  });

  const activeVendor = getActiveVendorCode();
  const allItems = opsData?.items ?? [];
  const items = useMemo(() => {
    let list = allItems;
    if (activeVendor === SUPPORTED_SOURCE_VENDOR) {
      list = list.filter((op) =>
        isSupportedCanonicalSlice(op.operationCode ?? "", SUPPORTED_SOURCE_VENDOR, SUPPORTED_TARGET_VENDOR)
      );
    }
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (op) =>
        (op.operationCode ?? "").toLowerCase().includes(q) ||
        (op.title ?? "").toLowerCase().includes(q)
    );
  }, [allItems, search, activeVendor]);
  const hasSelection = !!selectedOp;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">Canonical Explorer</h1>
      <p className="text-sm text-gray-600">
        Browse canonical operation schemas and examples. Read-only.
      </p>

      <div className="flex flex-col lg:flex-row gap-4">
        <div className="w-full lg:w-64 shrink-0">
          <h2 className="text-sm font-medium text-gray-700 mb-2">Operations</h2>
          {opsLoading && <p className="text-sm text-gray-500">Loading…</p>}
          {opsError && (
            <p className="text-sm text-red-600">
              Failed to load operations. Check your connection.
            </p>
          )}
          {!opsLoading && !opsError && items.length === 0 && (
            <p className="text-sm text-gray-500">No canonical operations registered.</p>
          )}
          {!opsLoading && allItems.length > 0 && (
            <>
              <input
                type="search"
                placeholder="Search by code or title…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full mb-2 px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-500"
                aria-label="Search operations"
              />
              <ul className="border border-gray-200 rounded-lg divide-y divide-gray-200 bg-white">
                {items.length === 0 ? (
                  <li className="px-3 py-4 text-sm text-gray-500 text-center">
                    No operations match your search.
                  </li>
                ) : (
                  items.map((op) => (
                    <li key={op.operationCode}>
                      <button
                        type="button"
                        onClick={() => setSelectedOp(op)}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 ${
                          selectedOp?.operationCode === op.operationCode
                            ? "bg-slate-100 text-slate-900 font-medium"
                            : "text-gray-700"
                        }`}
                      >
                        {op.title ?? op.operationCode}
                        <span className="block text-xs text-gray-500">
                          {op.operationCode}
                          {op.latestVersion ? ` · ${op.latestVersion}` : ""}
                        </span>
                      </button>
                    </li>
                  ))
                )}
              </ul>
            </>
          )}
        </div>

        <div className="flex-1 min-w-0">
          {!hasSelection && (
            <div className="border border-gray-200 rounded-lg p-8 bg-gray-50 text-center text-gray-500 text-sm">
              Select an operation to view schemas and examples.
            </div>
          )}
          {hasSelection && (
            <>
              <div className="mb-3">
                <h2 className="text-lg font-medium text-gray-900">
                  {opDetail?.title ?? selectedOp!.operationCode} ({selectedOp!.latestVersion})
                </h2>
              </div>
              <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
                <div className="flex border-b border-gray-200">
                  {TABS.map(({ id, label }) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setActiveTab(id)}
                      className={`px-4 py-2 text-sm font-medium ${
                        activeTab === id
                          ? "bg-slate-100 text-slate-900 border-b-2 border-slate-600"
                          : "text-gray-600 hover:bg-gray-50"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="p-4">
                  {detailLoading && (
                    <p className="text-sm text-gray-500">Loading details…</p>
                  )}
                  {!detailLoading && opDetail && (
                    <>
                      {activeTab === "overview" && (
                        <div className="space-y-4 text-sm">
                          {opDetail.description && (
                            <div>
                              <h3 className="font-medium text-gray-700 mb-1">Description</h3>
                              <p className="text-gray-600">{opDetail.description}</p>
                            </div>
                          )}
                          <div>
                            <h3 className="font-medium text-gray-700 mb-1">Metadata</h3>
                            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-gray-600">
                              <dt>Operation:</dt>
                              <dd className="font-mono">{opDetail.operationCode}</dd>
                              <dt>Version:</dt>
                              <dd>{opDetail.version}</dd>
                              {opDetail.versionAliases?.length ? (
                                <>
                                  <dt>Aliases:</dt>
                                  <dd>{opDetail.versionAliases.join(", ")}</dd>
                                </>
                              ) : null}
                            </dl>
                          </div>
                        </div>
                      )}
                      {activeTab === "request-schema" && (
                        <JsonBlock
                          data={opDetail.requestPayloadSchema as Record<string, unknown>}
                          label="Request payload schema"
                          onCopy={() => {}}
                        />
                      )}
                      {activeTab === "response-schema" && (
                        <JsonBlock
                          data={opDetail.responsePayloadSchema as Record<string, unknown>}
                          label="Response payload schema"
                          onCopy={() => {}}
                        />
                      )}
                      {activeTab === "examples" && (
                        <div className="space-y-6">
                          <JsonBlock
                            data={opDetail.examples?.request ?? null}
                            label="Request payload"
                            onCopy={() => {}}
                          />
                          <JsonBlock
                            data={opDetail.examples?.response ?? null}
                            label="Response payload"
                            onCopy={() => {}}
                          />
                          <JsonBlock
                            data={
                              (opDetail.examples?.requestEnvelope as Record<string, unknown>) ?? null
                            }
                            label="Request envelope"
                            onCopy={() => {}}
                          />
                          <JsonBlock
                            data={
                              (opDetail.examples?.responseEnvelope as Record<string, unknown>) ??
                              null
                            }
                            label="Response envelope"
                            onCopy={() => {}}
                          />
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
