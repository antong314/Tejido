import type { Phase } from "../types";

// Single source of truth for the phase → label + color mapping in the
// admin surface. Used by the participants table on the session edit
// page and by the participant detail header. The pill style itself
// (radius, padding, font) is shared via the className so updates to
// the visual treatment land everywhere consistently.

const PHASE_STYLES: Record<
  string,
  { bg: string; color: string; label: string }
> = {
  complete: {
    bg: "bg-pill-complete-bg",
    color: "text-pill-complete",
    label: "Complete",
  },
  in_conversation: {
    bg: "bg-pill-active-bg",
    color: "text-pill-active",
    label: "In conversation",
  },
  in_permissions: {
    bg: "bg-pill-pending-bg",
    color: "text-pill-pending",
    label: "Permissions",
  },
  in_addition_permissions: {
    bg: "bg-pill-pending-bg",
    color: "text-pill-pending",
    label: "Addition perms",
  },
  awaiting_consent: {
    bg: "bg-a-bg-subtle",
    color: "text-a-ink-muted",
    label: "Awaiting consent",
  },
  awaiting_addition: {
    bg: "bg-pill-pending-bg",
    color: "text-pill-pending",
    label: "Adding",
  },
  not_started: {
    bg: "bg-a-bg-subtle",
    color: "text-a-ink-faint",
    label: "Not started",
  },
};

interface Props {
  phase: Phase | string;
}

export function PhasePill({ phase }: Props) {
  const s = PHASE_STYLES[phase] ?? {
    bg: "bg-a-bg-subtle",
    color: "text-a-ink-muted",
    label: String(phase),
  };
  return (
    <span
      className={[
        "inline-flex items-center whitespace-nowrap rounded-pill px-2 py-0.5",
        "text-[11px] font-semibold tracking-[0.03em]",
        s.bg,
        s.color,
      ].join(" ")}
    >
      {s.label}
    </span>
  );
}
