import { describe, expect, it } from "vitest";
import { isFeatureEnabled } from "./featureFlags";

describe("isFeatureEnabled", () => {
  it("returns true when feature is explicitly enabled", () => {
    expect(isFeatureEnabled({ flow_builder: true }, "flow_builder")).toBe(true);
  });

  it("returns false for unknown feature (safe default)", () => {
    expect(isFeatureEnabled({ flow_builder: true }, "unknown_feature")).toBe(false);
  });

  it("returns false when feature map is missing", () => {
    expect(isFeatureEnabled(undefined, "flow_builder")).toBe(false);
    expect(isFeatureEnabled(null, "flow_builder")).toBe(false);
  });

  it("returns false when feature code is blank", () => {
    expect(isFeatureEnabled({ flow_builder: true }, "")).toBe(false);
    expect(isFeatureEnabled({ flow_builder: true }, "   ")).toBe(false);
  });
});
