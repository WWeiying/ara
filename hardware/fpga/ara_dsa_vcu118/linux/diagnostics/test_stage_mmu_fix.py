import tempfile
import unittest
from pathlib import Path
from stage_mmu_fix import MMU, digest, stage


class StageTest(unittest.TestCase):
    def test_only_mmu_changes_and_source_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source"
            (src / MMU).parent.mkdir(parents=True)
            (src / MMU).write_bytes(b"old")
            (src / "other").write_bytes(b"unchanged")
            inventory = f"{digest(b'old')}  {MMU}\n{digest(b'unchanged')}  other\n"
            (src / "SHA256SUMS").write_text(inventory)
            replacement = root / "fix.sv"
            replacement.write_bytes(b"new")
            dst = root / "output"
            stage(src, dst, replacement)
            self.assertEqual((src / MMU).read_bytes(), b"old")
            self.assertEqual((src / "SHA256SUMS").read_text(), inventory)
            self.assertEqual((dst / MMU).read_bytes(), b"new")
            self.assertEqual((dst / "other").read_bytes(), b"unchanged")
            for row in (dst / "SHA256SUMS").read_text().splitlines():
                sha, name = row.split("  ", 1)
                self.assertEqual(digest((dst / name).read_bytes()), sha)
            with self.assertRaises(ValueError):
                stage(src, dst, replacement)
            (src / "other").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                stage(src, root / "bad", replacement)
            self.assertFalse((root / "bad").exists())


if __name__ == "__main__":
    unittest.main()
