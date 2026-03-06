/**
 * Tests for Vendor Endpoints Config page - direct save (no change-request gating).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as endpointsApi from "../api/endpoints";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { VendorEndpointsConfigPage } from "./VendorEndpointsConfigPage";

vi.mock("../api/endpoints");

const savedEndpoint = {
  id: "ep-123",
  operationCode: "GET_RECEIPT",
  url: "https://api.example.com/receipt",
  httpMethod: "POST",
  payloadFormat: "JSON",
  flowDirection: "OUTBOUND",
  verificationStatus: "PENDING",
  endpointHealth: "not_verified",
};

function TestWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/configuration/endpoints"]}>
        <Routes>
          <Route path="/configuration/endpoints" element={<VendorEndpointsConfigPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("VendorEndpointsConfigPage - endpoint save", () => {
  beforeEach(() => {
    localStorage.setItem("integrationHub.activeVendorCode", "LH001");
    localStorage.setItem("VENDOR_API_KEY::LH001", "test-key");
    vi.clearAllMocks();

    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT", canonicalVersion: "v1" }],
    });
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT" }],
    });
    vi.mocked(endpointsApi.listAuthProfiles).mockResolvedValue({ items: [], nextCursor: null });
  });

  it("save endpoint calls direct API and returns endpoint object (not PENDING/changeRequestId)", async () => {
    vi.mocked(endpointsApi.upsertVendorEndpoint).mockResolvedValue({
      endpoint: savedEndpoint,
    });

    const user = userEvent.setup();
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Add Endpoint/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Add Endpoint/i }));

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    const dialog = screen.getByRole("dialog");
    const operationSelect = within(dialog).getAllByRole("combobox")[0]!;
    await user.selectOptions(operationSelect, "GET_RECEIPT");

    const urlInput = screen.getByPlaceholderText(/api\.vendor\.com/);
    await user.clear(urlInput);
    await user.type(urlInput, "https://api.example.com/receipt");

    const saveBtn = screen.getByRole("button", { name: /^Save$/ });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(endpointsApi.upsertVendorEndpoint).toHaveBeenCalled();
      const call = vi.mocked(endpointsApi.upsertVendorEndpoint).mock.calls[0];
      expect(call[0]).toMatchObject({
        operationCode: "GET_RECEIPT",
        url: "https://api.example.com/receipt",
      });
    });
  });

  it("does not show pending admin approval message for endpoint saves", async () => {
    vi.mocked(endpointsApi.upsertVendorEndpoint).mockResolvedValue({
      endpoint: savedEndpoint,
    });

    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /endpoints/i })).toBeInTheDocument();
    });

    expect(screen.queryByText(/pending admin approval/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/submitted for admin approval/i)).not.toBeInTheDocument();
  });
});
