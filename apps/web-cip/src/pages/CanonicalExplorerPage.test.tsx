import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { CanonicalExplorerPage } from "./CanonicalExplorerPage";
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
      <CanonicalExplorerPage />
    </QueryClientProvider>
  );
}

describe("CanonicalExplorerPage smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(endpointsApi.listCanonicalOperations).mockResolvedValue({
      items: [
        {
          operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
          latestVersion: "1.0",
          title: "Verify Member Eligibility",
          description: "Check member eligibility for a given date.",
          versions: ["1.0"],
        },
        {
          operationCode: "GET_MEMBER_ACCUMULATORS",
          latestVersion: "1.0",
          title: "Get Member Accumulators",
          description: "Retrieve member benefit accumulators.",
          versions: ["1.0"],
        },
      ],
    });
    vi.mocked(endpointsApi.getCanonicalOperation).mockImplementation(
      async (operationCode: string) => {
        if (operationCode === "GET_VERIFY_MEMBER_ELIGIBILITY") {
          return {
            operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
            version: "1.0",
            title: "Verify Member Eligibility",
            description: "Check member eligibility for a given date.",
            versionAliases: ["v1"],
            requestPayloadSchema: { type: "object", required: ["memberIdWithPrefix", "date"] },
            responsePayloadSchema: { type: "object", required: ["memberIdWithPrefix", "status"] },
            examples: {
              request: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
              response: { memberIdWithPrefix: "LH001-12345", status: "ACTIVE" },
              requestEnvelope: {
                operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
                version: "1.0",
                direction: "REQUEST",
                payload: { memberIdWithPrefix: "LH001-12345", date: "2025-03-06" },
              },
              responseEnvelope: {
                operationCode: "GET_VERIFY_MEMBER_ELIGIBILITY",
                version: "1.0",
                direction: "RESPONSE",
                payload: { memberIdWithPrefix: "LH001-12345", status: "ACTIVE" },
              },
            },
          };
        }
        return {
          operationCode: "GET_MEMBER_ACCUMULATORS",
          version: "1.0",
          title: "Get Member Accumulators",
          description: "Retrieve member benefit accumulators.",
          versionAliases: ["v1"],
          requestPayloadSchema: { type: "object", required: ["memberIdWithPrefix", "asOfDate"] },
          responsePayloadSchema: { type: "object" },
          examples: {
            request: { memberIdWithPrefix: "LH001-12345", asOfDate: "2025-03-06" },
            response: { memberIdWithPrefix: "LH001-12345", planYear: 2025 },
            requestEnvelope: {},
            responseEnvelope: {},
          },
        };
      }
    );
  });

  it("renders Canonical Explorer title", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Canonical Explorer" })).toBeInTheDocument();
  });

  it("loads and displays operations list", async () => {
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.listCanonicalOperations).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("Verify Member Eligibility")).toBeInTheDocument();
    expect(screen.getByText("Get Member Accumulators")).toBeInTheDocument();
  });

  it("selecting an operation shows detail tabs", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getCanonicalOperation).toHaveBeenCalledWith(
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        "1.0"
      );
    });
    expect(screen.getByRole("button", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request schema" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Response schema" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Examples" })).toBeInTheDocument();
  });

  it("Examples tab renders example blocks", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Examples" }));
    expect(screen.getByText("Request payload")).toBeInTheDocument();
    expect(screen.getByText("Response payload")).toBeInTheDocument();
    expect(screen.getByText("Request envelope")).toBeInTheDocument();
    expect(screen.getByText("Response envelope")).toBeInTheDocument();
  });

  it("search filters operations list", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    const searchInput = screen.getByPlaceholderText("Search by code or title…");
    await userEvent.setup().type(searchInput, "accumulator");
    expect(screen.getByText("Get Member Accumulators")).toBeInTheDocument();
    expect(screen.queryByText("Verify Member Eligibility")).not.toBeInTheDocument();
  });

  it("empty state when no operations", async () => {
    vi.mocked(endpointsApi.listCanonicalOperations).mockResolvedValue({ items: [] });
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.listCanonicalOperations).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("No canonical operations registered.")).toBeInTheDocument();
  });

  it("error state when list fails", async () => {
    vi.mocked(endpointsApi.listCanonicalOperations).mockRejectedValue(new Error("Network error"));
    renderPage();
    await waitFor(() => {
      expect(endpointsApi.listCanonicalOperations).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText(/Failed to load operations/)).toBeInTheDocument();
  });

  it("Request Schema tab shows schema content", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Request schema" }));
    expect(screen.getByText("Request payload schema")).toBeInTheDocument();
    expect(screen.getByText(/memberIdWithPrefix/)).toBeInTheDocument();
  });

  it("Response Schema tab shows schema content", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Verify Member Eligibility")).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByText("Verify Member Eligibility"));
    await waitFor(() => {
      expect(endpointsApi.getCanonicalOperation).toHaveBeenCalled();
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Response schema" }));
    expect(screen.getByText("Response payload schema")).toBeInTheDocument();
    expect(screen.getByText(/memberIdWithPrefix/)).toBeInTheDocument();
  });
});
