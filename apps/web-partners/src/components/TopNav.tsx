import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { getActiveVendorCode } from "frontend-shared";
import { AuthButton } from "./AuthButton";
import { useFeature } from "../features/FeatureFlagContext";

const configPaths = [
  "/configuration",
  "/configuration/access",
  "/configuration/allowlist",
  "/configuration/auth-profiles",
  "/configuration/endpoints",
  "/builder",
];
const isFlowsPath = (path: string) =>
  path === "/flows" || (path.startsWith("/flows/") && path.length > 7);
const isFlowJourneyPath = (path: string) => path === "/flow";
const operationsPaths = ["/transactions"];

interface TopNavProps {
  /** When true, renders vertical stack for mobile drawer */
  mobile?: boolean;
  /** Called when Settings is clicked (mobile only); defaults to openSettings event */
  onSettingsClick?: () => void;
}

export function TopNav({ mobile, onSettingsClick }: TopNavProps = {}) {
  const location = useLocation();
  const activeVendor = getActiveVendorCode();
  const hasVendorKey = !!activeVendor;
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement | null>(null);
  const featureHomeWelcome = useFeature("home_welcome");
  const featureAuditView = useFeature("audit_view");
  const featureFlowBuilder = useFeature("flow_builder");
  const featureRegistryBasic = useFeature("registry_basic");
  const featureExecuteTest = useFeature("execute_test");

  const isConfigActive = configPaths.includes(location.pathname);
  const isFlowsActive = isFlowsPath(location.pathname);
  const isOperationsActive = operationsPaths.includes(location.pathname);

  const navLinkClass = (isActive: boolean) =>
    `block px-3 py-2 sm:inline-block text-sm font-medium rounded-md transition-colors ${
      isActive
        ? "bg-teal-50 text-teal-800"
        : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
    }`;

  const disabledClass = "block px-3 py-2 sm:inline-block text-sm font-medium text-gray-400 cursor-not-allowed";

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

  const openSettings = () => {
    if (onSettingsClick) onSettingsClick();
    else window.dispatchEvent(new CustomEvent("openSettings"));
  };

  const navEl = (
    <>
      {featureHomeWelcome && (
        <NavLink to="/home" className={({ isActive }) => navLinkClass(isActive || location.pathname === "/")}>
          Home
        </NavLink>
      )}
      {featureAuditView &&
        (hasVendorKey ? (
          <NavLink to="/transactions" className={() => navLinkClass(isOperationsActive)}>
            Operations
          </NavLink>
        ) : (
          <span className={disabledClass} title="Select active licensee first">
            Operations
          </span>
        ))}
      {featureFlowBuilder &&
        (hasVendorKey ? (
          <>
            <NavLink to="/flow" className={() => navLinkClass(isFlowJourneyPath(location.pathname))}>
              Flow
            </NavLink>
            <NavLink to="/flows" className={() => navLinkClass(isFlowsActive)}>
              Flows
            </NavLink>
          </>
        ) : (
          <>
            <span className={disabledClass} title="Select active licensee first">
              Flow
            </span>
            <span className={disabledClass} title="Select active licensee first">
              Flows
            </span>
          </>
        ))}
      {featureRegistryBasic &&
        (hasVendorKey ? (
          <NavLink to="/configuration" className={() => navLinkClass(isConfigActive)}>
            Configuration
          </NavLink>
        ) : (
          <span className={disabledClass} title="Select active licensee first">
            Configuration
          </span>
        ))}
      {featureExecuteTest &&
        (hasVendorKey ? (
          <NavLink
            to="/execute"
            className={() => navLinkClass(location.pathname === "/execute")}
          >
            Execute
          </NavLink>
        ) : (
          <span className={disabledClass} title="Select active licensee first">
            Execute
          </span>
        ))}
      {!mobile && <AuthButton />}
      {mobile && (
        <div className="block w-full px-4 py-3 border-t border-gray-100 mt-2">
          <AuthButton />
        </div>
      )}
      {mobile ? (
        <button
          type="button"
          onClick={openSettings}
          className="block w-full text-left px-4 py-3 border-t border-gray-100 mt-2 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100"
        >
          Settings
        </button>
      ) : (
        <div className="relative" ref={settingsRef}>
          <button
            type="button"
            onClick={() => setSettingsMenuOpen((v) => !v)}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-gray-200 text-gray-700 hover:bg-gray-300"
            aria-label="Settings"
          >
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <circle cx="12" cy="5.5" r="2" />
              <circle cx="12" cy="12" r="2" />
              <circle cx="12" cy="18.5" r="2" />
            </svg>
          </button>
          {settingsMenuOpen && (
            <div className="absolute right-0 mt-2 w-36 rounded-md border border-gray-200 bg-white shadow-lg z-50">
              <button
                type="button"
                onClick={() => {
                  setSettingsMenuOpen(false);
                  openSettings();
                }}
                className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                Settings
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );

  if (mobile) {
    return (
      <nav className="flex flex-col" aria-label="Main navigation">
        {navEl}
      </nav>
    );
  }

  return (
    <nav className="flex items-center gap-1" aria-label="Main navigation">
      {navEl}
    </nav>
  );
}
