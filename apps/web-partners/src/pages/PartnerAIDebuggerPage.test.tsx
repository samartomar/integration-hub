import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PartnerAIDebuggerPage } from "./PartnerAIDebuggerPage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PartnerAIDebuggerPage />
    </QueryClientProvider>
  );
}

describe("PartnerAIDebuggerPage smoke", () => {
  beforeEach(() => {
    localStorage.setItem("integrationHub.activeVendorCode", "LH001");
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listPartnerSyntegrisCanonicalOperations).mockResolvedValue({
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
    vi.mocked(endpointsApi.getPartnerSyntegrisCanonicalOperation).mockResolvedValue({
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      title: "Verify Member Eligibility",
      description: "Check member eligibility.",
      versionAliases: ["v1"],
      requestPayloadSchema: { type: "object" },
      responsePayloadSchema: { type: "object" },
      examples: {
        request: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
        response: { memberIdWithPrefix: "LH001-12345", status: "ACTIVE" },
      },
    });
    vi.mocked(endpointsApi.analyzePartnerDebugRequest).mockResolvedValue({
      debugType: "CANONICAL_REQUEST",
      status: "PASS",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Request payload is valid for GET_VERIFY_MEMBER_ELIGIBILITY 1.0.",
      findings: [],
      normalizedArtifacts: { payload: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" } },
      notes: ["Deterministic debugger only. No LLM or vendor endpoint was used."],
    });
    vi.mocked(endpointsApi.analyzePartnerDebugFlowDraft).mockResolvedValue({
      debugType: "FLOW_DRAFT",
      status: "PASS",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Flow draft is valid for GET_VERIFY_MEMBER_ELIGIBILITY 1.0.",
      findings: [],
      normalizedArtifacts: { draft: { name: "Eligibility Flow", operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY" } },
      notes: ["Deterministic debugger only. No LLM or vendor endpoint was used."],
    });
    vi.mocked(endpointsApi.analyzePartnerDebugSandboxResult).mockResolvedValue({
      debugType: "SANDBOX_RESULT",
      status: "PASS",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Sandbox result is valid for GET_VERIFY_MEMBER_ELIGIBILITY 1.0.",
      findings: [
        {
          severity: "INFO",
          code: "MOCK_ONLY",
          title: "Mock-only execution",
          message: "Sandbox result is from mock execution.",
          field: null,
          suggestion: null,
        },
      ],
      normalizedArtifacts: { sandboxResult: { operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY", valid: true } },
      notes: ["Deterministic debugger only. No LLM or vendor endpoint was used."],
    });
  });

  it("renders AI Debugger title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "AI Debugger" })).toBeInTheDocument();
  });

  it("AI toggle renders and defaults OFF", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Enhance with AI/)).toBeInTheDocument();
    });
    const checkbox = screen.getByRole("checkbox", { name: /Enhance with AI/ });
    expect(checkbox).not.toBeChecked();
  });

  it("when AI toggle ON, enhanceWithAi true is passed to API", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByRole("checkbox", { name: /Enhance with AI/ }));
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Analyze Request" }));
    await waitFor(() => {
      expect(endpointsApi.analyzePartnerDebugRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          payload: expect.any(Object),
          enhanceWithAi: true,
        })
      );
    });
  });

  it("fallback aiWarnings render when API returns them", async () => {
    vi.mocked(endpointsApi.analyzePartnerDebugRequest).mockResolvedValue({
      debugType: "CANONICAL_REQUEST",
      status: "PASS",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Request payload is valid.",
      findings: [],
      normalizedArtifacts: {},
      notes: ["Deterministic debugger only."],
      aiWarnings: ["AI enhancement unavailable; deterministic debugger result returned."],
      modelInfo: { provider: "bedrock", enhanced: false, reason: "invoke_failed" },
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Analyze Request" }));
    await waitFor(() => {
      expect(endpointsApi.analyzePartnerDebugRequest).toHaveBeenCalled();
    });
    expect(await screen.findByText(/AI enhancement unavailable/)).toBeInTheDocument();
  });

  it("AI Summary section renders when API returns aiSummary", async () => {
    vi.mocked(endpointsApi.analyzePartnerDebugRequest).mockResolvedValue({
      debugType: "CANONICAL_REQUEST",
      status: "FAIL",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Validation failed.",
      findings: [
        {
          severity: "ERROR",
          code: "X",
          title: "X",
          message: "Invalid date",
          field: "payload.date",
          suggestion: "Use YYYY-MM-DD",
        },
      ],
      normalizedArtifacts: {},
      notes: [],
      aiSummary: "The date field must use YYYY-MM-DD format.",
      remediationPlan: [
        { priority: 1, title: "Fix date", reason: "Invalid format", action: "Use 2025-03-06" },
      ],
      prioritizedNextSteps: ["Correct payload.date format.", "Re-run sandbox validation."],
      aiWarnings: ["AI enhancement is advisory only. Deterministic findings remain authoritative."],
      modelInfo: { provider: "bedrock", modelId: "anthropic.claude-3-haiku", enhanced: true },
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Analyze Request" }));
    await waitFor(() => {
      expect(endpointsApi.analyzePartnerDebugRequest).toHaveBeenCalled();
    });
    expect(await screen.findByText(/The date field must use YYYY-MM-DD format/)).toBeInTheDocument();
    expect(screen.getByText("AI Enhancement (advisory)")).toBeInTheDocument();
    expect(screen.getByText("Fix date")).toBeInTheDocument();
  });
});
