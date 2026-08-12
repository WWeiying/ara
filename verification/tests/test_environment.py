import tempfile
import unittest
from pathlib import Path

from ara_verify.environment import bender_lock_revision, config_values


class ConfigTests(unittest.TestCase):
    def test_config_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/default.mk").write_text(
                "nr_lanes ?= 4\nvlen ?= 1024\n", encoding="utf-8"
            )
            self.assertEqual(config_values(root, "default"), {"nr_lanes": 4, "vlen": 1024})

    def test_bender_lock_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "Bender.lock"
            lock.write_text(
                "packages:\n"
                "  cva6:\n"
                "    revision: 0123abcdef\n"
                "    dependencies: []\n"
                "  fpnew:\n"
                "    revision: fedcba3210\n",
                encoding="utf-8",
            )
            self.assertEqual(bender_lock_revision(lock, "cva6"), "0123abcdef")
            self.assertIsNone(bender_lock_revision(lock, "missing"))
