"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { Node, mergeAttributes } from "@tiptap/core";
import { EditorContent, NodeViewWrapper, ReactNodeViewRenderer, useEditor, type NodeViewProps } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { SourceFootnote } from "@/components/SourceFootnote";
import { cn } from "@/lib/utils";
import { fromDoc, toDoc, type Sentence } from "@/lib/letterDoc";

export type { Sentence };

type Ctx = { numbering: Record<string, number>; sources: Record<string, any> };

// A citation footnote is an inline atom: people edit the words around it but cannot type inside it, so
// every sentence keeps exactly the sources the reviewer checked.
function CitationView({ node, extension }: NodeViewProps) {
  const ctx = (extension.options as { ctx: Ctx }).ctx;
  const cite = node.attrs.cite as string;
  return (
    <NodeViewWrapper as="span" className="inline">
      <SourceFootnote n={ctx.numbering[cite]} src={ctx.sources[cite]} />
    </NodeViewWrapper>
  );
}

const Citation = Node.create<{ ctx: Ctx }>({
  name: "citation",
  group: "inline",
  inline: true,
  atom: true,
  selectable: false,
  addOptions() {
    return { ctx: { numbering: {}, sources: {} } };
  },
  addAttributes() {
    return { cite: { default: "" } };
  },
  parseHTML() {
    return [{ tag: "span[data-cite]", getAttrs: (el) => ({ cite: (el as HTMLElement).dataset.cite }) }];
  },
  renderHTML({ HTMLAttributes, node }) {
    return ["span", mergeAttributes(HTMLAttributes, { "data-cite": node.attrs.cite }), `[${node.attrs.cite}]`];
  },
  addNodeView() {
    return ReactNodeViewRenderer(CitationView);
  },
});

export function LetterSectionEditor({
  title,
  sentences,
  numbering,
  sources,
  onChange,
}: {
  title: string;
  sentences: Sentence[];
  numbering: Record<string, number>;
  sources: Record<string, any>;
  onChange: (s: Sentence[]) => void;
}) {
  const hasPlaceholder = sentences.some((s) => /\[ADD:/.test(s.text));
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        blockquote: false,
        codeBlock: false,
        code: false,
        horizontalRule: false,
        bold: false,
        italic: false,
        strike: false,
        link: false,
        underline: false,
      }),
      Citation.configure({ ctx: { numbering, sources } }),
    ],
    content: toDoc(sentences),
    editorProps: {
      attributes: {
        "aria-label": `${title} text`,
        "aria-multiline": "true",
        role: "textbox",
        class: cn("input min-h-[2.75rem] space-y-2 text-base leading-relaxed [&_p]:m-0", hasPlaceholder && "border-amber-500 bg-amber-50"),
      },
    },
    onUpdate: ({ editor }) => onChange(fromDoc(editor.getJSON(), sentences)),
  });
  return <EditorContent editor={editor} />;
}
