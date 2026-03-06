import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MissionControlPage } from "./MissionControlPage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");
vi.mock("frontend-shared", async (importOriginal) => {
  const actual = await importOriginal<typeof import("frontend-shared")>();
  return {
    ...actual,
    PageLayout: ({
      title,
      description,
      right,
      children,
    }: {
      title?: string;
      description?: string;
      right?: ReactNode;
      children?: ReactNode;
    }) => (
      <div>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
        {right}
        {children}
      </div>
    ),
  };
});

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MissionControlPage />
    </QueryClientProvider>
  );
}

describe("MissionControlPage smoke", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    vi.mocked(endpointsApi.getMissionControlTopology).mockResolvedValue({
      nodes: [
        { vendorCode: "LH001", vendorName: "Vendor 1" },
        { vendorCode: "LH002", vendorName: "Vendor 2" },
      ],
      edges: [
        {
          sourceVendorCode: "LH001",
          targetVendorCode: "LH002",
          operationCode: "verifyMember",
          flowDirection: "OUTBOUND",
        },
        {
          sourceVendorCode: "LH002",
          targetVendorCode: "LH001",
          operationCode: "checkCoverage",
          flowDirection: "OUTBOUND",
        },
      ],
    });
    vi.mocked(endpointsApi.getMissionControlActivity).mockResolvedValue({
      items: [
        {
          ts: "2026-03-05T10:00:00Z",
          transactionId: "tx-1",
          correlationId: "corr-1",
          sourceVendorCode: "LH001",
          targetVendorCode: "LH002",
          operationCode: "verifyMember",
          stage: "EXECUTE_SUCCESS",
          statusCode: 200,
        },
        {
          ts: "2026-03-05T10:00:01Z",
          transactionId: "tx-2",
          correlationId: "corr-2",
          sourceVendorCode: "LH002",
          targetVendorCode: "LH001",
          operationCode: "checkCoverage",
          stage: "POLICY_DENY",
          decisionCode: "ALLOWLIST_DENY",
          statusCode: 403,
        },
      ],
      count: 2,
      lookbackMinutes: 10,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders title Mission Control", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Mission Control" })).toBeInTheDocument();
  });

  it("topology fetch triggers API call", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.getMissionControlTopology).toHaveBeenCalledTimes(1);
    });
  });

  it("activity polling fires every 2 seconds", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.getMissionControlActivity).toHaveBeenCalledTimes(1);
    });

    await new Promise((resolve) => setTimeout(resolve, 2_200));
    await waitFor(() => {
      expect(vi.mocked(endpointsApi.getMissionControlActivity).mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  }, 10_000);

  it("pause toggle stops polling", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.getMissionControlActivity).toHaveBeenCalledTimes(1);
    });

    await userEvent.setup().click(
      screen.getByRole("button", { name: "Pause live updates" })
    );
    await new Promise((resolve) => setTimeout(resolve, 2_500));
    expect(endpointsApi.getMissionControlActivity).toHaveBeenCalledTimes(1);
  }, 10_000);

  it("filters update activity list", async () => {
    renderPage();
    const activityHeading = await screen.findByRole("heading", { name: "Live Activity" });
    const activitySection = activityHeading.closest("section");
    if (!activitySection) {
      throw new Error("Live Activity section not found");
    }
    await waitFor(() => {
      expect(within(activitySection).getByText(/verifyMember/)).toBeInTheDocument();
      expect(within(activitySection).getByText(/checkCoverage/)).toBeInTheDocument();
    });

    const [operationSelect, vendorSelect] = screen.getAllByRole("combobox");
    await userEvent.setup().selectOptions(
      operationSelect,
      "verifyMember"
    );
    await userEvent.setup().selectOptions(
      vendorSelect,
      "LH001"
    );

    await waitFor(() => {
      expect(within(activitySection).getByText(/verifyMember/)).toBeInTheDocument();
      expect(within(activitySection).queryByText(/checkCoverage/)).not.toBeInTheDocument();
    });
  });
});
