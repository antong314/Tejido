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
    <aside className="flex h-full w-1/2 shrink-0 flex-col border-r border-neutral-200 bg-white">
      <div className="border-b border-neutral-200 px-6 py-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-neutral-600">
          {title}
        </div>
      </div>
      <article className="prose prose-sm prose-neutral max-w-none flex-1 overflow-y-auto px-8 py-6 prose-headings:mb-3 prose-headings:mt-6 prose-p:my-3 prose-li:my-1 prose-hr:my-6">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{contentMd}</ReactMarkdown>
      </article>
    </aside>
  );
}
