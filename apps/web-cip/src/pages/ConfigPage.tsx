import { useState } from "react";
import { getActiveVendorCode } from "../utils/vendorStorage";
import { SupportedOpsTab } from "../components/config/SupportedOpsTab";
import { EndpointsTab } from "../components/config/EndpointsTab";
import { AuthProfilesTab } from "../components/config/AuthProfilesTab";
import { ContractsTab } from "../components/config/ContractsTab";
import { MappingsTab } from "../components/config/MappingsTab";

type TabId = "supportedOps" | "endpoints" | "authProfiles" | "contracts" | "mappings";

const TABS: { id: TabId; label: string }[] = [
  { id: "supportedOps", label: "Supported Ops" },
  { id: "endpoints", label: "Endpoints" },
  { id: "authProfiles", label: "Auth Profiles" },
  { id: "contracts", label: "Contracts" },
  { id: "mappings", label: "Mappings" },
];

export function ConfigPage() {
  const [activeTab, setActiveTab] = useState<TabId>("supportedOps");

  const activeVendor = getActiveVendorCode();

  if (!activeVendor) {
    return (
      <div className="space-y-6">
        <h1 className="text-lg sm:text-2xl font-bold text-gray-900">My Config</h1>
        <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-700">
            Select an active licensee above to configure endpoints, mappings, and contracts.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-lg sm:text-2xl font-bold text-gray-900">My Config</h1>

      <p className="text-sm text-gray-600">
        Configure endpoints, mappings, and contracts below.
      </p>

      <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
        <div className="flex gap-3">
          <svg
            className="h-5 w-5 shrink-0 text-slate-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <div>
            <h3 className="font-semibold text-slate-800 mb-2">How vendor onboarding works</h3>
            <ul className="list-disc list-inside space-y-1 text-slate-600">
              <li>
                <strong>Auth profiles</strong> define how the platform authenticates when calling your APIs or bots (API key, bearer token, basic auth, OAuth2 client credentials).
              </li>
              <li>
                <strong>Endpoints</strong> define <em>where</em> to call (URL, method, timeout) and which operation they serve.
              </li>
              <li>
                A single <strong>auth profile</strong> can be reused across many endpoints.
              </li>
              <li>
                <strong>Contracts &amp; mappings</strong> control the shape of the request/response payloads, not authentication.
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div className="border-b border-gray-200 overflow-x-auto -mx-px">
        <nav className="flex gap-2 sm:gap-4 min-w-max">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveTab(id)}
              className={`py-3 px-1 border-b-2 font-medium text-sm whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center ${
                activeTab === id
                  ? "border-slate-600 text-slate-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>

      {activeTab === "supportedOps" && <SupportedOpsTab />}
      {activeTab === "endpoints" && <EndpointsTab />}
      {activeTab === "authProfiles" && <AuthProfilesTab />}
      {activeTab === "contracts" && <ContractsTab />}
      {activeTab === "mappings" && <MappingsTab />}
    </div>
  );
}
