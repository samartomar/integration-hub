import { useOktaAuth } from "@okta/okta-react";
import { useEffect, useRef, useState } from "react";
import { isOktaEnabled } from "../config/oktaConfig";

/**
 * Login/Logout button for TopBar. Renders nothing when Okta is disabled.
 */
export function AuthButton() {
  const oktaEnabled = isOktaEnabled();
  if (!oktaEnabled) return null;

  return <AuthButtonInner />;
}

function AuthButtonInner() {
  const { oktaAuth, authState } = useOktaAuth();
  const isAuthenticated = !!authState?.isAuthenticated;
  const claims = (authState?.idToken?.claims ?? {}) as Record<string, unknown>;
  const user = claims as { email?: string; name?: string };
  const displayName = user?.name?.trim() || user?.email?.trim() || "User";
  const email = user?.email?.trim() || "No email";
  const licensee =
    (typeof claims.lhcode === "string" && claims.lhcode.trim()) ||
    (typeof claims.vendor_code === "string" && claims.vendor_code.trim()) ||
    (typeof claims["https://gosam.io/lhcode"] === "string" && String(claims["https://gosam.io/lhcode"]).trim()) ||
    "N/A";
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

  if (!isAuthenticated) {
    return (
      <button
        type="button"
        onClick={() => {
          void oktaAuth.signInWithRedirect({
            originalUri: `${window.location.pathname}${window.location.search}`,
          });
        }}
        className="text-sm font-medium rounded-md text-slate-700 hover:text-slate-900 hover:bg-slate-200 px-3 py-2 transition-colors"
      >
        Log in
      </button>
    );
  }

  const initial =
    ((displayName.match(/[A-Za-z]/)?.[0] ?? displayName.trim().charAt(0) ?? "U").toUpperCase());

  return (
    <div
      className="relative"
      ref={menuRef}
      onMouseEnter={() => setHoverOpen(true)}
      onMouseLeave={() => setHoverOpen(false)}
    >
      <button
        type="button"
        onClick={() => setMenuOpen((v) => !v)}
        title={displayName}
        className="h-7 w-7 inline-flex items-center justify-center rounded-full bg-pink-500 text-white text-sm font-semibold hover:bg-pink-600 transition-colors"
      >
        {initial}
      </button>
      {hoverOpen && !menuOpen && (
        <div className="absolute right-0 mt-2 w-56 rounded-xl bg-gray-700 px-4 py-3 text-white shadow-lg z-50">
          <div className="text-xs text-gray-200">Name</div>
          <div className="text-sm leading-5">{displayName}</div>
          <div className="mt-1 text-xs text-gray-200">Email</div>
          <div className="text-sm leading-5 break-all">{email}</div>
          <div className="mt-1 text-xs text-gray-200">Licensee</div>
          <div className="text-sm leading-5">{licensee}</div>
        </div>
      )}
      {menuOpen && (
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
