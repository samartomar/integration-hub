import { describe, it, expect, vi, beforeEach } from "vitest";
import * as endpointsApi from "../api/endpoints";
vi.mock("../api/endpoints");
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PartnerSandboxPage } from "./PartnerSandboxPage";

function TestWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PartnerSandboxPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PartnerSandboxPage", () => {
  beforeEach(() => {
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
      examples: { request: {}, response: {} },
    });
  });

  it("renders and operation selection works", async () => {
    const user = userEvent.setup();
    render(<TestWrapper />);
    await waitFor(() => {
      expect(screen.getByText(/Sandbox/i)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(endpointsApi.listSandboxCanonicalOperations).toHaveBeenCalled();
    });
    await user.click(screen.getByText(/GET_VERIFY_MEMBER_ELIGIBILITY/i));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalledWith(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        "v1"
      );
    });
  });
});
