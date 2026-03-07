/** Adoption Workbench – consolidated governance surface.
 * Tabs: Adoption | Mapping Readiness (includes release bundle).
 * Reuses existing pages; no functionality removed.
 */

import { Link, useSearchParams } from "react-router-dom";
import { SyntegrisAdoptionWorkbenchPage } from "./SyntegrisAdoptionWorkbenchPage";
import { CanonicalMappingReadinessPage } from "./CanonicalMappingReadinessPage";

const TABS = [
  { id: "adoption", label: "Adoption" },
  { id: "readiness", label: "Mapping Readiness" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function AdoptionWorkbenchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") as TabId | null;
  const activeTab: TabId =
    (tabParam && TABS.some((t) => t.id === tabParam) ? tabParam : "adoption") ?? "adoption";

  const setTab = (id: TabId) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (id === "adoption") next.delete("tab");
      else next.set("tab", id);
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h1 className="text-xl font-semibold text-gray-900">Adoption & Readiness</h1>
        <div className="flex items-center gap-2">
          <Link
            to="/admin/syntegris-operator-guide"
            className="text-xs text-slate-600 hover:text-slate-900 hover:underline"
          >
            Operator Guide →
          </Link>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
              activeTab === t.id
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "adoption" && <SyntegrisAdoptionWorkbenchPage />}
      {activeTab === "readiness" && <CanonicalMappingReadinessPage />}
    </div>
  );
}
