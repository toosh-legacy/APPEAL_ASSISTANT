import { describe, expect, it } from "vitest";
import { fromDoc, toDoc, type Sentence } from "./letterDoc";

const sents: Sentence[] = [
  { text: "I ask for a full and fair review.", citations: ["R1"], kind: "legal", argument_id: "full_fair_review" },
  { text: "Please reverse the denial.", citations: [], kind: "request", argument_id: null },
];

describe("letter section editor mapping", () => {
  it("round-trips sentences, citations, kinds and argument ids", () => {
    expect(fromDoc(toDoc(sents), sents)).toEqual(sents);
  });

  it("keeps citations attached when the words around them change", () => {
    const doc = toDoc(sents);
    doc.content[0].content[0] = { type: "text", text: "I am asking for a full and fair review. " };
    const out = fromDoc(doc, sents);
    expect(out[0]).toMatchObject({ text: "I am asking for a full and fair review.", citations: ["R1"], kind: "legal" });
  });

  it("drops sentences the person deleted", () => {
    const doc = toDoc(sents);
    doc.content[1].content = [];
    expect(fromDoc(doc, sents)).toHaveLength(1);
  });
});
