import { useState, useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ConnectionBanner, DebugPanel, getActiveVendorCode } from "frontend-shared";
import { listVendors } from "./api/endpoints";
import { OktaTokenSetup } from "./components/OktaTokenSetup";
import { EnvironmentBadge } from "./components/EnvironmentBadge";
import { canonicalVendorsKey, STALE_CONFIG } from "./api/queryKeys";
import { SettingsModal } from "./components/SettingsModal";
import { TopNav } from "./components/TopNav";
import { ConfigNavCards } from "./components/ConfigNavCards";
import { SectionSubNav } from "./components/SectionSubNav";

const configPaths = [
  "/configuration",
  "/configuration/access",
  "/configuration/allowlist",
  "/configuration/auth-profiles",
  "/configuration/endpoints",
  "/builder",
];
const operationsPaths = ["/transactions"];
const operationsNavItems = [
  { path: "/transactions", label: "Transactions" },
];

export function VendorAppLayout() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [, setCredentialsVersion] = useState(0);
  const location = useLocation();
  const queryClient = useQueryClient();
  const activeVendor = getActiveVendorCode();
  const hasKey = !!activeVendor;
  const { data: vendorsData } = useQuery({
    queryKey: canonicalVendorsKey,
    queryFn: () => listVendors({ limit: 200 }),
    staleTime: STALE_CONFIG,
  });
  const vendors = vendorsData?.items ?? [];
  const vendorDisplay =
    activeVendor && hasKey
      ? vendors.find((v) => (v.vendorCode ?? "").toUpperCase() === activeVendor.toUpperCase())
          ?.vendorName ?? activeVendor
      : null;

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const refresh = () => setCredentialsVersion((v) => v + 1);
    const openSettings = () => setSettingsOpen(true);
    window.addEventListener("vendorKeysChanged" as keyof WindowEventMap, refresh);
    window.addEventListener("activeVendorChanged" as keyof WindowEventMap, refresh);
    window.addEventListener("openSettings" as keyof WindowEventMap, openSettings);
    return () => {
      window.removeEventListener("vendorKeysChanged" as keyof WindowEventMap, refresh);
      window.removeEventListener("activeVendorChanged" as keyof WindowEventMap, refresh);
      window.removeEventListener("openSettings" as keyof WindowEventMap, openSettings);
    };
  }, []);

  const showConfigSubNav = configPaths.includes(location.pathname);
  const showOperationsSubNav = operationsPaths.includes(location.pathname);

  const openSettings = () => {
    setMobileNavOpen(false);
    setSettingsOpen(true);
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <OktaTokenSetup />
      <header
        className="h-14 flex items-center justify-between px-3 sm:px-6 shadow-sm shrink-0 border-b border-teal-200 border-t-4 border-t-teal-500 bg-teal-50"
      >
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={() => setMobileNavOpen((o) => !o)}
            className="p-2 -ml-1 rounded-lg md:hidden text-slate-700 hover:bg-teal-100"
            aria-label="Open menu"
            aria-expanded={mobileNavOpen}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          {vendorDisplay ? (
            <span className="inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold bg-teal-600 text-white truncate max-w-[320px]">
              {vendorDisplay}
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold bg-teal-600 text-white">
              Licensee Portal
            </span>
          )}
          <EnvironmentBadge />
        </div>
        <div className="hidden md:flex items-center gap-1 shrink-0">
          <TopNav />
        </div>
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          className="md:hidden p-2 rounded-lg text-slate-600 hover:bg-teal-100"
          aria-label="Settings"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>
      </header>
      <ConnectionBanner onRetry={() => queryClient.invalidateQueries()} />

      {/* Mobile nav overlay + drawer */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 md:hidden" aria-hidden>
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setMobileNavOpen(false)}
          />
          <nav className="absolute top-14 left-0 right-0 bg-white shadow-lg border-b border-gray-200 max-h-[calc(100vh-3.5rem)] overflow-y-auto">
            <div className="py-2">
              <TopNav mobile onSettingsClick={openSettings} />
            </div>
          </nav>
        </div>
      )}
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
      <DebugPanel />
      <main className="flex-1 min-w-0 overflow-auto bg-slate-50 [scrollbar-gutter:stable]">
        <div className="w-full max-w-[1600px] mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-5 lg:py-6 border-l-4 border-l-teal-500">
          {showConfigSubNav && <ConfigNavCards />}
          {showOperationsSubNav && operationsNavItems.length > 1 && (
            <SectionSubNav items={operationsNavItems} />
          )}
          <Outlet />
        </div>
      </main>
    </div>
  );
}
