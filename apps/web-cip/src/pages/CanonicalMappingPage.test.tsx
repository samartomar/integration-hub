import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CanonicalMappingPage } from "./CanonicalMappingPage";
import * as endpointsApi from "../api/endpoints";

vi.mock("../api/endpoints");

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CanonicalMappingPage />
    </QueryClientProvider>
  );
}

describe("CanonicalMappingPage smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listCanonicalMappingOperations).mockResolvedValue({
      items: [
        {
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          version: "1.0",
          title: "Verify Member Eligibility",
          description: "Check member eligibility.",
          vendorPairs: [{ sourceVendor: "LH001", targetVendor: "LH002" }],
        },
        {
          operationCode: "GET_MEMBER_ACCUMULATORS",
          version: "1.0",
          title: "Get Member Accumulators",
          description: "Retrieve member benefit accumulators.",
          vendorPairs: [{ sourceVendor: "LH001", targetVendor: "LH002" }],
        },
      ],
    });
    vi.mocked(endpointsApi.previewCanonicalMapping).mockResolvedValue({
      valid: true,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      mappingDefinitionSummary: { fieldMappings: 2, constants: 0 },
      inputPayload: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
      outputPayload: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
      notes: ["Preview only. No runtime execution performed."],
    });
    vi.mocked(endpointsApi.validateCanonicalMapping).mockResolvedValue({
      valid: true,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      mappingAvailable: true,
      warnings: [],
      notes: ["Preview only. No runtime execution performed."],
    });
  });

  it("renders Canonical Mappings title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Canonical Mappings" })).toBeInTheDocument();
  });

  it("loads and displays operations list", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.listCanonicalMappingOperations).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("Verify Member Eligibility")).toBeInTheDocument();
    expect(screen.getByText("Get Member Accumulators")).toBeInTheDocument();
  });

  it("preview mapping shows output payload", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Preview Mapping" }));
    await waitFor(() => {
      expect(endpointsApi.previewCanonicalMapping).toHaveBeenCalled();
    });
    expect(await screen.findByText(/Output payload/)).toBeInTheDocument();
  });

  it("validation shows result", async () => {
    vi.mocked(endpointsApi.validateCanonicalMapping).mockResolvedValue({
      valid: false,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      mappingAvailable: false,
      warnings: ["No mapping definition for LH001->LH999"],
      notes: ["Preview only. No runtime execution performed."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Validate Mapping" }));
    await waitFor(() => {
      expect(endpointsApi.validateCanonicalMapping).toHaveBeenCalled();
    });
    expect(await screen.findByText(/No mapping definition/)).toBeInTheDocument();
  });

  it("Generate Proposal Package button renders after suggestion", async () => {
    vi.mocked(endpointsApi.suggestCanonicalMapping).mockResolvedValue({
      valid: true,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
      notes: ["AI mapping suggestions are advisory only."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Suggest Mapping" }));
    await waitFor(() => {
      expect(endpointsApi.suggestCanonicalMapping).toHaveBeenCalled();
    });
    expect(screen.getByRole("button", { name: "Generate Proposal Package" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Proposal Markdown" })).toBeInTheDocument();
  });

  it("proposal package section renders with review checklist", async () => {
    vi.mocked(endpointsApi.suggestCanonicalMapping).mockResolvedValue({
      valid: true,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
      notes: ["AI mapping suggestions are advisory only."],
    });
    vi.mocked(endpointsApi.generateCanonicalMappingProposalPackage).mockResolvedValue({
      valid: true,
      proposalPackage: {
        proposalId: "test-proposal-id",
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        direction: "CANONICAL_TO_VENDOR",
        createdAt: "2025-03-06T12:00:00Z",
        deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
        reviewChecklist: ["Confirm canonical source fields are correct."],
        promotionGuidance: ["Review proposal manually."],
        notes: ["Proposal package only. No runtime mapping was changed."],
      },
      notes: [],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Suggest Mapping" }));
    await waitFor(() => {
      expect(endpointsApi.suggestCanonicalMapping).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Proposal Package" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingProposalPackage).toHaveBeenCalled();
    });
    expect(screen.getAllByText(/Proposal Package \(Review Artifact Only\)/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Confirm canonical source fields are correct/)).toBeInTheDocument();
    expect(screen.getByText(/Proposal package only/)).toBeInTheDocument();
  });

  it("Generate Promotion Artifact button renders after proposal package", async () => {
    vi.mocked(endpointsApi.suggestCanonicalMapping).mockResolvedValue({
      valid: true,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
      notes: ["AI mapping suggestions are advisory only."],
    });
    vi.mocked(endpointsApi.generateCanonicalMappingProposalPackage).mockResolvedValue({
      valid: true,
      proposalPackage: {
        proposalId: "test-proposal-id",
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        direction: "CANONICAL_TO_VENDOR",
        createdAt: "2025-03-06T12:00:00Z",
        deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
        reviewChecklist: ["Confirm canonical source fields are correct."],
        promotionGuidance: ["Review proposal manually."],
        notes: ["Proposal package only. No runtime mapping was changed."],
      },
      notes: [],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Suggest Mapping" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Proposal Package" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingProposalPackage).toHaveBeenCalled();
    });
    expect(screen.getByRole("button", { name: "Generate Promotion Artifact" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Promotion Markdown" })).toBeInTheDocument();
  });

  it("promotion artifact section renders after Generate Promotion Artifact", async () => {
    vi.mocked(endpointsApi.suggestCanonicalMapping).mockResolvedValue({
      valid: true,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
      notes: ["AI mapping suggestions are advisory only."],
    });
    vi.mocked(endpointsApi.generateCanonicalMappingProposalPackage).mockResolvedValue({
      valid: true,
      proposalPackage: {
        proposalId: "test-proposal-id",
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        direction: "CANONICAL_TO_VENDOR",
        createdAt: "2025-03-06T12:00:00Z",
        deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
        reviewChecklist: ["Confirm canonical source fields are correct."],
        promotionGuidance: ["Review proposal manually."],
        notes: ["Proposal package only. No runtime mapping was changed."],
      },
      notes: [],
    });
    vi.mocked(endpointsApi.generateCanonicalMappingPromotionArtifact).mockResolvedValue({
      valid: true,
      promotionArtifact: {
        proposalId: "test-proposal-id",
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        direction: "CANONICAL_TO_VENDOR",
        targetDefinitionFile: "apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py",
        recommendedChanges: { unchanged: [], added: [], changed: [] },
        reviewChecklist: ["Confirm proposed target file path is correct."],
        testChecklist: ["Run mapping engine unit tests."],
        notes: ["Promotion artifact only. No mapping definition was changed."],
      },
      pythonSnippet: "# Suggested mapping for GET_VERIFY_MEMBER_ELIGIBILITY",
      markdown: "# Mapping Promotion Artifact",
      notes: [],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Suggest Mapping" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Proposal Package" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingProposalPackage).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Promotion Artifact" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingPromotionArtifact).toHaveBeenCalled();
    });
    expect(screen.getByText(/Promotion Artifact \(Review-Only \/ Manual Apply\)/)).toBeInTheDocument();
    expect(screen.getByText(/eligibility_v1_lh001_lh002\.py/)).toBeInTheDocument();
    expect(screen.getByText(/Promotion artifact only/)).toBeInTheDocument();
  });

  it("promotion markdown section renders after Generate Promotion Markdown", async () => {
    vi.mocked(endpointsApi.suggestCanonicalMapping).mockResolvedValue({
      valid: true,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
      notes: ["AI mapping suggestions are advisory only."],
    });
    vi.mocked(endpointsApi.generateCanonicalMappingProposalPackage).mockResolvedValue({
      valid: true,
      proposalPackage: {
        proposalId: "test-proposal-id",
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        direction: "CANONICAL_TO_VENDOR",
        createdAt: "2025-03-06T12:00:00Z",
        deterministicBaseline: { fieldMappings: 2, constants: 0, warnings: [] },
        reviewChecklist: [],
        promotionGuidance: [],
        notes: [],
      },
      notes: [],
    });
    vi.mocked(endpointsApi.generateCanonicalMappingPromotionMarkdown).mockResolvedValue({
      markdown: "# Mapping Promotion Artifact\n\n**Proposal ID:** `test-proposal-id`",
      proposalId: "test-proposal-id",
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Suggest Mapping" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Proposal Package" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingProposalPackage).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Promotion Markdown" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingPromotionMarkdown).toHaveBeenCalled();
    });
    expect(screen.getByText(/Promotion Markdown \(Review-Only \/ Manual Apply\)/)).toBeInTheDocument();
    expect(screen.getByText(/# Mapping Promotion Artifact/)).toBeInTheDocument();
  });

  it("Generate Scaffold Bundle button renders and scaffold section shows result", async () => {
    vi.mocked(endpointsApi.generateCanonicalMappingScaffoldBundle).mockResolvedValue({
      valid: true,
      scaffoldBundle: {
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        mappingDefinitionFile: "apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py",
        fixtureFile: "apps/api/src/schema/mapping_fixtures/eligibility_v1_lh001_lh002.py",
        testFile: "tests/schema/test_mapping_certification_eligibility_v1_lh001_lh002.py",
        directions: ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"],
        reviewChecklist: ["Confirm vendor pair naming is correct."],
        notes: ["Scaffold only. No mapping was created or applied."],
      },
      mappingDefinitionStub: "# Mapping definition stub",
      fixtureStub: "# Fixture stub",
      testStub: "# Test stub",
      markdown: "# Scaffold Onboarding",
      notes: ["Scaffold only. No mapping was created or applied."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    expect(screen.getByRole("button", { name: "Generate Scaffold Bundle" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Scaffold Bundle" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingScaffoldBundle).toHaveBeenCalled();
    });
    expect(screen.getByText(/Scaffold Bundle \(Onboarding \/ Review-Only/)).toBeInTheDocument();
    expect(screen.getAllByText(/eligibility_v1_lh001_lh002\.py/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Scaffold only. No mapping was created or applied/)).toBeInTheDocument();
  });

  it("Generate Scaffold Markdown button renders and markdown section shows result", async () => {
    vi.mocked(endpointsApi.generateCanonicalMappingScaffoldMarkdown).mockResolvedValue({
      markdown: "# Mapping Scaffold Onboarding\n\n**Operation:** GET_VERIFY_MEMBER_ELIGIBILITY",
      notes: ["Onboarding/review-only artifact."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Scaffold Markdown" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingScaffoldMarkdown).toHaveBeenCalled();
    });
    expect(screen.getByText(/Scaffold Markdown \(Onboarding \/ Review-Only\)/)).toBeInTheDocument();
    expect(screen.getByText(/# Mapping Scaffold Onboarding/)).toBeInTheDocument();
  });

  it("Generate Scaffold Bundle button renders and scaffold section shows result", async () => {
    vi.mocked(endpointsApi.generateCanonicalMappingScaffoldBundle).mockResolvedValue({
      valid: true,
      scaffoldBundle: {
        operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
        version: "1.0",
        sourceVendor: "LH001",
        targetVendor: "LH002",
        mappingDefinitionFile: "apps/api/src/schema/canonical_mappings/eligibility_v1_lh001_lh002.py",
        fixtureFile: "apps/api/src/schema/mapping_fixtures/eligibility_v1_lh001_lh002.py",
        testFile: "tests/schema/test_mapping_certification_eligibility_v1_lh001_lh002.py",
        directions: ["CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"],
        reviewChecklist: ["Confirm vendor pair naming is correct."],
        notes: ["Scaffold only. No mapping was created or applied."],
      },
      mappingDefinitionStub: "# Mapping definition stub",
      fixtureStub: "# Fixture stub",
      testStub: "# Test stub",
      markdown: "# Scaffold Onboarding",
      notes: ["Scaffold only. No mapping was created or applied."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    expect(screen.getByRole("button", { name: "Generate Scaffold Bundle" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Scaffold Markdown" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Scaffold Bundle" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingScaffoldBundle).toHaveBeenCalled();
    });
    expect(screen.getByText(/Scaffold Bundle \(Onboarding \/ Review-Only/)).toBeInTheDocument();
    expect(screen.getAllByText(/eligibility_v1_lh001_lh002\.py/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Scaffold only\. No mapping was created or applied/)).toBeInTheDocument();
  });

  it("scaffold markdown section renders after Generate Scaffold Markdown", async () => {
    vi.mocked(endpointsApi.generateCanonicalMappingScaffoldMarkdown).mockResolvedValue({
      markdown: "# Mapping Scaffold Onboarding\n\n**Operation:** GET_VERIFY_MEMBER_ELIGIBILITY",
      notes: ["Scaffold only. No mapping was created or applied."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Generate Scaffold Markdown" }));
    await waitFor(() => {
      expect(endpointsApi.generateCanonicalMappingScaffoldMarkdown).toHaveBeenCalled();
    });
    expect(screen.getByText(/Scaffold Markdown \(Onboarding \/ Review-Only\)/)).toBeInTheDocument();
    expect(screen.getByText(/# Mapping Scaffold Onboarding/)).toBeInTheDocument();
  });

  it("Run Certification button renders and certification section shows result", async () => {
    vi.mocked(endpointsApi.certifyCanonicalMapping).mockResolvedValue({
      valid: true,
      operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
      version: "1.0",
      sourceVendor: "LH001",
      targetVendor: "LH002",
      direction: "CANONICAL_TO_VENDOR",
      fixtureSet: "default",
      summary: { passed: 2, failed: 0, warnings: 0, status: "PASS" },
      results: [
        { fixtureId: "eligibility-c2v-basic", status: "PASS", inputPayload: {}, expectedOutput: {}, actualOutput: {}, notes: [] },
        { fixtureId: "eligibility-c2v-shape-variation", status: "PASS", inputPayload: {}, expectedOutput: {}, actualOutput: {}, notes: [] },
      ],
      notes: ["Certification is deterministic and fixture-based.", "No runtime execution performed."],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    expect(screen.getByRole("button", { name: "Run Certification" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Run Certification" }));
    await waitFor(() => {
      expect(endpointsApi.certifyCanonicalMapping).toHaveBeenCalled();
    });
    expect(screen.getByText(/Certification \(Fixture-Based Verification Only\)/)).toBeInTheDocument();
    expect(screen.getByText(/PASS: Passed 2, Failed 0/)).toBeInTheDocument();
    expect(screen.getByText(/eligibility-c2v-basic/)).toBeInTheDocument();
  });
});
