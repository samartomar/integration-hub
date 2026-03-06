import { describe, it, expect } from "vitest";
import { buildOperationDirectionMap } from "./directionCapabilities";
import type { MyAllowlistResponse } from "../api/endpoints";

function mkEligible(opCode: string, canCallOutbound: boolean, canReceiveInbound: boolean) {
  return { operationCode: opCode, canCallOutbound, canReceiveInbound };
}

describe("buildOperationDirectionMap", () => {
  it("eligibleOperations outbound only → canConfigureOutbound=true, canConfigureInbound=false", () => {
    const allowlist: MyAllowlistResponse = {
      outbound: [],
      inbound: [],
      eligibleOperations: [mkEligible("GET_WEATHER", true, false)],
    };
    const map = buildOperationDirectionMap(allowlist);
    expect(map["GET_WEATHER"]).toEqual({
      canConfigureOutbound: true,
      canConfigureInbound: false,
    });
  });

  it("eligibleOperations inbound only → canConfigureOutbound=false, canConfigureInbound=true", () => {
    const allowlist: MyAllowlistResponse = {
      outbound: [],
      inbound: [],
      eligibleOperations: [mkEligible("GET_RECEIPT", false, true)],
    };
    const map = buildOperationDirectionMap(allowlist);
    expect(map["GET_RECEIPT"]).toEqual({
      canConfigureOutbound: false,
      canConfigureInbound: true,
    });
  });

  it("eligibleOperations both directions → canConfigureOutbound=true, canConfigureInbound=true", () => {
    const allowlist: MyAllowlistResponse = {
      outbound: [],
      inbound: [],
      eligibleOperations: [mkEligible("GET_WEATHER", true, true)],
    };
    const map = buildOperationDirectionMap(allowlist);
    expect(map["GET_WEATHER"]).toEqual({
      canConfigureOutbound: true,
      canConfigureInbound: true,
    });
  });

  it("no eligibleOperations → empty map, looked-up operation undefined", () => {
    const allowlist: MyAllowlistResponse = {
      outbound: [],
      inbound: [],
      eligibleOperations: [],
    };
    const map = buildOperationDirectionMap(allowlist);
    expect(map["GET_WEATHER"]).toBeUndefined();
    expect(map).toEqual({});
  });

  it("normalizes operation code to uppercase for lookup", () => {
    const allowlist: MyAllowlistResponse = {
      outbound: [],
      inbound: [],
      eligibleOperations: [mkEligible("get_weather", true, false)],
    };
    const map = buildOperationDirectionMap(allowlist);
    expect(map["GET_WEATHER"]).toEqual({
      canConfigureOutbound: true,
      canConfigureInbound: false,
    });
  });
});
