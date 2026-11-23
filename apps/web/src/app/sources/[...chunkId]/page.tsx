"use client";
import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function Source({ params }: { params: Promise<{ chunkId: string[] }> }) {
  const { chunkId } = use(params);
  const id = chunkId.map(decodeURIComponent).join("/");
  const q = useQuery({ queryKey: ["chunk", id], queryFn: async () => (await api<any>(`/v1/kb/chunks/${encodeURIComponent(id)}`)).data });
  if (q.isLoading) return <p>Loading…</p>;
  if (q.isError) return <p role="alert">Source not found.</p>;
  const c = q.data;
  return (
    <article className="card space-y-3">
      <h1 className="text-2xl font-bold">{c.citation}</h1>
      {c.heading && <p className="text-sm text-slate-700">{c.heading}</p>}
      {c.draft_content && <p className="badge bg-amber-200 text-amber-900">Draft content — not yet reviewed by a person</p>}
      <p className="whitespace-pre-wrap">{c.text}</p>
      {c.url && (
        <p>
          Official text: <a href={c.url}>{c.url}</a> {c.effective_date && <span>(current as of {c.effective_date})</span>}
        </p>
      )}
      {c.attribution && <p className="text-sm">Source: {c.attribution}</p>}
    </article>
  );
}
