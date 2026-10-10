import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "consolidate_local_inputs", Path(__file__).resolve().parents[1] /
    "consolidate_local_inputs.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConsolidationInputsTests(unittest.TestCase):
    def test_hash_inventory_follows_nested_directory_links(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "source").mkdir()
            (base / "payload").mkdir()
            (base / "payload/test").write_bytes(b"input")
            (base / "source/nested").symlink_to(base / "payload", target_is_directory=True)
            result = MODULE.tree_hashes(base / "source")
            self.assertEqual(result, {"nested/test": MODULE.digest(base / "payload/test")})

    def test_relocated_venv_does_not_keep_creator_worktree_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "ara_dsa_signoff_integration"
            for name in ("plic-venv", "soc-venv"):
                folder = root / "verification/tools" / name / "bin"
                folder.mkdir(parents=True)
                old = base / "ara_dsa_verification/verification/tools" / name
                (folder / "pip").write_text(f"#!{old}/bin/python\n")
                (folder / "python").write_bytes(b"\x7fELF\xff")
            with patch.object(MODULE.subprocess, "run"):
                changed = MODULE.relocate_venvs(root)
                self.assertEqual(len(changed), 2)
                self.assertEqual(MODULE.relocate_venvs(root), [])
            for name in ("plic-venv", "soc-venv"):
                prefix = root / "verification/tools" / name
                self.assertEqual((prefix / "bin/pip").read_text(), f"#!{prefix}/bin/python\n")
                self.assertEqual((prefix / "bin/python").read_bytes(), b"\x7fELF\xff")


if __name__ == "__main__":
    unittest.main()
