import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  title: string;
  contentMd: string;
}

// Collapsible side panel rendered to the right of the chat for workflows
// that declare ui.side_panel (currently only document_revision). Renders
// the document via react-markdown so admins can paste in real markdown
// (with tables, links, hr, etc.) and have it render the way they expect.

export function SidePanel({ title, contentMd }: Props) {
  const [open, setOpen] = useState(true);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="absolute right-4 top-4 z-10 rounded-full border border-neutral-300 bg-white px-3 py-1 text-xs text-neutral-700 shadow-sm hover:bg-neutral-50"
        title={`Show ${title}`}
      >
        ☰ {title}
      </button>
    );
  }

  return (
    <aside className="flex h-full w-full max-w-md shrink-0 flex-col border-l border-neutral-200 bg-white">
      <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-2.5">
        <div className="text-xs font-semibold uppercase tracking-wide text-neutral-600">
          {title}
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-neutral-500 hover:text-neutral-900"
          title="Hide panel"
        >
          hide
        </button>
      </div>
      <article className="prose prose-sm prose-neutral max-w-none flex-1 overflow-y-auto px-5 py-4 prose-headings:mb-2 prose-headings:mt-4 prose-p:my-2">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{contentMd}</ReactMarkdown>
      </article>
    </aside>
  );
}
