import { describe, it, expect } from "vitest";
import { formatVersionLabel } from "./flowReadiness";

describe("formatVersionLabel", () => {
  it("keeps v1 as v1", () => {
    expect(formatVersionLabel("v1")).toBe("v1");
  });
  it("fixes vv1 to v1", () => {
    expect(formatVersionLabel("vv1")).toBe("v1");
  });
  it("fixes vv2 to v2", () => {
    expect(formatVersionLabel("vv2")).toBe("v2");
  });
  it("adds v prefix when missing", () => {
    expect(formatVersionLabel("1")).toBe("v1");
  });
  it("handles empty as v1", () => {
    expect(formatVersionLabel("")).toBe("v1");
  });
  it("handles null/undefined as v1", () => {
    expect(formatVersionLabel(null)).toBe("v1");
    expect(formatVersionLabel(undefined)).toBe("v1");
  });
  it("normalizes uppercase v prefix (V1)", () => {
    expect(formatVersionLabel("V1")).toBe("v1");
  });
  it("trims whitespace before normalizing", () => {
    expect(formatVersionLabel(" v1 ")).toBe("v1");
    expect(formatVersionLabel("  vv1  ")).toBe("v1");
  });
});
