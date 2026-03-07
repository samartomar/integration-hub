import { useState, useEffect, useRef } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useOktaAuth } from "@okta/okta-react";
import { EnvironmentBadge } from "./EnvironmentBadge";
import { AuthButton } from "./AuthButton";
import { useFeature } from "../features/FeatureFlagContext";

/** Converged nav: Registry, Canonical, Flow Builder, Adoption workbench. Tool pages (Sandbox, etc.) reached via Canonical/Adoption/Operator Guide. */
const primaryNavItems = [
  { path: "/admin/registry", label: "Registry", featureCode: "registry_basic" },
  { path: "/admin/canonical", label: "Canonical", featureCode: "registry_basic" },
  { path: "/admin/flow-builder", label: "Flow Builder", featureCode: "registry_basic" },
  { path: "/admin/adoption", label: "Adoption", featureCode: "registry_basic" },
  { path: "/ai", label: "AI", featureCode: "ai_formatter_ui" },
] as const;

const adminNavItems = [
  { path: "/admin/dashboard", label: "Dashboard", featureCode: "home_welcome" },
  { path: "/admin/transactions", label: "Transactions", featureCode: "audit_view" },
  { path: "/admin/mission-control", label: "Mission Control", featureCode: "registry_basic" },
  { path: "/admin/syntegris-operator-guide", label: "Operator Guide", featureCode: "registry_basic" },
  { path: "/admin/policy-decisions", label: "Policy Decisions", adminOnly: true },
  { path: "/admin/policy-simulator", label: "Policy Simulator", adminOnly: true },
  { path: "/admin/journey-mode", label: "Journey Mode" },
] as const;

function isPrimaryNavActive(pathname: string, label: string): boolean {
  if (label === "Registry") {
    return pathname.startsWith("/admin/registry") || pathname === "/registry";
  }
  if (label === "Canonical") return pathname.startsWith("/admin/canonical");
  if (label === "Flow Builder") return pathname.startsWith("/admin/flow-builder");
  if (label === "Adoption")
    return (
      pathname.startsWith("/admin/adoption") ||
      pathname.startsWith("/admin/syntegris-adoption") ||
      pathname.startsWith("/admin/canonical-mapping-readiness")
    );
  if (label === "Operator Guide") return pathname.startsWith("/admin/syntegris-operator-guide");
  if (label === "AI") return pathname.startsWith("/ai");
  return false;
}

interface TopBarProps {
  onSettingsClick: () => void;
  onFeaturesClick: () => void;
}

export function TopBar({ onSettingsClick, onFeaturesClick }: TopBarProps) {
  const location = useLocation();
  const okta = useOktaAuth();
  const authState = okta?.authState;
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!settingsMenuOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (!settingsRef.current?.contains(e.target as Node)) setSettingsMenuOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSettingsMenuOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [settingsMenuOpen]);

  const navLinkClass = (isActive: boolean) =>
    `block px-3 py-2 sm:inline-block text-sm font-medium rounded-md transition-colors ${
      isActive
        ? "bg-slate-300 text-slate-900"
        : "text-slate-600 hover:text-slate-900 hover:bg-slate-200"
    }`;

  const featureHomeWelcome = useFeature("home_welcome");
  const featureAuditView = useFeature("audit_view");
  const featureRegistryBasic = useFeature("registry_basic");
  const featureAiFormatter = useFeature("ai_formatter_ui");
  const tokenClaims = (authState?.idToken?.claims || authState?.accessToken?.claims || {}) as Record<string, unknown>;
  const rawGroups = tokenClaims.groups ?? tokenClaims.group;
  const groups = Array.isArray(rawGroups) ? rawGroups.map((g) => String(g)) : [];
  const isAdmin = groups.some((g) => g.toLowerCase() === "integrationhub-admins");

  const visibleAdminNavItems = adminNavItems.filter((item) => {
    if (item.path === "/admin/dashboard") return featureHomeWelcome;
    if (item.path === "/admin/transactions") return featureAuditView;
    if (item.path === "/admin/mission-control") return featureRegistryBasic;
    if ((item as { adminOnly?: boolean }).adminOnly) return isAdmin;
    return true;
  });
  const visiblePrimaryNavItems = primaryNavItems.filter((item) => {
    if (item.path === "/admin/registry") return featureRegistryBasic;
    if (item.path === "/admin/canonical") return featureRegistryBasic;
    if (item.path === "/admin/flow-builder") return featureRegistryBasic;
    if (item.path === "/admin/adoption") return featureRegistryBasic;
    if (item.path === "/ai") return featureAiFormatter;
    return true;
  });

  return (
    <>
      <header className="h-14 flex items-center justify-between px-3 sm:px-6 shadow-sm shrink-0 border-b border-slate-400 border-t-4 border-t-slate-600 bg-slate-200">
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={() => setMobileNavOpen((o) => !o)}
            className="p-2 -ml-1 rounded-lg lg:hidden text-slate-700 hover:bg-slate-300"
            aria-label="Open menu"
            aria-expanded={mobileNavOpen}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium bg-slate-600 text-white shrink-0">
            Central Integration Platform
          </span>
          <EnvironmentBadge />
          <nav className="hidden lg:flex items-center gap-1 border-l border-slate-400 pl-4 shrink-0">
            {visibleAdminNavItems.map(({ path, label }) => (
              <NavLink
                key={path}
                to={path}
                className={({ isActive }) => navLinkClass(isActive)}
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <nav className="hidden lg:flex items-center gap-1 border-l border-slate-400 pl-4 shrink-0">
            {visiblePrimaryNavItems.map(({ path, label }) => (
              <NavLink
                key={path}
                to={path}
                className={() => navLinkClass(isPrimaryNavActive(location.pathname, label))}
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="hidden lg:flex items-center gap-2 shrink-0">
          <AuthButton />
          <div className="relative" ref={settingsRef}>
            <button
              type="button"
              onClick={() => setSettingsMenuOpen((v) => !v)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-gray-200 text-gray-700 hover:bg-gray-300"
              aria-label="Open settings menu"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <circle cx="12" cy="5.5" r="2" />
                <circle cx="12" cy="12" r="2" />
                <circle cx="12" cy="18.5" r="2" />
              </svg>
            </button>
            {settingsMenuOpen && (
              <div className="absolute right-0 mt-2 w-40 rounded-md border border-gray-200 bg-white shadow-lg z-50">
                <button
                  type="button"
                  onClick={() => {
                    setSettingsMenuOpen(false);
                    onSettingsClick();
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  Settings
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSettingsMenuOpen(false);
                    onFeaturesClick();
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  Features
                </button>
              </div>
            )}
          </div>
        </div>
        <div className="flex lg:hidden items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={onSettingsClick}
            className="p-2 rounded-lg text-slate-600 hover:bg-slate-300"
            aria-label="Settings"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </header>

      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" aria-hidden>
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setMobileNavOpen(false)}
          />
          <nav className="absolute top-14 left-0 right-0 bg-white shadow-lg border-b border-gray-200 max-h-[calc(100vh-3.5rem)] overflow-y-auto">
            <div className="py-2 px-3">
              <div className="flex flex-col gap-0">
                {visibleAdminNavItems.map(({ path, label }) => (
                  <NavLink
                    key={path}
                    to={path}
                    className={({ isActive }) =>
                      `px-4 py-3 rounded-lg ${navLinkClass(isActive)}`
                    }
                  >
                    {label}
                  </NavLink>
                ))}
                {visiblePrimaryNavItems.map(({ path, label }) => (
                  <NavLink
                    key={path}
                    to={path}
                    className={() =>
                      `px-4 py-3 rounded-lg ${navLinkClass(isPrimaryNavActive(location.pathname, label))}`
                    }
                  >
                    {label}
                  </NavLink>
                ))}
                <div className="block w-full px-4 py-3 border-t border-gray-100 mt-2">
                  <AuthButton />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setMobileNavOpen(false);
                    onSettingsClick();
                  }}
                  className="block w-full text-left px-4 py-3 text-sm font-medium text-slate-700 hover:text-slate-900 hover:bg-slate-200 border-t border-gray-100 mt-2 rounded-lg"
                >
                  Settings
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMobileNavOpen(false);
                    onFeaturesClick();
                  }}
                  className="block w-full text-left px-4 py-3 text-sm font-medium text-slate-700 hover:text-slate-900 hover:bg-slate-200 rounded-lg"
                >
                  Features
                </button>
              </div>
            </div>
          </nav>
        </div>
      )}
    </>
  );
}
