import { ReactNode } from "react";
import { navigate } from "../router";

interface Props {
  children: ReactNode;
  title?: string;
}

export function AdminLayout({ children, title }: Props) {
  return (
    <div className="flex h-full flex-col bg-neutral-50">
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-6 py-3">
        <div className="flex items-center gap-6">
          <a
            href="/admin"
            onClick={(e) => {
              e.preventDefault();
              navigate("/admin");
            }}
            className="text-sm font-semibold text-neutral-900 hover:underline"
          >
            Tejido admin
          </a>
          {title && (
            <span className="text-sm text-neutral-600">{title}</span>
          )}
        </div>
        <a
          href="/admin/sessions/new"
          onClick={(e) => {
            e.preventDefault();
            navigate("/admin/sessions/new");
          }}
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-800"
        >
          + New workflow
        </a>
      </header>
      <main className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-4xl">{children}</div>
      </main>
    </div>
  );
}
