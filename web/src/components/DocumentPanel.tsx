import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  title: string;
  contentMd: string;
}

// Persistent left-column document view used by the split layout
// (document_revision workflow). Unlike SidePanel this is NOT collapsible —
// the participant should never lose sight of the document they're
// reacting to. Scrolls independently of the chat column on the right.

export function DocumentPanel({ title, contentMd }: Props) {
  return (
    <aside className="flex h-full w-[48%] shrink-0 flex-col border-r border-p-border bg-p-bg-card">
      <div className="border-b border-p-border px-8 py-6">
        <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-p-ink-faint">
          The document
        </div>
        <h2 className="mt-1 font-p-display text-[20px] font-normal leading-tight text-p-ink">
          {title}
        </h2>
      </div>
      <article className="prose prose-sm prose-neutral max-w-none flex-1 overflow-y-auto px-8 py-7 text-p-ink prose-headings:mb-3 prose-headings:mt-6 prose-p:my-3 prose-li:my-1 prose-hr:my-6">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{contentMd}</ReactMarkdown>
      </article>
    </aside>
  );
}
