import { describe, it, expect, vi, beforeEach } from "vitest";
import * as endpointsApi from "../api/endpoints";
vi.mock("../api/endpoints");
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PartnerRuntimePreflightPage } from "./PartnerRuntimePreflightPage";

function TestWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PartnerRuntimePreflightPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PartnerRuntimePreflightPage", () => {
  beforeEach(() => {
    localStorage.setItem("integrationHub.activeVendorCode", "LH001");
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listSandboxCanonicalOperations).mockResolvedValue({
      items: [
        { operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY", latestVersion: "v1", title: "Eligibility" },
      ],
    });
    vi.mocked(endpointsApi.getSandboxCanonicalOperation).mockResolvedValue({
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "v1",
      requestPayloadSchema: {},
      responsePayloadSchema: {},
      examples: {
        request: {},
        response: {},
        requestEnvelope: {
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          version: "v1",
          direction: "REQUEST",
          payload: {},
        },
      },
    });
    vi.mocked(endpointsApi.runCanonicalRuntimePreflight).mockResolvedValue({
      valid: true,
      status: "READY",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      canonicalVersion: "v1",
      sourceVendor: "LH001",
      targetVendor: "LH002",
    });
  });

  it("renders and DRY_RUN with mocked API", async () => {
    const user = userEvent.setup();
    render(<TestWrapper />);
    expect(screen.getByText(/Runtime Preflight/i)).toBeInTheDocument();
    const opButton = await screen.findByText(/GET_VERIFY_MEMBER_ELIGIBILITY/i);
    await user.click(opButton);
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    const runBtn = screen.getByRole("button", { name: /Run Preflight/i });
    await user.click(runBtn);
    await waitFor(() => {
      expect(endpointsApi.runCanonicalRuntimePreflight).toHaveBeenCalled();
    });
    expect(screen.getByText(/READY/i)).toBeInTheDocument();
  });
});
