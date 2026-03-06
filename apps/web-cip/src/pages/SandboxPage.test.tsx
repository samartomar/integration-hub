import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SandboxPage } from "./SandboxPage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SandboxPage />
    </QueryClientProvider>
  );
}

describe("SandboxPage smoke", () => {
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
    vi.mocked(endpointsApi.validateSandboxRequest).mockResolvedValue({
      valid: true,
      errors: [],
      normalizedVersion: "1.0",
    });
    vi.mocked(endpointsApi.runMockSandboxTest).mockResolvedValue({
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      mode: "MOCK",
      valid: true,
      requestPayloadValid: true,
      requestEnvelopeValid: true,
      responseEnvelopeValid: true,
      requestEnvelope: { operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY", direction: "REQUEST" },
      responseEnvelope: { operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY", direction: "RESPONSE" },
      notes: ["Mock sandbox execution only. No vendor endpoint was called."],
    });
  });

  it("renders Sandbox title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Sandbox" })).toBeInTheDocument();
  });

  it("loads and displays operations list", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.listSandboxCanonicalOperations).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("Verify Member Eligibility")).toBeInTheDocument();
  });

  it("selecting an operation shows detail and request editor", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalledWith(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        "1.0"
      );
    });
    expect(screen.getByLabelText("Request payload JSON")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate Request" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Mock Test" })).toBeInTheDocument();
  });

  it("example request populates editor", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    const textarea = screen.getByLabelText("Request payload JSON") as HTMLTextAreaElement;
    expect(textarea.value).toContain("memberIdWithPrefix");
    expect(textarea.value).toContain("LH001-12345");
  });

  it("Validate Request shows success", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Validate Request" }));
    await waitFor(() => {
      expect(endpointsApi.validateSandboxRequest).toHaveBeenCalled();
    });
    expect(await screen.findByText("Valid")).toBeInTheDocument();
  });

  it("Run Mock Test shows requestEnvelope and responseEnvelope", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getSandboxCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Run Mock Test" }));
    await waitFor(() => {
      expect(endpointsApi.runMockSandboxTest).toHaveBeenCalled();
    });
    expect(await screen.findByText(/Pass/)).toBeInTheDocument();
    expect(screen.getByText("Request envelope")).toBeInTheDocument();
    expect(screen.getByText("Response envelope")).toBeInTheDocument();
  });
});
