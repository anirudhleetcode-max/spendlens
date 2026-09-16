import { describe, expect, it, vi, afterEach } from "vitest";
import { inr, inrShort, shiftMonth } from "./format";
import { api, ApiError, tokenStore } from "./api";

describe("format", () => {
  it("uses Indian digit grouping", () => {
    expect(inr(123456.5)).toBe("₹1,23,456.50");
    expect(inrShort(1500)).toBe("₹1.5k");
    expect(inrShort(250000)).toBe("₹2.5L");
  });
  it("shifts months across years", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2025-12", 1)).toBe("2026-01");
  });
});

describe("api error handling", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns validation errors into one readable message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: [{ loc: ["body", "amount"], msg: "Input should be greater than 0" }], status: 422,
    }), { status: 422 })));
    await expect(api("/api/expenses", { method: "POST", json: {} })).rejects.toMatchObject({
      status: 422, message: "amount: Input should be greater than 0",
    });
  });

  it("clears the session on 401 and reports network failures", async () => {
    tokenStore.set("abc");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Invalid or expired session" }), { status: 401 })));
    await expect(api("/api/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(tokenStore.get()).toBeNull();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api("/api/health")).rejects.toMatchObject({ status: 0 });
  });
});
