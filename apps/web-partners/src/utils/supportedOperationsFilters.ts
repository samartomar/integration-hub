/**
 * Shared filter state for Supported Operations page.
 * Used to preserve filters in URL and when navigating to/from Visual Flow Builder.
 */

export type DirectionFilter = "all" | "inbound" | "outbound" | "both";
export type StatusFilter = "all" | "ok" | "partial" | "not_configured";

export interface SupportedOpsFilterParams {
  search?: string;
  direction?: DirectionFilter;
  status?: StatusFilter;
}

const PARAM_SEARCH = "search";
const PARAM_DIRECTION = "direction";
const PARAM_STATUS = "status";

export function parseFilterParams(searchParams: URLSearchParams): SupportedOpsFilterParams {
  const search = searchParams.get(PARAM_SEARCH) ?? "";
  const direction = (searchParams.get(PARAM_DIRECTION) as DirectionFilter | null) ?? "all";
  const status = (searchParams.get(PARAM_STATUS) as StatusFilter | null) ?? "all";
  return { search, direction, status };
}

const PARAM_STAGE = "stage";

export function buildFilterQueryString(
  params: SupportedOpsFilterParams,
  stage?: string
): string {
  const q = new URLSearchParams();
  if (stage) q.set(PARAM_STAGE, stage);
  if (params.search?.trim()) q.set(PARAM_SEARCH, params.search.trim());
  if (params.direction && params.direction !== "all") q.set(PARAM_DIRECTION, params.direction);
  if (params.status && params.status !== "all") q.set(PARAM_STATUS, params.status);
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Parse filter params from location.search (e.g. when on Flow Builder). */
export function parseFilterParamsFromSearch(search: string): SupportedOpsFilterParams {
  const q = search.startsWith("?") ? search.slice(1) : search;
  return parseFilterParams(new URLSearchParams(q));
}

/** Extract direction from URL for Flow Builder pill (inbound | outbound | null). */
export function getDirectionFromSearch(search: string): "inbound" | "outbound" | null {
  const params = parseFilterParamsFromSearch(search);
  if (params.direction === "inbound" || params.direction === "outbound") return params.direction;
  return null;
}

export function buildContractsPathWithFilters(params: SupportedOpsFilterParams): string {
  const qs = buildFilterQueryString(params);
  return `/configuration${qs}`;
}
