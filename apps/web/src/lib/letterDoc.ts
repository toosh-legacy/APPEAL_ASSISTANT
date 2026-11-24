/* eslint-disable @typescript-eslint/no-explicit-any */
// Tiptap document <-> letter sentences. One paragraph per sentence; citations are inline atom nodes.
export type Sentence = { text: string; citations?: string[]; kind?: string; argument_id?: string | null };

export function toDoc(sentences: Sentence[]) {
  return {
    type: "doc",
    content: sentences.map((s) => ({
      type: "paragraph",
      content: [...(s.text ? [{ type: "text", text: s.text }] : []), ...(s.citations ?? []).map((c) => ({ type: "citation", attrs: { cite: c } }))],
    })),
  };
}

/** Paragraph i keeps sentence i's kind and argument; its text and citations come from the editor. */
export function fromDoc(doc: any, previous: Sentence[]): Sentence[] {
  const out: Sentence[] = [];
  (doc.content ?? []).forEach((p: any, i: number) => {
    const parts = p.content ?? [];
    const text = parts
      .filter((n: any) => n.type === "text")
      .map((n: any) => n.text)
      .join("")
      .trim();
    const citations = parts.filter((n: any) => n.type === "citation").map((n: any) => n.attrs.cite);
    if (!text && citations.length === 0) return;
    const prev = previous[i] ?? { kind: "fact", argument_id: null };
    out.push({ ...prev, text, citations });
  });
  return out;
}
