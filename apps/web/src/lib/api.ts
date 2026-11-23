// Typed API client. Types are generated from packages/schemas/openapi.json (npm run gen:api).
import type { paths } from "./api-types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type CaseCreated = paths["/v1/cases"]["post"]["responses"]["201"]["content"]["application/json"];
export type UploadResponse = paths["/v1/uploads"]["post"]["responses"]["200"]["content"]["application/json"];

export class ApiError extends Error {
  constructor(
    public status: number,
    public title: string,
    public detail: string,
  ) {
    super(`${title}${detail ? ": " + detail : ""}`);
  }
}

export function saveToken(id: string, token: string) {
  if (typeof window !== "undefined") localStorage.setItem(`case:${id}`, token);
}
export function getToken(id: string): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(`case:${id}`);
}

export async function api<T = any>(path: string, init: RequestInit & { caseId?: string } = {}): Promise<{ data: T; headers: Headers }> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (init.caseId) {
    const t = getToken(init.caseId);
    if (t) headers.set("Authorization", `Bearer ${t}`);
  }
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (!res.ok) {
    let body: any = {};
    try {
      body = await res.json();
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, body.title ?? res.statusText, body.detail ?? "");
  }
  const ct = res.headers.get("content-type") ?? "";
  const data = (ct.includes("json") ? await res.json() : await res.text()) as T;
  return { data, headers: res.headers };
}

export async function download(path: string, caseId: string, filename: string) {
  const t = getToken(caseId);
  const res = await fetch(`${API}${path}`, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
  if (!res.ok) {
    let body: any = {};
    try {
      body = await res.json();
    } catch {
      /* */
    }
    throw new ApiError(res.status, body.title ?? res.statusText, body.detail ?? "");
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export const CATEGORY_LABELS: Record<string, string> = {
  medical_necessity: "Medical necessity",
  prior_authorization: "Prior authorization",
  out_of_network: "Out of network",
  coding_billing_error: "Coding or billing error",
  experimental_investigational: "Experimental or investigational",
  not_covered_benefit: "Not a covered benefit",
  timely_filing: "Timely filing",
  other_unclear: "Other or unclear",
};

export const PLAN_LABELS: Record<string, string> = {
  employer_self_funded: "Employer plan (self-funded)",
  employer_fully_insured: "Employer plan (insured)",
  individual_marketplace: "Individual / Marketplace plan",
  medicare_advantage: "Medicare Advantage",
  medicaid_managed_care: "Medicaid managed care",
};
