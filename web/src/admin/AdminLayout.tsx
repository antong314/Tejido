import { ReactNode } from "react";
import { navigate } from "../router";

interface Props {
  children: ReactNode;
  title?: string;
}

export function AdminLayout({ children, title }: Props) {
  return (
    <div className="flex h-full flex-col bg-a-bg font-admin text-a-ink">
      <header className="flex h-12 items-center justify-between border-b border-a-border bg-a-bg-card px-6">
        <div className="flex items-center gap-6">
          <a
            href="/admin"
            onClick={(e) => {
              e.preventDefault();
              navigate("/admin");
            }}
            className="font-p-display text-[17px] tracking-[-0.2px] text-a-ink no-underline hover:no-underline"
          >
            tejido
          </a>
          <nav className="flex items-stretch self-stretch text-[13px]">
            <NavLink href="/admin">Sessions</NavLink>
            <NavLink href="/admin/workflows">Workflows</NavLink>
            <NavLink href="/admin/contexts">Contexts</NavLink>
          </nav>
          {title && (
            <span className="text-[13px] text-a-ink-muted">{title}</span>
          )}
        </div>
        <a
          href="/admin/sessions/new"
          onClick={(e) => {
            e.preventDefault();
            navigate("/admin/sessions/new");
          }}
          className="rounded-sm bg-a-accent px-3.5 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-a-accent-dark"
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

function NavLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  // Treat the link as "active" when the current path is at or below this
  // route's prefix. Cheap O(1) check, no need for a context. The header
  // hosts the active border so the underline lines up with the bottom
  // edge of the header.
  const active =
    typeof window !== "undefined" &&
    (window.location.pathname === href ||
      window.location.pathname.startsWith(href + "/"));
  return (
    <a
      href={href}
      onClick={(e) => {
        e.preventDefault();
        navigate(href);
      }}
      className={[
        "flex items-center px-3 transition-colors",
        "border-b-2",
        active
          ? "border-a-accent font-medium text-a-ink"
          : "border-transparent text-a-ink-muted hover:text-a-ink",
      ].join(" ")}
    >
      {children}
    </a>
  );
}
