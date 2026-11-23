"use client";
import { use, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { API, api, download, getToken, CATEGORY_LABELS } from "@/lib/api";

const STEPS = [
  { agent: "intake", label: "Read the letter and hid personal details" },
  { agent: "classifier", label: "Worked out why they said no" },
  { agent: "research", label: "Found your rules, deadline and similar cases" },
  { agent: "writer", label: "Drafted your letter" },
  { agent: "reviewer", label: "Checked every sentence against its source" },
];
const ACTIVE = new Set(["CLASSIFYING", "RESEARCHING", "DRAFTING", "REVIEWING", "RECEIVED", "EXTRACTING"]);

function useCase(id: string) {
  return useQuery({
    queryKey: ["case", id],
    queryFn: async () => (await api<any>(`/v1/cases/${id}`, { caseId: id })).data,
    refetchInterval: (q) => (ACTIVE.has(q.state.data?.status) ? 1500 : false),
  });
}

function Progress({ id, status }: { id: string; status: string }) {
  const [done, setDone] = useState<Record<string, number>>({});
  const qc = useQueryClient();
  useEffect(() => {
    const token = getToken(id);
    if (!token) return;
    const es = new EventSource(`${API}/v1/cases/${id}/events?token=${encodeURIComponent(token)}`);
    const onStep = (e: MessageEvent) => {
      const ev = JSON.parse(e.data);
      setDone((d) => ({ ...d, [ev.agent]: (d[ev.agent] ?? 0) + 1 }));
      qc.invalidateQueries({ queryKey: ["case", id] });
    };
    es.addEventListener("step", onStep as any);
    es.addEventListener("status", () => qc.invalidateQueries({ queryKey: ["case", id] }));
    es.addEventListener("needs_category", () => qc.invalidateQueries({ queryKey: ["case", id] }));
    es.onerror = () => es.close();
    return () => es.close();
  }, [id, qc]);
  const finished = ["READY", "NEEDS_HUMAN"].includes(status);
  return (
    <section className="card" aria-labelledby="progress-h">
      <h2 id="progress-h" className="text-lg font-bold">Progress</h2>
      <ol className="mt-2 space-y-1" aria-live="polite">
        {STEPS.map((s) => {
          const ok = finished || (done[s.agent] ?? 0) > 0;
          return (
            <li key={s.agent} className="flex items-center gap-2">
              <span aria-hidden className={`inline-block h-3 w-3 rounded-full ${ok ? "bg-green-600" : "bg-slate-300"}`} />
              <span>{s.label}</span>
              <span className="sr-only">{ok ? "done" : "waiting"}</span>
            </li>
          );
        })}
      </ol>
      {!finished && <p className="mt-2 text-sm">You can close this page. Your case keeps going, and this link brings you back.</p>}
    </section>
  );
}

function SourceFootnote({ n, src }: { n: number; src: any }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button type="button" className="mx-0.5 align-super text-xs font-semibold text-brand-dark underline" aria-label={`Source ${n}: ${src?.citation ?? ""}`}>
          [{n}]
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 max-h-[80vh] w-[92vw] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-xl bg-white p-5">
          <Dialog.Title className="font-bold">{src?.citation}</Dialog.Title>
          <Dialog.Description className="mt-2 whitespace-pre-wrap text-sm">{src?.excerpt}</Dialog.Description>
          {src?.status === "needs_human_review" && <p className="badge mt-2 bg-amber-200 text-amber-900">Draft content — not yet reviewed</p>}
          <p className="mt-3">
            <a href={`/sources/${encodeURIComponent(src?.chunk_id ?? "")}`}>Open the full source</a>
          </p>
          <Dialog.Close className="btn-secondary mt-4">Close</Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function LetterEditor({ id }: { id: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["letter", id], queryFn: async () => (await api<any>(`/v1/cases/${id}/letter`, { caseId: id })).data });
  const [sections, setSections] = useState<any[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [reason, setReason] = useState<Record<string, string>>({});
  useEffect(() => {
    if (q.data) setSections(q.data.sections);
  }, [q.data]);
  const numbering = useMemo(() => {
    const m: Record<string, number> = {};
    for (const s of sections ?? []) for (const x of s.sentences) for (const c of x.citations ?? []) if (!(c in m)) m[c] = Object.keys(m).length + 1;
    return m;
  }, [sections]);
  if (q.isLoading || !sections) return <p>Loading your letter…</p>;
  if (q.isError) return null;
  const L = q.data;
  const placeholders = sections.flatMap((s) => s.sentences.map((x: any) => x.text)).join(" ").match(/\[ADD: [^\]]+\]/g)?.length ?? 0;

  function edit(si: number, xi: number, text: string) {
    setSections((prev) => prev!.map((s, i) => (i !== si ? s : { ...s, sentences: s.sentences.map((x: any, j: number) => (j !== xi ? x : { ...x, text })) })));
  }
  async function save() {
    setMsg(null);
    const r = await api(`/v1/cases/${id}/letter`, { method: "PUT", caseId: id, body: JSON.stringify({ sections }) });
    qc.setQueryData(["letter", id], r.data);
    setMsg("Saved.");
  }
  async function regenerate(sectionId: string) {
    setMsg(null);
    try {
      const r = await api(`/v1/cases/${id}/letter/regenerate`, { method: "POST", caseId: id, body: JSON.stringify({ section_id: sectionId, reason: reason[sectionId] ?? "shorter" }) });
      qc.setQueryData(["letter", id], r.data);
      setSections((r.data as any).sections);
      setMsg("Paragraph regenerated and re-checked.");
    } catch (e: any) {
      setMsg(e.message);
    }
  }
  async function exportAs(fmt: "pdf" | "docx") {
    setMsg(null);
    try {
      await save();
      await download(`/v1/cases/${id}/exports/${fmt}`, id, `appeal-letter.${fmt}`);
    } catch (e: any) {
      setMsg(e.message);
    }
  }
  return (
    <section className="card space-y-4" aria-labelledby="letter-h">
      <h2 id="letter-h" className="text-lg font-bold">Your appeal letter</h2>
      <p className="text-sm">
        Edit anything. Numbers in brackets open the exact source. Fill every <mark className="bg-amber-200">[ADD: …]</mark> before downloading.
      </p>
      {(L.review?.warnings ?? []).filter((w: any) => w.code !== "placeholder").map((w: any, i: number) => (
        <p key={i} className="rounded-lg bg-amber-50 p-2 text-sm">
          {w.message}
        </p>
      ))}
      {sections.map((s, si) => (
        <div key={s.id} className="space-y-2 border-t border-slate-200 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">{s.title}</h3>
            {!["header", "closing"].includes(s.id) && (
              <div className="flex items-center gap-2 text-sm">
                <label htmlFor={`r-${s.id}`} className="sr-only">
                  How to change {s.title}
                </label>
                <select id={`r-${s.id}`} className="input w-auto py-1" value={reason[s.id] ?? "shorter"} onChange={(e) => setReason({ ...reason, [s.id]: e.target.value })}>
                  <option value="shorter">Shorter</option>
                  <option value="firmer">Firmer</option>
                  <option value="add_detail">Add detail</option>
                </select>
                <button type="button" className="btn-secondary py-1" onClick={() => regenerate(s.id)}>
                  Regenerate this paragraph
                </button>
              </div>
            )}
          </div>
          {s.sentences.map((x: any, xi: number) => (
            <div key={xi} className="flex items-start gap-1">
              <label className="sr-only" htmlFor={`s-${si}-${xi}`}>
                {s.title} sentence {xi + 1}
              </label>
              <textarea
                id={`s-${si}-${xi}`}
                className={`input min-h-[2.75rem] text-base ${/\[ADD:/.test(x.text) ? "border-amber-500 bg-amber-50" : ""}`}
                rows={Math.max(1, Math.ceil(x.text.length / 80))}
                value={x.text}
                onChange={(e) => edit(si, xi, e.target.value)}
              />
              <span className="whitespace-nowrap pt-2">
                {(x.citations ?? []).map((c: string) => (
                  <SourceFootnote key={c} n={numbering[c]} src={L.sources[c]} />
                ))}
              </span>
            </div>
          ))}
        </div>
      ))}
      <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-3">
        <button type="button" className="btn-secondary" onClick={save}>
          Save changes
        </button>
        <button type="button" className="btn" disabled={placeholders > 0} onClick={() => exportAs("pdf")}>
          Download PDF
        </button>
        <button type="button" className="btn" disabled={placeholders > 0} onClick={() => exportAs("docx")}>
          Download Word
        </button>
      </div>
      {placeholders > 0 && <p className="text-sm">{placeholders} placeholder(s) still need your information before you can download.</p>}
      {msg && (
        <p role="status" className="text-sm">
          {msg}
        </p>
      )}
    </section>
  );
}

function SimilarCases({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["prec", id], queryFn: async () => (await api<any>(`/v1/cases/${id}/precedents`, { caseId: id })).data });
  if (!q.data) return null;
  const { stats, precedents, explainer, attribution } = q.data;
  return (
    <section className="card space-y-3" aria-labelledby="sim-h">
      <h2 id="sim-h" className="text-lg font-bold">Similar independent reviews in California</h2>
      {stats && stats.enough_data ? (
        <div>
          <p>
            In <strong>{stats.n.toLocaleString()}</strong> California independent medical reviews for <em>{stats.scope}</em>, reviewers overturned the
            plan&apos;s decision in <strong>{Math.round(stats.rate * 100)}%</strong> of cases (95% confidence interval {Math.round(stats.ci_low * 100)}–
            {Math.round(stats.ci_high * 100)}%).
          </p>
          <details className="mt-1">
            <summary>How this changed over the years</summary>
            <table className="mt-2 text-sm">
              <caption className="sr-only">Overturn rate by year</caption>
              <thead>
                <tr>
                  <th className="pr-4 text-left">Year</th>
                  <th className="pr-4 text-right">Reviews</th>
                  <th className="text-right">Overturned</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_year.slice(-8).map((y: any) => (
                  <tr key={y.year}>
                    <td className="pr-4">{y.year}</td>
                    <td className="pr-4 text-right">{y.n}</td>
                    <td className="text-right">{y.n ? Math.round((100 * y.overturned_n) / y.n) : 0}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </div>
      ) : (
        <p>Not enough similar cases to show a rate.</p>
      )}
      <p className="rounded-lg bg-blue-50 p-3 text-sm">{explainer}</p>
      <ul className="space-y-3">
        {precedents.slice(0, 5).map((p: any) => (
          <li key={p.cite_id} className="rounded-lg border border-slate-200 p-3">
            <p className="font-semibold">
              {p.year} · {p.treatment_subcategory ?? p.treatment} · {p.overturned ? "Plan decision overturned" : "Plan decision upheld"}
            </p>
            <p className="mt-1 text-sm">{p.excerpt.slice(0, 280)}…</p>
            <a className="text-sm" href={`/sources/${encodeURIComponent(p.chunk_id)}`}>
              Read the full summary
            </a>
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-700">{attribution}</p>
    </section>
  );
}

export default function Workspace({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const q = useCase(id);
  const [err, setErr] = useState<string | null>(null);
  if (q.isLoading) return <p>Loading…</p>;
  if (q.isError) return <p role="alert">We could not open this case. It may have been deleted, or this browser does not have its access key.</p>;
  const c = q.data;
  if (c.status === "AWAITING_CONFIRMATION") {
    router.replace(`/cases/${id}/confirm`);
    return null;
  }
  const cls = c.classification;
  const dl = c.deadlines?.[0];

  async function pick(category: string) {
    try {
      await api(`/v1/cases/${id}/category`, { method: "POST", caseId: id, body: JSON.stringify({ category }) });
      qc.invalidateQueries({ queryKey: ["case", id] });
    } catch (e: any) {
      setErr(e.message);
    }
  }
  async function del() {
    if (!window.confirm("Delete this case and everything in it? This cannot be undone.")) return;
    await api(`/v1/cases/${id}`, { method: "DELETE", caseId: id });
    router.push("/");
  }

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Your appeal</h1>
      {c.degraded && <p className="rounded-lg bg-amber-50 p-3">This letter was made with our basic template because a service was unavailable.</p>}
      <Progress id={id} status={c.status} />

      {cls && (
        <section className="card" aria-labelledby="why-h">
          <h2 id="why-h" className="text-lg font-bold">Why they said no</h2>
          {c.status === "NEEDS_CATEGORY" ? (
            <div className="mt-2 space-y-2">
              <p>We are not sure what kind of denial this is. Pick the one that best matches your letter:</p>
              {err && <p role="alert">{err}</p>}
              <ul className="space-y-2">
                {cls.choices.map((ch: any) => (
                  <li key={ch.category}>
                    <button type="button" className="btn-secondary w-full justify-start text-left" onClick={() => pick(ch.category)}>
                      <span>
                        <strong>{ch.label}.</strong> {ch.why}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="mt-2 space-y-2">
              <p>
                <strong>{cls.label ?? CATEGORY_LABELS[c.category]}</strong>. {cls.why}
              </p>
              <p>{cls.confidence_words}</p>
              <p>
                <span className="font-semibold">What this usually means: </span>
                {cls.usually_means}
              </p>
              {Object.entries(c.denial_code_notes ?? {}).map(([code, note]) => (
                <p key={code} className="text-sm">
                  Code {code}: {String(note ?? "")}
                </p>
              ))}
            </div>
          )}
        </section>
      )}

      {c.deadlines && (
        <section className="card" aria-labelledby="dl-h">
          <h2 id="dl-h" className="text-lg font-bold">Your deadline</h2>
          {dl ? (
            <div className="mt-2 space-y-2">
              <p className="text-xl">
                {dl.label}: <strong>{new Date(dl.due_date + "T12:00:00").toLocaleDateString("en-US", { dateStyle: "long" })}</strong>
              </p>
              <p>{dl.days_remaining >= 0 ? `${dl.days_remaining} days left.` : "This date may have passed. Check your notice; you may still have options."}</p>
              <p className="text-sm">
                Counted from the date on your letter. Source: <a href={`/sources/${encodeURIComponent(dl.basis_chunk_id)}`}>{dl.basis_citation}</a>
              </p>
              <button type="button" className="btn-secondary" onClick={() => download(`/v1/cases/${id}/exports/ics`, id, "appeal-deadline.ics")}>
                Add to my calendar (.ics)
              </button>
            </div>
          ) : (
            <p className="mt-2">We could not find a cited rule for your plan type, so we do not show a date. Check your letter for the deadline.</p>
          )}
          {c.next_levels?.length > 0 && (
            <div className="mt-3">
              <h3 className="font-semibold">If the appeal is denied</h3>
              <ul className="list-disc pl-6">
                {c.next_levels.map((n: any) => (
                  <li key={n.rule_id}>
                    {n.label} — {n.window_text}. <a href={`/sources/${encodeURIComponent(n.basis_chunk_id)}`}>Source</a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {c.deadlines && <SimilarCases id={id} />}
      {c.letter && <LetterEditor id={id} />}

      {c.evidence && (
        <section className="card" aria-labelledby="ev-h">
          <h2 id="ev-h" className="text-lg font-bold">Evidence to gather</h2>
          <ul className="mt-2 space-y-1">
            {c.evidence.map((e: string) => (
              <li key={e}>
                <label className="flex items-start gap-2">
                  <input type="checkbox" className="mt-1 h-5 w-5" /> <span>{e}</span>
                </label>
              </li>
            ))}
          </ul>
          {c.clinician_request && (
            <details className="mt-3">
              <summary className="font-semibold">Request a letter from your clinician</summary>
              <p className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-100 p-3 text-sm">{c.clinician_request}</p>
            </details>
          )}
        </section>
      )}

      <section className="card">
        <button type="button" className="btn-secondary" onClick={del}>
          Delete this case
        </button>
      </section>
    </div>
  );
}
