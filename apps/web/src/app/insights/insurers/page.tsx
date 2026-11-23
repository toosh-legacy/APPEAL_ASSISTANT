"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function Insurers() {
  const q = useQuery({ queryKey: ["insurers"], queryFn: async () => (await api<any>("/v1/insights/insurers")).data });
  if (q.isLoading) return <p>Loading…</p>;
  if (q.isError) return <p className="card">Insurer insights are not available yet.</p>;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Insurer insights (Marketplace)</h1>
      <p className="rounded-lg bg-blue-50 p-3 text-sm">{q.data.disclaimer}</p>
      <table className="card w-full text-sm">
        <caption className="sr-only">Claims and appeals by issuer</caption>
        <thead>
          <tr>
            <th className="text-left">Issuer</th>
            <th>State</th>
            <th className="text-right">Denial rate</th>
            <th className="text-right">Appeals filed</th>
            <th className="text-right">Overturned</th>
          </tr>
        </thead>
        <tbody>
          {q.data.issuers.map((r: any, i: number) => (
            <tr key={i}>
              <td>{r.issuer}</td>
              <td className="text-center">{r.state}</td>
              <td className="text-right">{r.denial_rate == null ? "—" : `${(100 * r.denial_rate).toFixed(1)}%`}</td>
              <td className="text-right">{r.appeals_filed ?? "—"}</td>
              <td className="text-right">{r.appeals_overturned ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs">{q.data.source}</p>
    </div>
  );
}
