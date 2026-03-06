/**
 * React test for Visual Flow Builder - GET_RECEIPT flow, edit mapping JSON, run test.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as flowsApi from "../api/flows";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/flows");
vi.mock("../api/endpoints");
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { VendorFlowBuilderPage } from "./VendorFlowBuilderPage";
import type { VendorEndpoint, VendorMapping } from "frontend-shared";

const mockFlowData: flowsApi.FlowData = {
  operationCode: "GET_RECEIPT",
  version: "v1",
  canonicalRequestSchema: { properties: { transactionId: { type: "string" } } },
  canonicalResponseSchema: { properties: { receipt: { type: "string" } } },
  vendorRequestSchema: { properties: { txnId: { type: "string" } } },
  vendorResponseSchema: { properties: { result: { type: "string" } } },
  visualModel: null,
  requestMapping: null,
  responseMapping: null,
  requiresRequestMapping: false,
  requiresResponseMapping: false,
  endpoint: { url: "", httpMethod: "POST", timeoutMs: 8000 },
};

const mockMappingsData = {
  operationCode: "GET_RECEIPT",
  canonicalVersion: "v1",
  request: { direction: "CANONICAL_TO_TARGET_REQUEST", mapping: {} },
  response: { direction: "TARGET_TO_CANONICAL_RESPONSE", mapping: {} },
};

/** Partial config fixture: contract configured, endpoint missing, mapping missing, access allowed. */
const PARTIAL_CONFIG_MOCKS = {
  vendorContracts: { items: [{ operationCode: "GET_RECEIPT" }] as { operationCode: string }[] },
  endpoints: { items: [] as VendorEndpoint[] },
  mappings: { mappings: [] as VendorMapping[] },
  catalog: { items: [{ operationCode: "GET_RECEIPT", canonicalVersion: "v1" }] },
  allowlist: {
    outbound: [] as { sourceVendor: string; targetVendor: string; operation: string }[],
    inbound: [{ sourceVendor: "*", targetVendor: "LH001", operation: "GET_RECEIPT" }] as { sourceVendor: string; targetVendor: string; operation: string }[],
  },
  supported: { items: [{ operationCode: "GET_RECEIPT", supportsInbound: true, supportsOutbound: false }] as { operationCode: string; supportsInbound?: boolean; supportsOutbound?: boolean }[] },
};

function TestWrapper({ initialEntries = ["/builder/GET_RECEIPT/v1"] }: { initialEntries?: string[] }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/builder/:operationCode/:canonicalVersion" element={<VendorFlowBuilderPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("VendorFlowBuilderPage", () => {
  beforeEach(() => {
    localStorage.setItem("integrationHub.activeVendorCode", "LH001");
    localStorage.setItem("VENDOR_API_KEY::LH001", "test-key");
    vi.clearAllMocks();
    vi.mocked(flowsApi.getFlow).mockResolvedValue(mockFlowData);
    vi.mocked(flowsApi.testFlow).mockImplementation(async (_, __, payload) => {
      const req = payload.canonicalRequest as Record<string, unknown>;
      const reqMapping = (payload.requestMapping ?? {}) as Record<string, string>;
      const respMapping = (payload.responseMapping ?? {}) as Record<string, string>;
      const vendorReq: Record<string, unknown> = {};
      for (const [outKey, sel] of Object.entries(reqMapping)) {
        if (typeof sel === "string" && sel.startsWith("$.")) {
          const path = sel.slice(2);
          const val = req[path] ?? req[path.split(".").pop() ?? ""];
          vendorReq[outKey] = val;
        }
      }
      const vendorResp = {
        status: "OK",
        receiptId: `R-${req.transactionId ?? "unknown"}`,
        result: `R-${req.transactionId ?? "unknown"}`,
      };
      const canonResp: Record<string, unknown> = {};
      for (const [outKey, sel] of Object.entries(respMapping)) {
        if (typeof sel === "string" && sel.startsWith("$.")) {
          const path = sel.slice(2);
          const val = (vendorResp as Record<string, unknown>)[path];
          canonResp[outKey] = val;
        }
      }
      return {
        canonicalRequest: req,
        vendorRequest: vendorReq,
        vendorResponse: vendorResp,
        canonicalResponse: canonResp,
      };
    });
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT" }],
    });
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue({ outbound: [], inbound: [] });
    vi.mocked(endpointsApi.getOperationMappings).mockResolvedValue(mockMappingsData);
    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue({ items: [] });
    vi.mocked(endpointsApi.getVendorMappings).mockResolvedValue({ mappings: [] });
    vi.mocked(endpointsApi.listAuthProfiles).mockResolvedValue({ items: [], nextCursor: null });
  });

  it("renders for GET_RECEIPT, edits mapping JSON, Run Test reflects mapping", async () => {
    vi.mocked(flowsApi.getFlow).mockResolvedValue({
      ...mockFlowData,
      endpoint: { url: "https://api.example.com/receipt", httpMethod: "POST", timeoutMs: 8000, verificationStatus: "VERIFIED" },
    });
    vi.mocked(endpointsApi.getOperationMappings).mockResolvedValue({
      operationCode: "GET_RECEIPT",
      canonicalVersion: "v1",
      request: { direction: "CANONICAL_TO_TARGET_REQUEST", mapping: { txnId: "$.transactionId" } },
      response: { direction: "TARGET_TO_CANONICAL_RESPONSE", mapping: {} },
    });
    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue({ items: [{ operationCode: "GET_RECEIPT" }] });
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT", verificationStatus: "VERIFIED", url: "https://api.example.com/receipt", isActive: true }],
    });
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue({ items: [{ operationCode: "GET_RECEIPT", canonicalVersion: "v1" }] });
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({ items: [{ operationCode: "GET_RECEIPT", supportsOutbound: true, supportsInbound: true }] });
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue({
      outbound: [{ sourceVendor: "LH001", targetVendor: "LH002", operation: "GET_RECEIPT" }],
      inbound: [],
      eligibleOperations: [{ operationCode: "GET_RECEIPT", canCallOutbound: true, canReceiveInbound: false }],
    });
    const user = userEvent.setup();
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText(/Visual Flow Builder/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "mappings" }));

    const requestTextarea = screen.getByLabelText(/Request mapping \(Canonical/i);
    await user.clear(requestTextarea);
    await user.paste('{"txnId":"$.transactionId"}');

    await user.click(screen.getByRole("button", { name: /test/i }));

    const testTextarea = screen.getByLabelText(/Test request \(canonical format\)/i);
    await user.clear(testTextarea);
    await user.paste('{"transactionId":"TXN-001"}');

    await user.click(screen.getByRole("button", { name: /Run test/i }));

    await waitFor(() => {
      expect(flowsApi.testFlow).toHaveBeenCalled();
      const calls = vi.mocked(flowsApi.testFlow).mock.calls;
      expect(calls.length).toBeGreaterThan(0);
      const [op, ver, payload] = calls[0]!;
      expect(op).toBe("GET_RECEIPT");
      expect(ver).toBe("v1");
      expect(payload).toMatchObject({
        canonicalRequest: { transactionId: "TXN-001" },
        requestMapping: expect.objectContaining({ txnId: "$.transactionId" }),
      });
    });

    await waitFor(() => {
      const preElements = document.querySelectorAll("pre");
      const preText = Array.from(preElements)
        .map((el) => el.textContent ?? "")
        .join(" ");
      expect(preText).toContain("TXN-001");
      expect(preText).toContain("txnId");
    });
  });

  it("shows canonical response checkbox when operation has canonical response schema (GET_RECEIPT)", async () => {
    vi.mocked(endpointsApi.getOperationMappings).mockResolvedValue({
      operationCode: "GET_RECEIPT",
      canonicalVersion: "v1",
      request: { direction: "CANONICAL_TO_TARGET_REQUEST", mapping: {} },
      response: { direction: "TARGET_TO_CANONICAL_RESPONSE", mapping: { receipt: "$.result" } },
    });
    const user = userEvent.setup();
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText(/Visual Flow Builder/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "mappings" }));

    const checkbox = screen.getByRole("checkbox", { name: /Use canonical response format/i });
    expect(checkbox).toBeInTheDocument();
    expect(checkbox).not.toBeChecked();
  });

  it("when useCanonicalResponseFormat checked, Save sends responseMapping null", async () => {
    vi.mocked(endpointsApi.getOperationMappings).mockResolvedValue({
      operationCode: "GET_RECEIPT",
      canonicalVersion: "v1",
      request: null,
      response: null,
    });
    const user = userEvent.setup();
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText(/Visual Flow Builder/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "mappings" }));

    const checkbox = screen.getByRole("checkbox", { name: /Use canonical response format/i });
    await waitFor(() => expect(checkbox).toBeChecked());

    await user.click(checkbox);
    await user.click(checkbox);

    await user.click(screen.getByTestId("flow-builder-save-header"));

    await waitFor(() => {
      expect(endpointsApi.putOperationMappings).toHaveBeenCalledWith(
        "GET_RECEIPT",
        "v1",
        expect.objectContaining({
          response: expect.objectContaining({ mapping: null }),
        })
      );
    });
  });

  it("toggling canonical checkbox does not fire save mutation until Save clicked", async () => {
    vi.mocked(endpointsApi.getOperationMappings).mockResolvedValue({
      ...mockMappingsData,
      request: { direction: "CANONICAL_TO_TARGET_REQUEST", mapping: { txnId: "$.transactionId" } },
      response: { direction: "TARGET_TO_CANONICAL_RESPONSE", mapping: null },
      usesCanonicalRequest: false,
      usesCanonicalResponse: true,
    });

    const user = userEvent.setup();
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText(/Visual Flow Builder/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "mappings" }));

    const reqCheckbox = screen.getByTestId("flow-builder-use-canonical-request");
    await user.click(reqCheckbox);

    expect(endpointsApi.putOperationMappings).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("flow-builder-save-header"));

    await waitFor(() => {
      expect(endpointsApi.putOperationMappings).toHaveBeenCalled();
    });
  });

  it("flow builder operation info shows endpoint missing when readiness has no endpoint", async () => {
    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue(PARTIAL_CONFIG_MOCKS.vendorContracts);
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue(PARTIAL_CONFIG_MOCKS.endpoints);
    vi.mocked(endpointsApi.getVendorMappings).mockResolvedValue(PARTIAL_CONFIG_MOCKS.mappings);
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue(PARTIAL_CONFIG_MOCKS.catalog);
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue(PARTIAL_CONFIG_MOCKS.allowlist);
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue(PARTIAL_CONFIG_MOCKS.supported);

    render(<TestWrapper initialEntries={["/builder/GET_RECEIPT/v1?direction=inbound"]} />);

    await waitFor(() => {
      expect(screen.getByText(/Visual Flow Builder/i)).toBeInTheDocument();
    });

    expect(screen.getByText("Operation info")).toBeInTheDocument();
    await waitFor(() => {
      // Endpoint is missing (no endpoint configured); Missing must appear
      expect(screen.getByText("Missing")).toBeInTheDocument();
      // Contract or mapping may be configured (canonical pass-through); pill uses icon-only when ready, so check title
      const configuredPill = screen.queryByTitle(/Vendor contract is configured|Mapping uses canonical|Request and response mappings configured/i);
      const hasConfigured = configuredPill !== null || screen.getAllByText(/Configured|Using canonical format/i).length > 0;
      expect(hasConfigured).toBe(true);
    });
  });

  it("when both canonical checkboxes checked, shows Mapping uses canonical pass-through banner", async () => {
    vi.mocked(endpointsApi.getOperationMappings).mockResolvedValue({
      operationCode: "GET_RECEIPT",
      canonicalVersion: "v1",
      request: { direction: "CANONICAL_TO_TARGET_REQUEST", mapping: null },
      response: { direction: "TARGET_TO_CANONICAL_RESPONSE", mapping: null },
      usesCanonicalRequest: true,
      usesCanonicalResponse: true,
    });

    const user = userEvent.setup();
    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText(/Visual Flow Builder/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "mappings" }));

    expect(screen.getByText(/Mapping uses canonical pass-through\. No changes required\./i)).toBeInTheDocument();
  });

  it("inbound endpoint helper text references other licensees calling your API", async () => {
    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue(PARTIAL_CONFIG_MOCKS.vendorContracts);
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue(PARTIAL_CONFIG_MOCKS.endpoints);
    vi.mocked(endpointsApi.getVendorMappings).mockResolvedValue(PARTIAL_CONFIG_MOCKS.mappings);
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue(PARTIAL_CONFIG_MOCKS.catalog);
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue(PARTIAL_CONFIG_MOCKS.allowlist);
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue(PARTIAL_CONFIG_MOCKS.supported);

    const user = userEvent.setup();
    render(<TestWrapper initialEntries={["/builder/GET_RECEIPT/v1?direction=inbound"]} />);

    await waitFor(() => {
      expect(screen.getByText(/Visual Flow Builder/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^Endpoint$/i }));

    expect(screen.getAllByText(/other licensees call your API/i).length).toBeGreaterThan(0);
  });

  it("outbound endpoint helper text references routing to target licensee API", async () => {
    vi.mocked(endpointsApi.getVendorContracts).mockResolvedValue(PARTIAL_CONFIG_MOCKS.vendorContracts);
    vi.mocked(endpointsApi.getVendorEndpoints).mockResolvedValue(PARTIAL_CONFIG_MOCKS.endpoints);
    vi.mocked(endpointsApi.getVendorMappings).mockResolvedValue(PARTIAL_CONFIG_MOCKS.mappings);
    vi.mocked(endpointsApi.getVendorOperationsCatalog).mockResolvedValue(PARTIAL_CONFIG_MOCKS.catalog);
    vi.mocked(endpointsApi.getMyAllowlist).mockResolvedValue(PARTIAL_CONFIG_MOCKS.allowlist);
    vi.mocked(endpointsApi.getVendorSupportedOperations).mockResolvedValue({
      items: [{ operationCode: "GET_RECEIPT", supportsInbound: false, supportsOutbound: true }],
    });

    const user = userEvent.setup();
    render(<TestWrapper initialEntries={["/builder/GET_RECEIPT/v1?direction=outbound"]} />);

    await waitFor(() => {
      expect(screen.getByText(/Visual Flow Builder/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^Endpoint$/i }));

    expect(screen.getAllByText(/routes your request/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/target licensee/i).length).toBeGreaterThan(0);
  });
});
