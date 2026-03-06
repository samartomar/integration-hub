import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AIDebuggerPage } from "./AIDebuggerPage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AIDebuggerPage />
    </QueryClientProvider>
  );
}

describe("AIDebuggerPage smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listSandboxCanonicalOperations).mockResolvedValue({
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
    vi.mocked(endpointsApi.getSandboxCanonicalOperation).mockResolvedValue({
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
    vi.mocked(endpointsApi.analyzeDebugRequest).mockResolvedValue({
      debugType: "CANONICAL_REQUEST",
      status: "PASS",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Request payload is valid for GET_VERIFY_MEMBER_ELIGIBILITY 1.0.",
      findings: [],
      normalizedArtifacts: { payload: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" } },
      notes: ["Deterministic debugger only. No LLM or vendor endpoint was used."],
    });
    vi.mocked(endpointsApi.analyzeDebugFlowDraft).mockResolvedValue({
      debugType: "FLOW_DRAFT",
      status: "PASS",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Flow draft is valid for GET_VERIFY_MEMBER_ELIGIBILITY 1.0.",
      findings: [],
      normalizedArtifacts: { draft: { name: "Eligibility Flow", operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY" } },
      notes: ["Deterministic debugger only. No LLM or vendor endpoint was used."],
    });
    vi.mocked(endpointsApi.analyzeDebugSandboxResult).mockResolvedValue({
      debugType: "SANDBOX_RESULT",
      status: "PASS",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Sandbox result is valid for GET_VERIFY_MEMBER_ELIGIBILITY 1.0.",
      findings: [{ severity: "INFO", code: "MOCK_ONLY", title: "Mock-only execution", message: "Sandbox result is from mock execution.", field: null, suggestion: null }],
      normalizedArtifacts: { sandboxResult: { operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY", valid: true } },
      notes: ["Deterministic debugger only. No LLM or vendor endpoint was used."],
    });
  });

  it("renders AI Debugger title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "AI Debugger" })).toBeInTheDocument();
  });

  it("mode switching works", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Canonical Request" })).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Flow Draft" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sandbox Result" })).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Flow Draft" }));
    expect(screen.getByText("Flow draft (JSON)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze Flow Draft" })).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Sandbox Result" }));
    expect(screen.getByText("Sandbox result (JSON)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze Sandbox Result" })).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Canonical Request" }));
    expect(screen.getByText("Operations")).toBeInTheDocument();
  });

  it("valid request analysis shows PASS", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Analyze Request" }));
    await waitFor(() => {
      expect(endpointsApi.analyzeDebugRequest).toHaveBeenCalled();
    });
    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/Request payload is valid/)).toBeInTheDocument();
  });

  it("invalid request analysis shows findings", async () => {
    vi.mocked(endpointsApi.analyzeDebugRequest).mockResolvedValue({
      debugType: "CANONICAL_REQUEST",
      status: "FAIL",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Request payload validation failed.",
      findings: [
        {
          severity: "ERROR",
          code: "INVALID_DATE_FORMAT",
          title: "Invalid date format",
          message: "Field payload.date must match YYYY-MM-DD.",
          field: "payload.date",
          suggestion: "Use a date like 2025-03-06.",
        },
      ],
      normalizedArtifacts: {},
      notes: ["Deterministic debugger only. No LLM or vendor endpoint was used."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Analyze Request" }));
    await waitFor(() => {
      expect(endpointsApi.analyzeDebugRequest).toHaveBeenCalled();
    });
    expect(await screen.findByText("FAIL")).toBeInTheDocument();
    expect(screen.getByText("Invalid date format")).toBeInTheDocument();
    expect(screen.getByText(/INVALID_DATE_FORMAT/)).toBeInTheDocument();
  });

  it("flow draft analysis renders findings", async () => {
    vi.mocked(endpointsApi.analyzeDebugFlowDraft).mockResolvedValue({
      debugType: "FLOW_DRAFT",
      status: "FAIL",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      summary: "Flow draft validation failed.",
      findings: [
        {
          severity: "ERROR",
          code: "INVALID_TRIGGER_TYPE",
          title: "Invalid trigger type",
          message: "trigger.type must be one of: API, MANUAL.",
          field: "trigger.type",
          suggestion: "Use MANUAL or API for trigger.type.",
        },
      ],
      normalizedArtifacts: {},
      notes: ["Deterministic debugger only. No LLM or vendor endpoint was used."],
    });
    renderPage();
    await userEvent.setup().click(screen.getByRole("button", { name: "Flow Draft" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Analyze Flow Draft" }));
    await waitFor(() => {
      expect(endpointsApi.analyzeDebugFlowDraft).toHaveBeenCalled();
    });
    expect(await screen.findByText("FAIL")).toBeInTheDocument();
    expect(screen.getByText("Invalid trigger type")).toBeInTheDocument();
  });

  it("sandbox result analysis renders findings and notes", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByRole("button", { name: "Sandbox Result" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Analyze Sandbox Result" }));
    await waitFor(() => {
      expect(endpointsApi.analyzeDebugSandboxResult).toHaveBeenCalled();
    });
    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("Mock-only execution")).toBeInTheDocument();
    expect(screen.getByText(/Deterministic debugger only/)).toBeInTheDocument();
  });
});
