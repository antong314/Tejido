"""Per-workflow-type admin overrides for the editable prompt fragments.

Workflow types are code-defined (the field schemas, processor mappings,
and UI hints have runtime implications and can't safely be JSON-edited).
But three string fragments inside each workflow ARE admin-editable:

  * task_framing      — the "what kind of conversation" wrapper around the
                        facilitator system prompt. The default lives at
                        WORKFLOW_TYPES[type].default_task_framing.
  * output_template   — the post-conversation processor's system prompt
                        (synthesis / proposal / revise). The default lives
                        at WORKFLOW_TYPES[type].default_output_template.
  * mechanics_override — optional override for the global FACILITATOR_MECHANICS
                        block. If empty, the system default is used.

This module owns the on-disk JSON files at `config/workflows/<type>.json`
and a tiny resolver API the rest of the codebase calls to get the
effective (override-or-default) value.

JSON shape (any field can be empty, in which case the default applies):

    {
      "type": "open_discussion",
      "task_framing": "...",
      "output_template": "...",
      "mechanics_override": ""
    }
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .prompts import FACILITATOR_MECHANICS
from .workflows import WORKFLOW_TYPES, UnknownWorkflowType, get_workflow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkflowOverrides:
    """The admin's edits to a workflow type's prompt fragments.

    Each field is the literal override text — empty string means "use
    the code-defined default." We don't try to encode the default
    value into the file; that lives in WORKFLOW_TYPES.
    """

    type: str
    task_framing: str = ""
    output_template: str = ""
    mechanics_override: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "task_framing": self.task_framing,
            "output_template": self.output_template,
            "mechanics_override": self.mechanics_override,
        }

    @classmethod
    def empty(cls, workflow_type: str) -> "WorkflowOverrides":
        return cls(type=workflow_type)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WorkflowOverrides":
        return cls(
            type=str(raw.get("type", "")),
            task_framing=str(raw.get("task_framing", "") or ""),
            output_template=str(raw.get("output_template", "") or ""),
            mechanics_override=str(raw.get("mechanics_override", "") or ""),
        )


# ---------------------------------------------------------------------------
# Persistence — same atomic-write tmpfile-then-rename pattern as sessions.


def overrides_path(workflows_dir: Path, workflow_type: str) -> Path:
    return workflows_dir / f"{workflow_type}.json"


def load_overrides(
    workflow_type: str, workflows_dir: Path
) -> WorkflowOverrides:
    """Read overrides for `workflow_type`. Returns an empty record if no file."""
    if workflow_type not in WORKFLOW_TYPES:
        raise UnknownWorkflowType(workflow_type)
    path = overrides_path(workflows_dir, workflow_type)
    if not path.exists():
        return WorkflowOverrides.empty(workflow_type)
    try:
        with path.open("r", encoding="utf-8") as h:
            raw = json.load(h)
    except json.JSONDecodeError as exc:
        logger.warning(
            "workflow overrides %s couldn't be parsed (%s); ignoring",
            path,
            exc,
        )
        return WorkflowOverrides.empty(workflow_type)
    # Force the type field to match the filename — the file is the source
    # of truth for which workflow these overrides belong to.
    return WorkflowOverrides.from_dict({**raw, "type": workflow_type})


def save_overrides(
    overrides: WorkflowOverrides, workflows_dir: Path
) -> Path:
    if overrides.type not in WORKFLOW_TYPES:
        raise UnknownWorkflowType(overrides.type)
    workflows_dir.mkdir(parents=True, exist_ok=True)
    final_path = overrides_path(workflows_dir, overrides.type)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{overrides.type}.",
        suffix=".json.tmp",
        dir=workflows_dir,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(overrides.to_dict(), h, ensure_ascii=False, indent=2)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp_name, final_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return final_path


def list_overrides(workflows_dir: Path) -> dict[str, WorkflowOverrides]:
    """Read overrides for every known workflow type. Always returns one
    entry per WORKFLOW_TYPES key (empty record if no file on disk)."""
    out: dict[str, WorkflowOverrides] = {}
    for wf_type in WORKFLOW_TYPES:
        out[wf_type] = load_overrides(wf_type, workflows_dir)
    return out


# ---------------------------------------------------------------------------
# Resolver — what the runtime calls to get the effective value.


def get_task_framing(workflow_type: str, workflows_dir: Path) -> str:
    """Override-or-default task framing for the facilitator prompt."""
    overrides = load_overrides(workflow_type, workflows_dir)
    if overrides.task_framing.strip():
        return overrides.task_framing
    return get_workflow(workflow_type).default_task_framing


def get_output_template(workflow_type: str, workflows_dir: Path) -> str:
    """Override-or-default output (synthesis/proposal/revise) template."""
    overrides = load_overrides(workflow_type, workflows_dir)
    if overrides.output_template.strip():
        return overrides.output_template
    return get_workflow(workflow_type).default_output_template


def get_mechanics(workflow_type: str, workflows_dir: Path) -> str:
    """Override-or-system-default facilitator mechanics."""
    overrides = load_overrides(workflow_type, workflows_dir)
    if overrides.mechanics_override.strip():
        return overrides.mechanics_override
    return FACILITATOR_MECHANICS


__all__ = [
    "WorkflowOverrides",
    "get_mechanics",
    "get_output_template",
    "get_task_framing",
    "list_overrides",
    "load_overrides",
    "overrides_path",
    "save_overrides",
]
