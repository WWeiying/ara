import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import admit_gap96_offline_v2 as tool


class ExpectedPinsTests(unittest.TestCase):
    def test_expected_pin_cannot_be_replaced(self):
        pins = {"a": "old"}
        with self.assertRaisesRegex(ValueError, "Expected-pin conflict"):
            tool.merge_expected(pins, {"a": "new"})
        self.assertEqual(pins, {"a": "old"})
        tool.merge_expected(pins, {"a": "old", "b": "new"})
        self.assertEqual(pins, {"a": "old", "b": "new"})

    def test_pinned_file_drift_rejected_before_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "file"
            path.write_bytes(b"before")
            expected = tool.original_sha(path)
            with patch.dict(tool.expected_pins, {str(path): expected}, clear=True):
                self.assertEqual(tool.checked_sha(path), expected)
                path.write_bytes(b"after")
                with self.assertRaisesRegex(ValueError, "Pinned evidence drift"):
                    tool.checked_sha(path)

    def test_shared_helper_is_not_changed(self):
        self.assertEqual(tool.original_sha(tool.shared_source), tool.shared_sha)
        self.assertIn("checked_sha", tool.wrapper.read_text())


if __name__ == "__main__":
    unittest.main()
