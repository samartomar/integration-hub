import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CanonicalExecutePage } from "./CanonicalExecutePage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <CanonicalExecutePage />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("CanonicalExecutePage smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listSandboxCanonicalOperations).mockResolvedValue({
      items: [
        {
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          latestVersion: "1.0",
          title: "Verify Member Eligibility",
          versions: ["1.0"],
        },
      ],
    });
    vi.mocked(endpointsApi.getSandboxCanonicalOperation).mockResolvedValue({
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      title: "Verify Member Eligibility",
      versionAliases: ["v1"],
      requestPayloadSchema: { type: "object" },
      responsePayloadSchema: { type: "object" },
      examples: {
        request: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
        response: {},
        requestEnvelope: {
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          version: "1.0",
          direction: "REQUEST",
          correlationId: "corr-exec",
          timestamp: "2025-03-06T12:00:00Z",
          context: {},
          payload: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
        },
      },
    });
    vi.mocked(endpointsApi.runCanonicalBridgeExecution).mockResolvedValue({
      mode: "DRY_RUN",
      valid: true,
      status: "READY",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      canonicalVersion: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      executeRequestPreview: { targetVendor: "LH002", operation: "GET_VERIFY_MEMBER_ELIGIBILITY", parameters: {} },
      executionPlan: { canExecute: true, reason: "Preflight passed." },
      notes: ["Bridge uses the existing execute path."],
    });
  });

  it("renders Canonical Execute title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Canonical Execute" })).toBeInTheDocument();
  });

  it("loads operations and shows mode selector", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.listSandboxCanonicalOperations).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    expect(screen.getByText("Mode")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveValue("DRY_RUN");
  });

  it("DRY_RUN run shows READY result", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => {
      expect(endpointsApi.runCanonicalBridgeExecution).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceVendor: "LH001",
          targetVendor: "LH002",
          mode: "DRY_RUN",
        })
      );
    });
    expect(await screen.findByText("READY")).toBeInTheDocument();
  });
});
