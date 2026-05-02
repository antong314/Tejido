"""Tests for the session JSON loader/saver.

The on-disk session format is an admin-managed file under config/sessions/;
this module covers the round-trip and the error paths the admin UI will
hit when sessions are malformed or missing.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from circle.session import (  # noqa: E402
    CommonSettings,
    Session,
    SessionFileError,
    delete_session,
    list_session_ids,
    load_session,
    load_session_from_path,
    new_session,
    save_session,
    session_path,
)


class SessionFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _make(self, sid: str = "smoke") -> Session:
        return new_session(
            id=sid,
            title=sid.replace("_", " ").title(),
            workflow_type="open_discussion",
            common=CommonSettings(),
            workflow_data={"question": "What is the question?"},
        )

    def test_save_then_load_round_trip(self) -> None:
        s = self._make()
        save_session(s, self.dir)
        loaded = load_session("smoke", self.dir)
        self.assertEqual(loaded.to_dict(), s.to_dict())

    def test_save_creates_directory_if_missing(self) -> None:
        nested = self.dir / "nested" / "sessions"
        s = self._make()
        save_session(s, nested)
        self.assertTrue((nested / "smoke.json").exists())

    def test_load_missing_raises(self) -> None:
        with self.assertRaises(SessionFileError):
            load_session("does_not_exist", self.dir)

    def test_load_malformed_json_raises(self) -> None:
        path = session_path(self.dir, "broken")
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        with self.assertRaises(SessionFileError):
            load_session_from_path(path)

    def test_list_session_ids_returns_sorted(self) -> None:
        for sid in ("zebra", "alpha", "mango"):
            save_session(self._make(sid), self.dir)
        self.assertEqual(list_session_ids(self.dir), ["alpha", "mango", "zebra"])

    def test_list_session_ids_skips_hidden_and_underscore(self) -> None:
        save_session(self._make("real"), self.dir)
        (self.dir / "_index.json").write_text("{}")
        (self.dir / ".tmp.json").write_text("{}")
        self.assertEqual(list_session_ids(self.dir), ["real"])

    def test_list_session_ids_empty_when_dir_missing(self) -> None:
        self.assertEqual(list_session_ids(self.dir / "nope"), [])

    def test_delete_session(self) -> None:
        save_session(self._make(), self.dir)
        self.assertTrue(delete_session("smoke", self.dir))
        self.assertFalse((self.dir / "smoke.json").exists())
        self.assertFalse(delete_session("smoke", self.dir))

    def test_atomic_write_no_tmp_left_on_success(self) -> None:
        save_session(self._make(), self.dir)
        leftover = list(self.dir.glob("*.json.tmp"))
        self.assertEqual(leftover, [])

    def test_load_rejects_unknown_workflow_in_file(self) -> None:
        path = session_path(self.dir, "bogus")
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "id": "bogus",
                    "title": "Bogus",
                    "workflow_type": "not_a_real_workflow",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "common": {},
                    "whisper": {},
                    "workflow_data": {},
                }
            )
        )
        # Construction raises (UnknownWorkflowType is a ValueError subclass).
        with self.assertRaises(Exception):
            load_session_from_path(path)


if __name__ == "__main__":
    unittest.main()
