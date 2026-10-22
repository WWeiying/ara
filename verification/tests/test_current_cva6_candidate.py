import tempfile
import unittest
from pathlib import Path

from fpga.derive_current_cva6_candidate import cva6_differences


class CurrentCva6CandidateTests(unittest.TestCase):
    def test_only_stvec_difference_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package/rtl/cva6"
            source = root / "source"
            for name in ("core/csr_regfile.sv", "core/load_unit.sv"):
                for parent in (package, source):
                    path = parent / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"common")
            (source / "core/csr_regfile.sv").write_bytes(b"current STVEC")
            changed = cva6_differences(root / "package", source)
            self.assertEqual(set(changed), {"core/csr_regfile.sv"})
            (source / "core/load_unit.sv").write_bytes(b"unexpected")
            with self.assertRaisesRegex(ValueError, "unreviewed CVA6 differences"):
                cva6_differences(root / "package", source)


if __name__ == "__main__":
    unittest.main()
