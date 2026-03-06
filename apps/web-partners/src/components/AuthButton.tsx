import { useOktaAuth } from "@okta/okta-react";
import { useEffect, useRef, useState } from "react";
import { getActiveVendorCode } from "frontend-shared";
import { isOktaEnabled } from "../config/oktaConfig";

/**
 * Login/Logout button for TopNav. Renders nothing when Okta is disabled.
 */
export function AuthButton() {
  const oktaEnabled = isOktaEnabled();
  if (!oktaEnabled) return null;

  return <AuthButtonInner />;
}

function AuthButtonInner() {
  const { oktaAuth, authState } = useOktaAuth();
  const isAuthenticated = !!authState?.isAuthenticated;
  const user = authState?.idToken?.claims as { email?: string; name?: string } | undefined;
  const displayName = user?.name?.trim() || "User";
  const email = user?.email?.trim() || "No email";
  const licensee = getActiveVendorCode() || "N/A";
  const initial =
    ((displayName.match(/[A-Za-z]/)?.[0] ?? displayName.trim().charAt(0) ?? "U").toUpperCase());
  const [menuOpen, setMenuOpen] = useState(false);
  const [hoverOpen, setHoverOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [menuOpen]);

  return (
    <div
      className="relative"
      ref={menuRef}
      onMouseEnter={() => setHoverOpen(true)}
      onMouseLeave={() => setHoverOpen(false)}
    >
      <button
        type="button"
        onClick={() => {
          if (isAuthenticated) {
            setMenuOpen((v) => !v);
            return;
          }
          void oktaAuth.signInWithRedirect({ originalUri: `${window.location.pathname}${window.location.search}` });
        }}
        title={isAuthenticated ? `Signed in as ${displayName}` : "Log in"}
        className="h-7 w-7 inline-flex items-center justify-center rounded-full bg-pink-500 text-white text-sm font-semibold hover:bg-pink-600 transition-colors"
      >
        {isAuthenticated ? initial : (
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="2" />
            <path d="M4 20c1.8-3.3 4.4-5 8-5s6.2 1.7 8 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        )}
      </button>
      {isAuthenticated && hoverOpen && !menuOpen && (
        <div className="absolute right-0 mt-2 w-56 rounded-xl bg-gray-700 px-4 py-3 text-white shadow-lg z-50">
          <div className="text-xs text-gray-200">Name</div>
          <div className="text-sm leading-5">{displayName}</div>
          <div className="mt-1 text-xs text-gray-200">Email</div>
          <div className="text-sm leading-5 break-all">{email}</div>
          <div className="mt-1 text-xs text-gray-200">Licensee</div>
          <div className="text-sm leading-5">{licensee}</div>
        </div>
      )}
      {isAuthenticated && menuOpen && (
        <div className="absolute right-0 mt-2 w-40 rounded-md border border-gray-200 bg-white shadow-lg z-50">
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              void oktaAuth.signOut({ postLogoutRedirectUri: window.location.origin });
            }}
            className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
