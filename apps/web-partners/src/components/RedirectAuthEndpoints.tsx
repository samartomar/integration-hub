import { Navigate, useLocation } from "react-router-dom";

/** Redirects /auth and /auth-security to Authentication profiles */
export function RedirectAuthToProfiles() {
  return <Navigate to="/configuration/auth-profiles" replace />;
}

/** Redirects /contracts to Configuration/Operations, preserving search params */
export function RedirectContractsToConfiguration() {
  const location = useLocation();
  const search = location.search ? location.search : "";
  return <Navigate to={`/configuration${search}`} replace />;
}

/** Redirects /endpoints to Endpoints page, preserving authProfile and operation params */
export function RedirectEndpointsToTab() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const authProfile = params.get("authProfile");
  const operation = params.get("operation");
  const next = new URLSearchParams();
  if (authProfile) next.set("authProfile", authProfile);
  if (operation) next.set("operation", operation);
  const qs = next.toString();
  return <Navigate to={qs ? `/configuration/endpoints?${qs}` : "/configuration/endpoints"} replace />;
}
