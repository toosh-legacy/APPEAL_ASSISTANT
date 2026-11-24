"use client";
import * as Dialog from "@radix-ui/react-dialog";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function SourceFootnote({ n, src }: { n: number; src: any }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="mx-0.5 inline-flex min-h-6 min-w-6 items-center justify-center align-super text-xs font-semibold text-brand-dark underline"
          aria-label={`Source ${n}: ${src?.citation ?? ""}`}
        >
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
