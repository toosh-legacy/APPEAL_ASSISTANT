import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getToken, saveToken, CATEGORY_LABELS, PLAN_LABELS } from "./api";

function mockFetch(status: number, body: unknown, contentType = "application/json") {
  const make = () => new Response(typeof body === "string" ? body : JSON.stringify(body), { status, headers: { "content-type": contentType } });
  const f = vi.fn().mockImplementation(async () => make());
  vi.stubGlobal("fetch", f);
  return f;
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("api()", () => {
  it("sends the case token as a bearer header", async () => {
    saveToken("c1", "tok-123");
    const f = mockFetch(200, { ok: true });
    await api("/v1/cases/c1", { caseId: "c1" });
    const headers = f.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok-123");
  });

  it("sets JSON content type only when there is a body", async () => {
    const f = mockFetch(200, {});
    await api("/x", { method: "POST", body: "{}" });
    expect((f.mock.calls[0][1].headers as Headers).get("Content-Type")).toBe("application/json");
    await api("/x");
    expect((f.mock.calls[1][1].headers as Headers).get("Content-Type")).toBeNull();
  });

  it("turns RFC 9457 problem details into ApiError", async () => {
    mockFetch(409, { title: "Not awaiting confirmation", detail: "Case is READY." }, "application/problem+json");
    const err = await api("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.message).toBe("Not awaiting confirmation: Case is READY.");
  });

  it("falls back to the status text when the error body is not JSON", async () => {
    mockFetch(502, "<html>bad gateway</html>", "text/html");
    const err = await api("/x").catch((e) => e);
    expect(err.status).toBe(502);
  });

  it("returns text for non-JSON responses and exposes headers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("plain", { status: 200, headers: { "content-type": "text/plain", ETag: '"3"' } })));
    const r = await api<string>("/x");
    expect(r.data).toBe("plain");
    expect(r.headers.get("ETag")).toBe('"3"');
  });
});

describe("tokens and labels", () => {
  it("stores tokens per case", () => {
    saveToken("a", "1");
    expect(getToken("a")).toBe("1");
    expect(getToken("b")).toBeNull();
  });

  it("has a label for every denial category and plan type", () => {
    expect(Object.keys(CATEGORY_LABELS)).toHaveLength(8);
    expect(Object.keys(PLAN_LABELS)).toEqual([
      "employer_self_funded",
      "employer_fully_insured",
      "individual_marketplace",
      "medicare_advantage",
      "medicaid_managed_care",
    ]);
  });
});
