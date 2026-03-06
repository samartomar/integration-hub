import { describe, it, expect, vi, beforeEach } from "vitest";
import * as endpointsApi from "../api/endpoints";
vi.mock("../api/endpoints");
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PartnerCanonicalExplorerPage } from "./PartnerCanonicalExplorerPage";

function TestWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PartnerCanonicalExplorerPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PartnerCanonicalExplorerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listCanonicalOperations).mockResolvedValue({
      items: [
        { operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY", latestVersion: "v1", title: "Eligibility" },
      ],
    });
  });

  it("renders and loads operations", async () => {
    render(<TestWrapper />);
    await waitFor(() => {
      expect(screen.getByText(/Canonical Explorer/i)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(endpointsApi.listCanonicalOperations).toHaveBeenCalled();
    });
    expect(screen.getByText(/GET_VERIFY_MEMBER_ELIGIBILITY/i)).toBeInTheDocument();
  });
});
