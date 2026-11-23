"use client";
import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, PLAN_LABELS } from "@/lib/api";

const FIELDS: { key: string; label: string }[] = [
  { key: "insurer", label: "Insurance company" },
  { key: "plan_type", label: "Plan type" },
  { key: "state", label: "State" },
  { key: "claim_number", label: "Claim or reference number" },
  { key: "member_id", label: "Member ID (hidden for privacy)" },
  { key: "service", label: "Service that was denied" },
  { key: "date_of_service", label: "Date of service" },
  { key: "notice_date", label: "Date on the denial letter" },
  { key: "denial_reason", label: "Reason given for the denial" },
  { key: "denial_codes", label: "Denial codes" },
];

export default function Confirm({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const q = useQuery({
    queryKey: ["case", id],
    queryFn: async () => {
      const r = await api<any>(`/v1/cases/${id}`, { caseId: id });
      return { ...r.data, etag: r.headers.get("ETag") };
    },
    refetchInterval: (query) => (["RECEIVED", "EXTRACTING"].includes(query.state.data?.status) ? 800 : false),
  });
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const f = q.data?.extraction?.fields;
    if (f && Object.keys(values).length === 0) {
      const v: Record<string, string> = {};
      for (const { key } of FIELDS) {
        const raw = f[key]?.value;
        v[key] = Array.isArray(raw) ? raw.join(", ") : (raw ?? "");
      }
      setValues(v);
    }
  }, [q.data, values]);

  if (q.isLoading) return <p>Loading…</p>;
  if (q.isError) return <p role="alert">We could not open this case. It may have been deleted.</p>;
  const c = q.data;
  if (["RECEIVED", "EXTRACTING"].includes(c.status))
    return (
      <p role="status" aria-live="polite" className="card">
        Reading your letter and hiding personal details…
      </p>
    );
  if (c.status === "FAILED")
    return (
      <div role="alert" className="card">
        <p className="font-semibold">We could not read this letter.</p>
        <p>{c.error}</p>
        <a href="/start">Try again by pasting the text</a>
      </div>
    );
  if (c.status !== "AWAITING_CONFIRMATION") {
    router.replace(`/cases/${id}`);
    return null;
  }
  const fields = c.extraction.fields;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const changed: Record<string, string> = {};
    for (const { key } of FIELDS) {
      const orig = Array.isArray(fields[key]?.value) ? fields[key].value.join(", ") : (fields[key]?.value ?? "");
      if ((values[key] ?? "") !== orig) changed[key] = values[key];
    }
    try {
      await api(`/v1/cases/${id}/extraction`, { method: "PUT", caseId: id, body: JSON.stringify({ fields: changed }), headers: { "If-Match": c.etag } });
      router.push(`/cases/${id}`);
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <h1 className="text-2xl font-bold">Check the facts</h1>
      <p>We found these details in your letter. Fix anything that is wrong. Nothing is drafted until you confirm.</p>
      {c.extraction.injection_flags?.length > 0 && (
        <p className="rounded-lg bg-amber-50 p-3">Your letter contained text that looked like instructions to a computer. We ignored it.</p>
      )}
      <div className="card space-y-4">
        {FIELDS.map(({ key, label }) => {
          const f = fields[key] ?? {};
          const low = (f.confidence ?? 0) < 0.7;
          return (
            <div key={key} className={low ? "rounded-lg border border-amber-400 bg-amber-50 p-3" : ""}>
              <label htmlFor={key} className="label">
                {label}{" "}
                <span className={`badge ${low ? "bg-amber-200 text-amber-900" : "bg-green-100 text-green-900"}`}>{low ? "Please check" : "Looks right"}</span>
              </label>
              {key === "plan_type" ? (
                <select id={key} className="input" value={values[key] ?? ""} onChange={(e) => setValues({ ...values, [key]: e.target.value })}>
                  <option value="">I am not sure</option>
                  {Object.entries(PLAN_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              ) : key === "denial_reason" ? (
                <textarea id={key} rows={3} className="input" value={values[key] ?? ""} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />
              ) : (
                <input
                  id={key}
                  className="input"
                  type={key.includes("date") ? "date" : "text"}
                  value={values[key] ?? ""}
                  readOnly={key === "member_id"}
                  onChange={(e) => setValues({ ...values, [key]: e.target.value })}
                />
              )}
              {low && f.hint && <p className="mt-1 text-sm text-slate-800">Where to find this: {f.hint}</p>}
            </div>
          );
        })}
      </div>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">
          {error}
        </p>
      )}
      <button type="submit" className="btn" disabled={busy}>
        {busy ? "Saving…" : "These facts are correct"}
      </button>
    </form>
  );
}
