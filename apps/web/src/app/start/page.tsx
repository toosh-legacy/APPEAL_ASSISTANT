"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, saveToken, type CaseCreated, type UploadResponse } from "@/lib/api";

const schema = z.object({
  text: z.string().max(20000, "Paste at most 20,000 characters.").optional(),
  consent: z.literal(true, { errorMap: () => ({ message: "Please confirm to continue." }) }),
});
type Form = z.infer<typeof schema>;

export default function Start() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { register, handleSubmit, formState } = useForm<Form>({ resolver: zodResolver(schema) });

  async function onSubmit(values: Form) {
    setError(null);
    setBusy(true);
    try {
      let body: Record<string, string>;
      if (file) {
        const ext = file.name.split(".").pop()?.toLowerCase();
        if (!["pdf", "txt"].includes(ext ?? "")) throw new Error("Please upload a PDF or a .txt file. Photos are coming soon.");
        if (file.size > 10 * 1024 * 1024) throw new Error("Files can be at most 10 MB.");
        const { data: up } = await api<UploadResponse>("/v1/uploads", {
          method: "POST",
          body: JSON.stringify({ filename: file.name, content_type: file.type || "application/octet-stream", size: file.size }),
        });
        const put = await fetch(up.upload_url, { method: "PUT", body: file, headers: { "x-ms-blob-type": "BlockBlob" } });
        if (!put.ok) throw new Error("The upload did not finish. Please try again.");
        body = { blob_name: up.blob_name };
      } else {
        if (!values.text || values.text.trim().length < 40) throw new Error("Paste the full text of your denial letter.");
        body = { text: values.text };
      }
      const { data } = await api<CaseCreated>("/v1/cases", {
        method: "POST",
        body: JSON.stringify(body),
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
      saveToken(data.id, data.access_token);
      router.push(`/cases/${data.id}/confirm`);
    } catch (e: any) {
      setError(e.message ?? "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
      <h1 className="text-2xl font-bold">Your denial letter</h1>
      <div className="card space-y-3">
        <label htmlFor="text" className="label">
          Paste the text of your letter
        </label>
        <textarea id="text" rows={12} className="input font-mono text-sm" {...register("text")} aria-describedby="text-help" />
        <p id="text-help" className="text-sm text-slate-700">
          Tip: include the whole letter, from the top to the appeal rights section.
        </p>
        <p className="font-semibold">Or upload a file (PDF or .txt, up to 10 MB)</p>
        <label htmlFor="file" className="sr-only">
          Upload your letter
        </label>
        <input id="file" type="file" accept=".pdf,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>
      <div className="card">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1 h-5 w-5" {...register("consent")} />
          <span>
            I understand this is not legal or medical advice, that I am the author of my appeal, and that my letter is processed to draft it. Identifiers are
            tokenized before any AI step. I can delete my case at any time.
          </span>
        </label>
        {formState.errors.consent && (
          <p role="alert" className="mt-2 text-red-800">
            {formState.errors.consent.message}
          </p>
        )}
      </div>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">
          {error}
        </p>
      )}
      <button type="submit" className="btn" disabled={busy}>
        {busy ? "Reading your letter…" : "Continue"}
      </button>
    </form>
  );
}
