/**
 * Tests for Vendor Access control page (VendorAllowlistPage).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as endpointsApi from "../api/endpoints";
import * as changeRequestsApi from "../api/changeRequests";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, Navigate } from "react-router-dom";
import { VendorAllowlistPage } from "./VendorAllowlistPage";

vi.mock("../api/endpoints");
vi.mock("../api/changeRequests");

function TestWrapper({
  initialEntries = ["/configuration/access"],
}: {
  initialEntries?: string[];
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/configuration/access" element={<VendorAllowlistPage />} />
          <Route path="*" element={<Navigate to="/configuration/access" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("VendorAllowlistPage - Access control", () => {
  beforeEach(() => {
    localStorage.setItem("integrationHub.activeVendorCode", "LH001");
    localStorage.setItem("VENDOR_API_KEY::LH001", "test-key");
    vi.clearAllMocks();
    vi.mocked(changeRequestsApi.listMyAllowlistChangeRequests).mockResolvedValue([]);
    vi.mocked(changeRequestsApi.listMyAccessRequestsAllStatuses).mockResolvedValue([]);
    vi.mocked(endpointsApi.getVendorConfigBundle).mockResolvedValue({
      vendorCode: "LH001",
      contracts: [],
      operationsCatalog: [
        { operationCode: "GET_RECEIPT", canonicalVersion: "v1" },
        { operationCode: "GET_WEATHER", canonicalVersion: "v1" },
      ],
      supportedOperations: [
        { operationCode: "GET_RECEIPT", supportsOutbound: true, supportsInbound: false },
        { operationCode: "GET_WEATHER", supportsOutbound: true, supportsInbound: true },
      ],
      endpoints: [],
      mappings: [],
      myAllowlist: {
        outbound: [
          { id: "1", sourceVendor: "LH001", targetVendor: "LH002", operation: "GET_RECEIPT", createdAt: "2024-01-01" },
        ],
        inbound: [
          { id: "2", sourceVendor: "*", targetVendor: "LH001", operation: "GET_WEATHER", createdAt: "2024-01-01" },
        ],
        eligibleOperations: [
          { operationCode: "GET_RECEIPT", canCallOutbound: true, canReceiveInbound: true },
          { operationCode: "GET_WEATHER", canCallOutbound: true, canReceiveInbound: true },
        ],
      },
      myOperations: { outbound: [], inbound: [] },
    });
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue({
      outbound: [
        { id: "1", sourceVendor: "LH001", targetVendor: "LH002", operation: "GET_RECEIPT", createdAt: "2024-01-01" },
      ],
      inbound: [
        { id: "2", sourceVendor: "*", targetVendor: "LH001", operation: "GET_WEATHER", createdAt: "2024-01-01" },
      ],
      eligibleOperations: [
        { operationCode: "GET_RECEIPT", canCallOutbound: true, canReceiveInbound: true },
        { operationCode: "GET_WEATHER", canCallOutbound: true, canReceiveInbound: true },
      ],
    });
    vi.mocked(endpointsApi.listVendors).mockResolvedValue({
      items: [
        { vendorCode: "LH001", vendorName: "Alpha Health" },
        { vendorCode: "LH002", vendorName: "Provider Co" },
      ],
      nextCursor: null,
    });
    vi.mocked(endpointsApi.listOperations).mockResolvedValue({
      items: [
        { operationCode: "GET_RECEIPT", canonicalVersion: "v1" },
        { operationCode: "GET_WEATHER", canonicalVersion: "v1" },
      ],
      nextCursor: null,
    });
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({
      items: [
        { operationCode: "GET_RECEIPT", supportsOutbound: true, supportsInbound: false },
        { operationCode: "GET_WEATHER", supportsOutbound: false, supportsInbound: true },
      ],
    });
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue({
      items: [
        { operationCode: "GET_RECEIPT", canonicalVersion: "v1" },
        { operationCode: "GET_WEATHER", canonicalVersion: "v1" },
      ],
    });
    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorMappings).mockResolvedValue({ mappings: [] });
    vi.mocked(endpointsApi.getMyOperations).mockResolvedValue({ outbound: [], inbound: [] });
  });

  it("shows Access control page with correct heading", async () => {
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Access control/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/Who you can call \(outbound\) and who can call you \(inbound\)/i)).toBeInTheDocument();
  });

  it("renders Outbound and Inbound section headings", async () => {
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /OUTBOUND/i })).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: /INBOUND/i })).toBeInTheDocument();
  });

  it("renders section helpers for Outbound and Inbound", async () => {
    render(<TestWrapper />);

    await waitFor(() => {
      // OUTBOUND and INBOUND appear in headings, table cells, and description - use getAllByText
      expect(screen.getAllByText(/OUTBOUND/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/INBOUND/i).length).toBeGreaterThan(0);
    });
  });

  it("shows stats bar with outbound/inbound sections", async () => {
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getAllByText(/OUTBOUND/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/INBOUND/i).length).toBeGreaterThan(0);
    });
  });

  it("Save rule calls createAllowlistChangeRequest and shows pending approval toast", async () => {
    vi.mocked(changeRequestsApi.createAllowlistChangeRequest).mockResolvedValue({
      id: "cr-1",
      status: "PENDING",
    });
    vi.mocked(endpointsApi.getEligibleAccess).mockResolvedValue({
      outboundTargets: ["LH002"],
      inboundSources: [],
      canUseWildcardOutbound: false,
      canUseWildcardInbound: false,
    });

    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Access control/i })).toBeInTheDocument();
    });

    const addButton = screen.getByRole("button", { name: /Add rule/i });
    await userEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText(/Add access rule/i)).toBeInTheDocument();
    });

    const operationSelect = screen.getByRole("combobox");
    await userEvent.selectOptions(operationSelect, "GET_WEATHER");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Next/i })).toBeInTheDocument();
    });

    const nextButton = screen.getByRole("button", { name: /Next/i });
    await userEvent.click(nextButton);

    await waitFor(() => {
      const select = screen.getByDisplayValue("Select licensee");
      expect(select).toBeInTheDocument();
      return select;
    });

    const partnerSelect = screen.getByDisplayValue("Select licensee");
    await userEvent.selectOptions(partnerSelect, "LH002");

    const saveButton = screen.getByRole("button", { name: /Save rule/i });
    await userEvent.click(saveButton);

    await waitFor(() => {
      expect(changeRequestsApi.createAllowlistChangeRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          direction: "OUTBOUND",
          operationCode: "GET_WEATHER",
          targetVendorCodes: ["LH002"],
          useWildcardTarget: false,
          ruleScope: "vendor",
          requestType: "ALLOWLIST_RULE",
        })
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Access rule submitted for approval. Status: pending admin review./i)
      ).toBeInTheDocument();
    });
  });

  it("provider narrowing flow: GET_WEATHER + LH001 calls createAllowlistChangeRequest with PROVIDER_NARROWING and shows toast", async () => {
    vi.mocked(changeRequestsApi.createAllowlistChangeRequest).mockResolvedValue({
      id: "acr-1",
      status: "PENDING",
      transactionId: "tx-1",
      correlationId: "corr-1",
    });
    vi.mocked(endpointsApi.getVendorConfigBundle).mockResolvedValue({
      vendorCode: "LH001",
      contracts: [],
      operationsCatalog: [
        { operationCode: "GET_RECEIPT", canonicalVersion: "v1" },
        { operationCode: "GET_WEATHER", canonicalVersion: "v1", directionPolicy: "PROVIDER_RECEIVES_ONLY" },
      ],
      supportedOperations: [
        { operationCode: "GET_RECEIPT", supportsOutbound: true, supportsInbound: false },
        { operationCode: "GET_WEATHER", supportsOutbound: true, supportsInbound: true },
      ],
      endpoints: [],
      mappings: [],
      myAllowlist: { outbound: [], inbound: [], eligibleOperations: [] },
      myOperations: { outbound: [], inbound: [] },
    });
    vi.mocked(endpointsApi.postProviderNarrowingCandidates).mockResolvedValue({
      operationCode: "GET_WEATHER",
      callerVendorCodes: ["LH001"],
      candidates: [
        {
          vendorCode: "LH001",
          vendorName: "Alpha Health",
          hasVendorRule: false,
          allowedByAdmin: true,
          requestable: true,
          currentScope: "VENDOR_ONLY",
        },
      ],
    });

    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Access control/i })).toBeInTheDocument();
    });

    const addButton = screen.getByRole("button", { name: /Add rule/i });
    await userEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText(/Add access rule/i)).toBeInTheDocument();
    });

    const operationSelect = screen.getByRole("combobox");
    await userEvent.selectOptions(operationSelect, "GET_WEATHER");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Next/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /Next/i }));

    await waitFor(() => {
      expect(endpointsApi.postProviderNarrowingCandidates).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Save rule/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /Save rule/i }));

    await waitFor(() => {
      expect(changeRequestsApi.createAllowlistChangeRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          direction: "OUTBOUND",
          operationCode: "GET_WEATHER",
          targetVendorCodes: ["LH001"],
          useWildcardTarget: false,
          ruleScope: "vendor",
          requestType: "PROVIDER_NARROWING",
        })
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Access rule submitted for approval. Status: pending admin review./i)
      ).toBeInTheDocument();
    });
  });

  it("inbound provider narrowing: unchecking a caller calls createAllowlistChangeRequest with CALLER_NARROWING", async () => {
    vi.mocked(changeRequestsApi.createAllowlistChangeRequest).mockResolvedValue({
      id: "acr-2",
      status: "PENDING",
      transactionId: "tx-2",
      correlationId: "corr-2",
    });
    vi.mocked(endpointsApi.getVendorConfigBundle).mockResolvedValue({
      vendorCode: "LH001",
      contracts: [],
      operationsCatalog: [
        { operationCode: "GET_WEATHER", canonicalVersion: "v1", directionPolicy: "PROVIDER_RECEIVES_ONLY" },
      ],
      supportedOperations: [
        { operationCode: "GET_WEATHER", supportsOutbound: false, supportsInbound: true },
      ],
      endpoints: [],
      mappings: [],
      myAllowlist: { outbound: [], inbound: [], eligibleOperations: [] },
      myOperations: { outbound: [], inbound: [] },
    });
    vi.mocked(endpointsApi.getProviderNarrowing).mockResolvedValue({
      operationCode: "GET_WEATHER",
      adminEnvelope: ["LH002", "LH003"],
      vendorWhitelist: ["LH002", "LH003"],
    });

    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Access control/i })).toBeInTheDocument();
    });

    const addButton = screen.getByRole("button", { name: /Add rule/i });
    await userEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText(/Add access rule/i)).toBeInTheDocument();
    });

    await userEvent.selectOptions(screen.getByRole("combobox"), "GET_WEATHER");
    await userEvent.click(screen.getByLabelText(/INBOUND/i));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Next/i })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("button", { name: /Next/i }));

    await waitFor(() => {
      expect(endpointsApi.getProviderNarrowing).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Save rule/i })).toBeInTheDocument();
    });

    const lh003Checkbox = screen.getByRole("checkbox", { name: /LH003/i });
    await userEvent.click(lh003Checkbox);

    await userEvent.click(screen.getByRole("button", { name: /Save rule/i }));

    await waitFor(() => {
      expect(changeRequestsApi.createAllowlistChangeRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          direction: "INBOUND",
          operationCode: "GET_WEATHER",
          targetVendorCodes: ["LH002"],
          useWildcardTarget: false,
          ruleScope: "vendor",
          requestType: "CALLER_NARROWING",
        })
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Access rule submitted for approval. Status: pending admin review./i)
      ).toBeInTheDocument();
    });
  });
});
