import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RuntimePreflightPage } from "./RuntimePreflightPage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RuntimePreflightPage />
    </QueryClientProvider>
  );
}

describe("RuntimePreflightPage smoke", () => {
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
        requestEnvelope: {
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          version: "1.0",
          direction: "REQUEST",
          correlationId: "corr-preflight",
          timestamp: "2025-03-06T12:00:00Z",
          context: {},
          payload: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
        },
      },
    });
    vi.mocked(endpointsApi.runCanonicalRuntimePreflight).mockResolvedValue({
      valid: true,
      status: "READY",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      canonicalVersion: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      normalizedEnvelope: { operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY", version: "1.0", direction: "REQUEST" },
      checks: [
        { code: "CANONICAL_OPERATION_RESOLVED", status: "PASS", message: "Canonical operation resolved." },
        { code: "CANONICAL_REQUEST_VALID", status: "PASS", message: "Canonical request envelope is valid." },
      ],
      executionPlan: { mode: "PREFLIGHT_ONLY", canExecute: true, nextStep: "Use existing runtime execute path after preflight passes." },
      notes: ["Preflight only. No vendor endpoint was called."],
    });
  });

  it("renders Runtime Preflight title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Runtime Preflight" })).toBeInTheDocument();
  });

  it("loads and displays operations list", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.listSandboxCanonicalOperations).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
  });

  it("selecting an operation prefills envelope", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalledWith(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        "1.0"
      );
    });
    const textareas = screen.getAllByRole("textbox");
    const textarea = textareas.find((el) => el.tagName === "TEXTAREA") as HTMLTextAreaElement;
    expect(textarea).toBeDefined();
    expect(textarea.value).toContain("operationCode");
    expect(textarea.value).toContain("GET_VERIFY_MEMBER_ELIGIBILITY");
    expect(textarea.value).toContain("memberIdWithPrefix");
  });

  it("valid preflight shows READY result", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Run Preflight" }));
    await waitFor(() => {
      expect(endpointsApi.runCanonicalRuntimePreflight).toHaveBeenCalled();
    });
    expect(await screen.findByText("READY")).toBeInTheDocument();
    expect(screen.getByText(/Preflight only/)).toBeInTheDocument();
  });

  it("invalid preflight shows errors/checks", async () => {
    vi.mocked(endpointsApi.runCanonicalRuntimePreflight).mockResolvedValue({
      valid: false,
      status: "BLOCKED",
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      canonicalVersion: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      errors: [{ field: "envelope.payload.date", message: "must match YYYY-MM-DD" }],
      checks: [
        { code: "CANONICAL_REQUEST_VALID", status: "FAIL", message: "Field envelope.payload.date: must match YYYY-MM-DD" },
      ],
      notes: ["Preflight only. No vendor endpoint was called."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Run Preflight" }));
    await waitFor(() => {
      expect(endpointsApi.runCanonicalRuntimePreflight).toHaveBeenCalled();
    });
    expect(await screen.findByText("BLOCKED")).toBeInTheDocument();
    expect(screen.getAllByText(/must match YYYY-MM-DD/).length).toBeGreaterThan(0);
  });
});
