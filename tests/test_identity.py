"""Tests for the storage index and the identity claim helpers.

The web `/join` endpoint depends on three invariants:
  1. New participants get a fresh UUID; their name is reserved in the index.
  2. A name that's already in the index (case + whitespace insensitive)
     can't be claimed by a different participant.
  3. The same participant can re-confirm their own name without conflict
     (so reconnect-after-restart paths don't false-positive).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from circle.controller.identity import (  # noqa: E402
    InvalidNameError,
    NameTakenError,
    claim_name,
    is_name_taken,
    normalize_name,
    validate_display_name,
)
from circle.storage import (  # noqa: E402
    list_participant_files,
    read_index,
    register_in_index,
)


class NormalizationTests(unittest.TestCase):
    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_name("Anton"), normalize_name("anton"))
        self.assertEqual(normalize_name("ANTON"), normalize_name("Anton"))

    def test_whitespace_collapse(self) -> None:
        self.assertEqual(normalize_name("  Anton   K. "), "anton k.")

    def test_validate_rejects_empty(self) -> None:
        with self.assertRaises(InvalidNameError):
            validate_display_name("")
        with self.assertRaises(InvalidNameError):
            validate_display_name("   ")

    def test_validate_rejects_nonstring(self) -> None:
        with self.assertRaises(InvalidNameError):
            validate_display_name(None)  # type: ignore[arg-type]

    def test_validate_rejects_overlong(self) -> None:
        with self.assertRaises(InvalidNameError):
            validate_display_name("a" * 100)

    def test_validate_rejects_control_chars(self) -> None:
        with self.assertRaises(InvalidNameError):
            validate_display_name("Anton\x00")

    def test_validate_trims_and_collapses(self) -> None:
        self.assertEqual(validate_display_name("  Anton   K. "), "Anton K.")


class IndexAndClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "session_x"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_index_when_no_one_joined(self) -> None:
        self.assertEqual(read_index(self.data_dir), {})
        self.assertFalse(is_name_taken(self.data_dir, "Anton"))

    def test_register_and_read_back(self) -> None:
        register_in_index(self.data_dir, "uuid-abc", "Anton")
        self.assertEqual(read_index(self.data_dir), {"uuid-abc": "Anton"})

    def test_register_idempotent(self) -> None:
        register_in_index(self.data_dir, "uuid-abc", "Anton")
        register_in_index(self.data_dir, "uuid-abc", "Anton")
        self.assertEqual(read_index(self.data_dir), {"uuid-abc": "Anton"})

    def test_register_can_update_name(self) -> None:
        register_in_index(self.data_dir, "uuid-abc", "Anton")
        register_in_index(self.data_dir, "uuid-abc", "Anton K.")
        self.assertEqual(read_index(self.data_dir), {"uuid-abc": "Anton K."})

    def test_is_name_taken_case_insensitive(self) -> None:
        register_in_index(self.data_dir, "uuid-abc", "Anton")
        self.assertTrue(is_name_taken(self.data_dir, "anton"))
        self.assertTrue(is_name_taken(self.data_dir, "  ANTON "))
        self.assertFalse(is_name_taken(self.data_dir, "Bob"))

    def test_is_name_taken_excludes_self(self) -> None:
        register_in_index(self.data_dir, "uuid-abc", "Anton")
        # Same participant re-confirming their own name is not a dupe.
        self.assertFalse(
            is_name_taken(self.data_dir, "Anton", except_participant_id="uuid-abc")
        )
        # A different participant attempting the same name IS a dupe.
        self.assertTrue(
            is_name_taken(self.data_dir, "Anton", except_participant_id="uuid-other")
        )

    def test_claim_name_allocates_uuid_when_free(self) -> None:
        pid, display = claim_name(self.data_dir, "  Anton K.  ")
        self.assertTrue(pid)
        self.assertEqual(display, "Anton K.")

    def test_claim_name_fresh_uuids_each_call(self) -> None:
        pid_a, _ = claim_name(self.data_dir, "Bob")
        pid_b, _ = claim_name(self.data_dir, "Carolina")
        self.assertNotEqual(pid_a, pid_b)

    def test_claim_name_rejects_dupe_after_index_register(self) -> None:
        register_in_index(self.data_dir, "uuid-abc", "Anton")
        with self.assertRaises(NameTakenError):
            claim_name(self.data_dir, "anton")
        with self.assertRaises(NameTakenError):
            claim_name(self.data_dir, "  Anton  ")

    def test_claim_name_validates_first(self) -> None:
        with self.assertRaises(InvalidNameError):
            claim_name(self.data_dir, "")


class ParticipantListingTests(unittest.TestCase):
    """`list_participant_files` must skip the index file and any tmp/dot files."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "session_x"
        self.data_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_skips_index_and_dot_files(self) -> None:
        (self.data_dir / "_index.json").write_text("{}")
        (self.data_dir / ".tmp.json").write_text("{}")
        (self.data_dir / "abc.json").write_text("{}")
        (self.data_dir / "def.json").write_text("{}")
        files = list_participant_files(self.data_dir)
        names = sorted(p.name for p in files)
        self.assertEqual(names, ["abc.json", "def.json"])


if __name__ == "__main__":
    unittest.main()
