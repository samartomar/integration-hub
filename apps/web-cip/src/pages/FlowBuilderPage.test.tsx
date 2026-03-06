import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { FlowBuilderPage } from "./FlowBuilderPage";
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
        {title ? <h1>{title}</h1> : null}
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
      <FlowBuilderPage />
    </QueryClientProvider>
  );
}

describe("FlowBuilderPage smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listFlowCanonicalOperations).mockResolvedValue({
      items: [
        {
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          latestVersion: "1.0",
          title: "Verify Member Eligibility",
          description: "Check member eligibility.",
          versions: ["1.0"],
        },
      ],
    });
    vi.mocked(endpointsApi.getFlowCanonicalOperation).mockResolvedValue({
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      title: "Verify Member Eligibility",
      description: "Check member eligibility.",
      versionAliases: ["v1"],
      requestPayloadSchema: { type: "object" },
      responsePayloadSchema: { type: "object" },
      examples: { request: {}, response: {} },
    });
    vi.mocked(endpointsApi.validateFlowDraft).mockResolvedValue({
      valid: true,
      normalizedDraft: {
        name: "Test Flow",
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        trigger: { type: "MANUAL" },
        mappingMode: "CANONICAL_FIRST",
      },
    });
  });

  it("renders Flow Builder title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Flow Builder" })).toBeInTheDocument();
  });

  it("loads and displays operations list", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.listFlowCanonicalOperations).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("Verify Member Eligibility")).toBeInTheDocument();
  });

  it("selecting an operation shows detail and draft form", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getFlowCanonicalOperation).toHaveBeenCalledWith(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        "1.0"
      );
    });
    expect(screen.getByLabelText("Flow Name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate Draft" })).toBeInTheDocument();
  });

  it("validating a draft shows success", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getFlowCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().type(screen.getByLabelText("Flow Name"), "Test Flow");
    await userEvent.setup().type(screen.getByLabelText("Source Vendor"), "LH001");
    await userEvent.setup().type(screen.getByLabelText("Target Vendor"), "LH002");
    await userEvent.setup().click(screen.getByRole("button", { name: "Validate Draft" }));
    await waitFor(() => {
      expect(endpointsApi.validateFlowDraft).toHaveBeenCalled();
    });
    expect(await screen.findByText("Valid")).toBeInTheDocument();
  });

  it("validating invalid draft shows errors", async () => {
    vi.mocked(endpointsApi.validateFlowDraft).mockResolvedValue({
      valid: false,
      errors: [{ message: "name is required and must be non-empty", field: "name" }],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getFlowCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Validate Draft" }));
    await waitFor(() => {
      expect(endpointsApi.validateFlowDraft).toHaveBeenCalled();
    });
    expect(await screen.findByText("Invalid")).toBeInTheDocument();
    expect(screen.getByText(/name is required/)).toBeInTheDocument();
  });
});
