// Tiny client-side router. We have ~5 routes; pulling in
// react-router-dom for that is overkill. App.tsx uses `useRoute()` to
// match the current pathname; `navigate()` pushes a new URL. A
// popstate listener inside the hook keeps the component tree in sync
// with browser back/forward.

import { useEffect, useState } from "react";

export type Route =
  | { name: "session"; sessionId: string }
  | { name: "admin_home" }
  | { name: "admin_new_session" }
  | { name: "admin_edit_session"; sessionId: string }
  | { name: "admin_participant"; sessionId: string; participantId: string }
  | { name: "admin_workflows" }
  | { name: "admin_edit_workflow"; workflowType: string }
  | { name: "welcome" };

const PATTERNS: Array<{ test: RegExp; build: (m: RegExpExecArray) => Route }> = [
  {
    test: /^\/s\/([a-z0-9][a-z0-9_-]*)$/,
    build: (m) => ({ name: "session", sessionId: m[1] }),
  },
  { test: /^\/admin\/?$/, build: () => ({ name: "admin_home" }) },
  {
    test: /^\/admin\/sessions\/new\/?$/,
    build: () => ({ name: "admin_new_session" }),
  },
  {
    // Note: /participants/<pid> match comes BEFORE the bare /:id match
    // so we don't accidentally read "sessions/<id>/participants" as the
    // session-id portion.
    test: /^\/admin\/sessions\/([a-z0-9][a-z0-9_-]*)\/participants\/([a-zA-Z0-9_-]+)\/?$/,
    build: (m) => ({
      name: "admin_participant",
      sessionId: m[1],
      participantId: m[2],
    }),
  },
  {
    test: /^\/admin\/sessions\/([a-z0-9][a-z0-9_-]*)\/?$/,
    build: (m) => ({ name: "admin_edit_session", sessionId: m[1] }),
  },
  // Workflow types are code-defined (not user-creatable) — no /new route.
  {
    test: /^\/admin\/workflows\/?$/,
    build: () => ({ name: "admin_workflows" }),
  },
  {
    test: /^\/admin\/workflows\/([a-z0-9_]+)\/?$/,
    build: (m) => ({ name: "admin_edit_workflow", workflowType: m[1] }),
  },
];

export function matchRoute(pathname: string): Route {
  for (const p of PATTERNS) {
    const m = p.test.exec(pathname);
    if (m) return p.build(m);
  }
  return { name: "welcome" };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() =>
    matchRoute(window.location.pathname),
  );
  useEffect(() => {
    const onPop = () => setRoute(matchRoute(window.location.pathname));
    window.addEventListener("popstate", onPop);
    // Also listen to a custom event our `navigate` dispatches so
    // pushState (which doesn't fire popstate) updates the tree too.
    window.addEventListener("tejido:navigate", onPop as EventListener);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("tejido:navigate", onPop as EventListener);
    };
  }, []);
  return route;
}

export function navigate(path: string): void {
  if (window.location.pathname === path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new Event("tejido:navigate"));
}
