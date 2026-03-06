import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listVendors, type ListRegistryResponse } from "../api/endpoints";
import type { Vendor } from "../types";
import { PageLayout } from "frontend-shared";
import { OverviewDashboard } from "../components/dashboard/OverviewDashboard";
import { OperationsDashboard } from "../components/dashboard/OperationsDashboard";
import { useFeature } from "../features/FeatureFlagContext";

const ALL_LICENSEES = "ALL";

type DashboardTab = "overview" | "operations";

function tabClass(active: boolean): string {
  return `px-3 py-2 text-sm font-medium rounded-lg ${
    active ? "bg-gray-800 text-white" : "bg-transparent text-gray-600 hover:bg-gray-100"
  }`;
}

function licenseeLabel(value: string, vendors: Vendor[]): string {
  if (value === ALL_LICENSEES) return "All licensees";
  const v = vendors.find((x) => x.vendorCode === value);
  return v ? `${v.vendorCode}` : value;
}

export function DashboardPage() {
  const [activeTab, setActiveTab] = useState<DashboardTab>("overview");
  const [selectedLicensee, setSelectedLicensee] = useState<string>(ALL_LICENSEES);

  const { data: vendorsData } = useQuery<ListRegistryResponse<Vendor>>({
    queryKey: ["registry-vendors"],
    queryFn: () => listVendors(),
  });
  const vendors = vendorsData?.items ?? [];
  const activeVendors = vendors.filter((v) => v.isActive !== false);
  const featureRegistryBasic = useFeature("registry_basic");

  return (
    <PageLayout
      embedded
      title="Admin Dashboard"
      description="View transaction volumes, status breakdown, and operations by licensee."
      right={
        <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-3 sm:gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
            <label className="text-sm text-slate-600">Licensee</label>
            <select
              value={selectedLicensee}
              onChange={(e) => setSelectedLicensee(e.target.value)}
              className="w-full sm:w-auto px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-gray-300 focus:border-gray-400 min-h-[44px] sm:min-h-0"
            >
              <option value={ALL_LICENSEES}>All licensees</option>
              {activeVendors.map((v) => (
                <option key={v.vendorCode} value={v.vendorCode}>
                  {v.vendorCode}
                </option>
              ))}
            </select>
          </div>
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
            <button
              type="button"
              className={tabClass(activeTab === "overview")}
              onClick={() => setActiveTab("overview")}
            >
              Overview
            </button>
            <button
              type="button"
              className={`${tabClass(activeTab === "operations")} border-l border-gray-200`}
              onClick={() => setActiveTab("operations")}
            >
              By Operation
            </button>
          </div>
          {featureRegistryBasic && (
            <Link
              to="/admin/registry"
              className="inline-flex items-center rounded-lg bg-gray-800 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-gray-700 border border-gray-700"
            >
              Open Registry
            </Link>
          )}
        </div>
      }
    >
      {activeTab === "overview" && (
        <OverviewDashboard
          selectedLicensee={selectedLicensee}
          vendors={activeVendors}
          subtitle={licenseeLabel(selectedLicensee, vendors)}
        />
      )}
      {activeTab === "operations" && (
        <OperationsDashboard
          selectedLicensee={selectedLicensee}
          vendors={activeVendors}
          subtitle={licenseeLabel(selectedLicensee, vendors)}
        />
      )}
    </PageLayout>
  );
}
