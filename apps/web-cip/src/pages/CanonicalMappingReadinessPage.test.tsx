import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CanonicalMappingReadinessPage } from "./CanonicalMappingReadinessPage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <CanonicalMappingReadinessPage />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const mockOnboardingItems = [
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
    nextAction: {
      code: "READY",
      title: "Ready",
      description: "Mapping is fully onboarded.",
      targetRoute: "/admin/canonical-mappings",
      prefill: {
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
      },
    },
  },
  {
    operationCode: "GET_MEMBER_ACCUMULATORS",
    version: "1.0",
    sourceVendor: "LH001",
    targetVendor: "LH002",
    mappingDefinition: true,
    fixtures: false,
    certification: false,
    runtimeReady: true,
    status: "IN_PROGRESS",
    notes: [],
    nextAction: {
      code: "ADD_FIXTURES",
      title: "Add fixtures",
      description: "Mapping definition exists but no fixtures.",
      targetRoute: "/admin/canonical-mappings",
      prefill: {
        operationCode: "GET_MEMBER_ACCUMULATORS",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
      },
    },
  },
];

describe("CanonicalMappingReadinessPage smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listCanonicalMappingOnboardingActions).mockResolvedValue({
      items: mockOnboardingItems,
      summary: { total: 2, ready: 1, inProgress: 1, missing: 0, warn: 0 },
      notes: ["Recommended action is derived from deterministic readiness only."],
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
    expect(endpointsApi.listCanonicalMappingOnboardingActions).toHaveBeenCalledWith(undefined);
    await userEvent.setup().type(
      screen.getByPlaceholderText(/e\.g\. GET_VERIFY_MEMBER_ELIGIBILITY/),
      "GET_VERIFY"
    );
    await waitFor(() => {
      expect(endpointsApi.listCanonicalMappingOnboardingActions).toHaveBeenCalledWith(
        expect.objectContaining({ operationCode: "GET_VERIFY" })
      );
    });
  });

  it("renders Next Action column with action buttons", async () => {
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    expect(screen.getByRole("button", { name: "Ready" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add fixtures" })).toBeInTheDocument();
  });

  it("next action button is clickable", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Add fixtures");
    const addFixturesBtn = screen.getByText("Add fixtures");
    await user.click(addFixturesBtn);
    expect(addFixturesBtn).toBeInTheDocument();
  });

  it("Generate Release Report button appears for READY rows", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    await user.click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    expect(screen.getByRole("button", { name: "Generate Release Report" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Markdown" })).toBeInTheDocument();
  });

  it("release report section renders after generating report", async () => {
    vi.mocked(endpointsApi.generateCanonicalMappingReleaseReport).mockResolvedValue({
      valid: true,
      report: {
        reportId: "r1",
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        status: "READY",
        readyForPromotion: true,
        blockers: [],
        evidence: {
          mappingDefinition: true,
          fixtures: true,
          certification: true,
          runtimeReady: true,
        },
        releaseChecklist: ["Review mapping definition changes.", "Complete manual code review."],
        recommendedNextStep: "Manual code review and promotion.",
        notes: ["Release report only. No code or runtime state was changed."],
      },
      markdown: "# Mapping Release Readiness Report\n\n**Operation:** GET_VERIFY_MEMBER_ELIGIBILITY",
      notes: [],
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    await user.click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await user.click(screen.getByRole("button", { name: "Generate Release Report" }));
    await waitFor(() => {
      expect(screen.getByText("Release Readiness Report")).toBeInTheDocument();
    });
    expect(screen.getByText(/Ready for promotion: Yes/)).toBeInTheDocument();
    expect(screen.getByText(/Review mapping definition changes/)).toBeInTheDocument();
    expect(screen.getByText(/Manual code review and promotion/)).toBeInTheDocument();
  });

  it("markdown artifact renders in report", async () => {
    vi.mocked(endpointsApi.generateCanonicalMappingReleaseReport).mockResolvedValue({
      valid: true,
      report: {
        reportId: "r1",
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        status: "READY",
        readyForPromotion: true,
        blockers: [],
        evidence: {},
        releaseChecklist: [],
        recommendedNextStep: "Manual code review.",
        notes: [],
      },
      markdown: "# Mapping Release Readiness Report\n\n**Operation:** GET_VERIFY_MEMBER_ELIGIBILITY v1.0",
      notes: [],
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    await user.click(screen.getByText("GET_VERIFY_MEMBER_ELIGIBILITY"));
    await user.click(screen.getByRole("button", { name: "Generate Release Report" }));
    await waitFor(() => {
      expect(screen.getByText("Markdown artifact")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Markdown artifact"));
    expect(screen.getByText(/Mapping Release Readiness Report/)).toBeInTheDocument();
  });

  it("candidate rows can be selected for bundle", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBeGreaterThanOrEqual(1);
    await user.click(checkboxes[0]);
    expect(screen.getByText(/selected for bundle/)).toBeInTheDocument();
  });

  it("Generate Release Bundle button works", async () => {
    vi.mocked(endpointsApi.generateCanonicalReleaseBundle).mockResolvedValue({
      valid: true,
      bundle: {
        bundleId: "b1",
        bundleName: "Release Candidate 2026-03-07",
        createdAt: "2026-03-07T12:00:00Z",
        summary: { included: 1, ready: 1, blocked: 0, status: "READY" },
        items: [
          {
            operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
            version: "1.0",
            sourceVendor: "LH001",
            targetVendor: "LH002",
            readyForPromotion: true,
            status: "READY",
            targetDefinitionFile: "apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py",
            evidence: {},
            blockers: [],
          },
        ],
        impactedFiles: ["apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py"],
        verificationChecklist: ["Review all included mapping definition changes."],
        notes: ["Release bundle only. No mappings were changed or applied."],
      },
      markdown: "# Release Candidate 2026-03-07\n\n**Status:** READY",
      notes: [],
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    await user.click(screen.getAllByRole("checkbox")[0]);
    await user.click(screen.getByRole("button", { name: "Generate Release Bundle" }));
    await waitFor(() => {
      expect(screen.getByText("Release Bundle")).toBeInTheDocument();
    });
    expect(screen.getByText(/Status: READY/)).toBeInTheDocument();
  });

  it("bundle summary and impacted files render", async () => {
    vi.mocked(endpointsApi.generateCanonicalReleaseBundle).mockResolvedValue({
      valid: true,
      bundle: {
        bundleId: "b1",
        bundleName: "Test Bundle",
        createdAt: "2026-03-07T12:00:00Z",
        summary: { included: 1, ready: 1, blocked: 0, status: "READY" },
        items: [
          {
            operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
            version: "1.0",
            sourceVendor: "LH001",
            targetVendor: "LH002",
            readyForPromotion: true,
            status: "READY",
            targetDefinitionFile: "apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py",
            evidence: {},
            blockers: [],
          },
        ],
        impactedFiles: ["apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py"],
        verificationChecklist: ["Review all included mapping definition changes."],
        notes: [],
      },
      markdown: "# Test Bundle",
      notes: [],
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("GET_VERIFY_MEMBER_ELIGIBILITY");
    await user.click(screen.getAllByRole("checkbox")[0]);
    await user.click(screen.getByRole("button", { name: "Generate Release Bundle" }));
    await waitFor(() => {
      expect(screen.getByText("Impacted files:")).toBeInTheDocument();
    });
    expect(screen.getByText(/eligibility_v1_lh001_lh002\.py/)).toBeInTheDocument();
  });
});
