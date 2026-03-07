import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CanonicalMappingReadinessPage } from "./CanonicalMappingReadinessPage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CanonicalMappingReadinessPage />
    </QueryClientProvider>
  );
}

describe("CanonicalMappingReadinessPage smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listCanonicalMappingReadiness).mockResolvedValue({
      items: [
        {
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          version: "1.0",
          sourceVendor: "LH001",
          targetVendor: "LH002",
          mappingDefinition: true,
          fixtures: true,
          certification: true,
          runtimeReady: true,
          status: "READY",
          notes: [],
        },
        {
          operationCode: "GET_MEMBER_ACCUMULATORS",
          version: "1.0",
          sourceVendor: "LH001",
          targetVendor: "LH002",
          mappingDefinition: true,
          fixtures: true,
          certification: true,
          runtimeReady: true,
          status: "READY",
          notes: [],
        },
      ],
      summary: { total: 2, ready: 2, inProgress: 0, missing: 0, warn: 0 },
      notes: ["Readiness is derived from existing code-first artifacts. No persistence."],
    });
  });

  it("renders Mapping Readiness title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Mapping Readiness" })).toBeInTheDocument();
  });

  it("loads and displays readiness rows", async () => {
    renderPage();
    expect(await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    expect(screen.getByText("GET_MEMBER_ACCUMULATORS")).toBeInTheDocument();
    expect(screen.getAllByText(/LH001 → LH002/).length).toBeGreaterThanOrEqual(1);
  });

  it("renders status labels", async () => {
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    expect(screen.getAllByText("READY").length).toBeGreaterThanOrEqual(1);
  });

  it("renders summary counts", async () => {
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    expect(screen.getByText(/Total:/)).toBeInTheDocument();
    expect(screen.getByText(/Ready:/)).toBeInTheDocument();
  });

  it("filters affect API request", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
    });
    expect(endpointsApi.listCanonicalMappingReadiness).toHaveBeenCalledWith(undefined);
    await userEvent.setup().type(
      screen.getByPlaceholderText(/e\.g\. GET_VERIFY_MEMBER_ELIGIBILITY/),
      "GET_VERIFY"
    );
    await waitFor(() => {
      expect(endpointsApi.listCanonicalMappingReadiness).toHaveBeenCalledWith(
        expect.objectContaining({ operationCode: "GET_VERIFY" })
      );
    });
  });
});
