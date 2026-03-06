/**
 * Tests for Configuration Overview / Operations page.
 * Merged page that replaced the old Supported Operations tab.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as endpointsApi from "../api/endpoints";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, Navigate } from "react-router-dom";
import { VendorConfigurationPage } from "./VendorConfigurationPage";
import { RedirectContractsToConfiguration } from "../components/RedirectAuthEndpoints";

vi.mock("../api/endpoints");

function TestWrapper({
  initialEntries = ["/configuration"],
  routes = [
    <Route key="contracts" path="/contracts" element={<RedirectContractsToConfiguration />} />,
    <Route key="config" path="/configuration" element={<VendorConfigurationPage />} />,
    <Route key="access" path="/configuration/access" element={<div data-testid="access-page">Access Control</div>} />,
    <Route key="builder" path="/builder/:operationCode/:canonicalVersion" element={<div data-testid="flow-builder">Flow Builder</div>} />,
  ],
}: {
  initialEntries?: string[];
  routes?: React.ReactNode[];
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          {routes}
          <Route path="*" element={<Navigate to="/configuration" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("VendorConfigurationPage - Operations", () => {
  beforeEach(() => {
    localStorage.setItem("integrationHub.activeVendorCode", "LH001");
    vi.clearAllMocks();

    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorMappings).mockResolvedValue({ mappings: [] });
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue({
      items: [
        { operationCode: "GET_RECEIPT", canonicalVersion: "v1" },
        { operationCode: "SEND_INVOICE", canonicalVersion: "v1" },
        { operationCode: "SUBMIT_ORDER", canonicalVersion: "v1" },
      ],
    });
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({
      items: [
        { operationCode: "GET_RECEIPT" },
        { operationCode: "SEND_INVOICE" },
      ],
    });
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue({ outbound: [], inbound: [] });
    vi.mocked(endpointsApi.getMyOperations).mockResolvedValue({ outbound: [], inbound: [] });
  });

  it("shows Configuration Overview page with canonical operations banner", async () => {
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText(/Canonical operations available to add/i)).toBeInTheDocument();
    });
  });

  it("clicking a row opens Flow Builder", async () => {
    const user = userEvent.setup();
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getAllByText(/GET_RECEIPT/).length).toBeGreaterThan(0);
    });

    const cells = screen.getAllByText(/GET_RECEIPT/);
    const cell = cells[0];
    const row = cell.closest("tr");
    expect(row).toBeTruthy();
    await user.click(row!);

    await waitFor(() => {
      expect(screen.getByTestId("flow-builder")).toBeInTheDocument();
    });
  });

  it("shows Add operation control when canonical operations are available to add", async () => {
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
    });

    expect(screen.getByText(/Canonical operations available to add/i)).toBeInTheDocument();
    expect(screen.getByText(/canonical contract is published/i)).toBeInTheDocument();
  });

  it("shows no operations available message when catalog is empty (no admin-approved ops)", async () => {
    vi.mocked(endpointsApi.getVendorConfigBundle).mockRejectedValue(new Error("Bundle not available"));
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({ items: [] });

    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText(/no operations are available/i)).toBeInTheDocument();
    });
  });

  it("shows operation filter when URL has operation param", async () => {
    render(<TestWrapper initialEntries={["/configuration?operation=GET_RECEIPT"]} />);

    await waitFor(() => {
      expect(screen.getByText(/Viewing operation/i)).toBeInTheDocument();
      expect(screen.getByText(/GET_RECEIPT/)).toBeInTheDocument();
    });

    expect(screen.getByText("Clear filter")).toBeInTheDocument();
  });

  it("redirects /contracts to /configuration preserving query params", async () => {
    render(<TestWrapper initialEntries={["/contracts?operation=GET_RECEIPT"]} />);

    await waitFor(() => {
      expect(screen.getByText(/Viewing operation/i)).toBeInTheDocument();
      expect(screen.getByText(/GET_RECEIPT/)).toBeInTheDocument();
    });
  });

  it("overview row shows endpoint missing when fixture has no endpoint for partial config", async () => {
    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT" }],
    });
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorMappings).mockResolvedValue({ mappings: [] });
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue({
      outbound: [],
      inbound: [{ sourceVendor: "*", targetVendor: "LH001", operation: "GET_RECEIPT" }],
      eligibleOperations: [{ operationCode: "GET_RECEIPT", canCallOutbound: false, canReceiveInbound: true }],
    });
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT", supportsInbound: true, supportsOutbound: false }],
    });
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT", canonicalVersion: "v1" }],
    });

    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText(/Canonical operations available to add/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getAllByText(/Configured|Using canonical format|Up to date/i).length
      ).toBeGreaterThan(0);
    });
    await waitFor(() => {
      expect(screen.getAllByText("Missing").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText(/Needs configuration/i).length).toBeGreaterThan(0);
  });

  it("Access pill navigates to access control page with operation and direction params", async () => {
    const user = userEvent.setup();
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getAllByText(/GET_RECEIPT/).length).toBeGreaterThan(0);
    });

    const accessLinks = screen.getAllByRole("link", { name: /Access status/i });
    expect(accessLinks.length).toBeGreaterThan(0);
    await user.click(accessLinks[0]);

    await waitFor(() => {
      expect(screen.getByTestId("access-page")).toBeInTheDocument();
    });
  });

  it("Mapping pill shows Using canonical format and Overall is Ready when my-operations has canonical pass-through", async () => {
    const canonicalPassThroughMyOps = {
      outbound: [
        {
          operationCode: "GET_RECEIPT",
          canonicalVersion: "v1",
          partnerVendorCode: "*",
          direction: "outbound" as const,
          status: "ready" as const,
          hasCanonicalOperation: true,
          hasVendorContract: false,
          hasRequestMapping: false,
          hasResponseMapping: false,
          mappingConfigured: true,
          effectiveMappingConfigured: true,
          mappingRequestSource: "canonical_pass_through" as const,
          mappingResponseSource: "canonical_pass_through" as const,
          usesCanonicalRequestMapping: true,
          usesCanonicalResponseMapping: true,
          usesCanonicalPassThrough: true,
          hasEndpoint: true,
          hasAllowlist: true,
          contractStatus: "OK" as const,
          endpointStatus: "OK" as const,
          issues: [],
        },
      ],
      inbound: [],
    };
    vi.mocked(endpointsApi.getVendorConfigBundle).mockRejectedValue(new Error("Bundle not available"));
    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT", url: "https://example.test/receipt", verificationStatus: "VERIFIED", isActive: true }],
    });
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT", canonicalVersion: "v1" }],
    });
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT", supportsOutbound: true, supportsInbound: false }],
    });
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue({
      outbound: [{ id: "1", sourceVendor: "LH001", targetVendor: "*", operation: "GET_RECEIPT", createdAt: "2024-01-01" }],
      inbound: [],
      eligibleOperations: [{ operationCode: "GET_RECEIPT", canCallOutbound: true, canReceiveInbound: false }],
    });
    vi.mocked(endpointsApi.getMyOperations).mockResolvedValue(canonicalPassThroughMyOps);

    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByTitle(/Using canonical format|canonical pass-through/i)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTitle(/Ready for traffic/i)).toBeInTheDocument();
    });
  });
});
