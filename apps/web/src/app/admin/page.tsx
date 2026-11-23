"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { API } from "@/lib/api";

async function adminGet(path: string, token: string) {
  const r = await fetch(`${API}${path}`, { headers: { "X-Admin-Token": token } });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

export default function Admin() {
  const [token, setToken] = useState("");
  const [active, setActive] = useState("");
  const traces = useQuery({ queryKey: ["traces", active], queryFn: () => adminGet("/admin/v1/traces?limit=10", active), enabled: !!active });
  const evals = useQuery({ queryKey: ["evals", active], queryFn: () => adminGet("/admin/v1/evals", active), enabled: !!active });
  const datasets = useQuery({ queryKey: ["datasets", active], queryFn: () => adminGet("/admin/v1/datasets", active), enabled: !!active });

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Operator dashboard</h1>
      <form
        className="card flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setActive(token);
        }}
      >
        <div>
          <label htmlFor="tok" className="label">
            Admin token (from .env)
          </label>
          <input id="tok" type="password" className="input" value={token} onChange={(e) => setToken(e.target.value)} />
        </div>
        <button className="btn" type="submit">
          Open
        </button>
      </form>
      {traces.isError && <p role="alert">Token rejected.</p>}

      {evals.data && (
        <section className="card" aria-labelledby="ev">
          <h2 id="ev" className="text-lg font-bold">
            Evaluations (latest first)
          </h2>
          <table className="mt-2 w-full text-sm">
            <caption className="sr-only">Eval runs</caption>
            <thead>
              <tr>
                <th className="text-left">Suite</th>
                <th className="text-left">Result</th>
                <th className="text-left">When</th>
              </tr>
            </thead>
            <tbody>
              {evals.data.runs.slice(0, 30).map((r: any, i: number) => (
                <tr key={i}>
                  <td>{r.suite}</td>
                  <td>{r.passed ? "PASS" : "FAIL"}</td>
                  <td>{String(r.at).slice(0, 19)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {datasets.data && (
        <section className="card" aria-labelledby="ds">
          <h2 id="ds" className="text-lg font-bold">
            Data refresh status
          </h2>
          <table className="mt-2 w-full text-sm">
            <caption className="sr-only">Datasets</caption>
            <thead>
              <tr>
                <th className="text-left">Dataset</th>
                <th className="text-right">Rows</th>
                <th className="text-left">Source</th>
                <th className="text-left">Downloaded</th>
                <th className="text-left">Schema</th>
                <th className="text-left">SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {datasets.data.loaded.map((d: any) => (
                <tr key={d.name}>
                  <td>{d.name}</td>
                  <td className="text-right">{d.rows}</td>
                  <td>{d.source}</td>
                  <td>{d.downloaded_at?.slice(0, 19)}</td>
                  <td>{d.schema_ok ? "OK" : "FAILED"}</td>
                  <td className="font-mono">{d.sha256?.slice(0, 12)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {traces.data && (
        <section className="card space-y-3" aria-labelledby="tr">
          <h2 id="tr" className="text-lg font-bold">
            Recent case traces (redacted)
          </h2>
          {traces.data.cases.map((c: any) => (
            <details key={c.case_id} className="rounded-lg border border-slate-200 p-2">
              <summary>
                {c.case_id.slice(0, 8)} · {c.status} {c.degraded ? "· degraded" : ""}
              </summary>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap bg-slate-100 p-2 text-xs">{c.redacted_input}</pre>
              <table className="mt-2 w-full text-xs">
                <caption className="sr-only">Agent steps</caption>
                <thead>
                  <tr>
                    <th className="text-left">Agent</th>
                    <th className="text-right">ms</th>
                    <th className="text-left">Prompt</th>
                    <th className="text-left">Provider</th>
                    <th className="text-right">Tokens in/out</th>
                  </tr>
                </thead>
                <tbody>
                  {c.steps.map((s: any, i: number) => (
                    <tr key={i}>
                      <td>{s.agent}</td>
                      <td className="text-right">{s.latency_ms}</td>
                      <td>{s.prompt_id ? `${s.prompt_id}@${s.prompt_version}` : "—"}</td>
                      <td>{s.provider}</td>
                      <td className="text-right">
                        {s.tokens_in}/{s.tokens_out}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ))}
        </section>
      )}
    </div>
  );
}
