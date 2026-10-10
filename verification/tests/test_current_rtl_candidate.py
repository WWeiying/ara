import tempfile
import unittest
from pathlib import Path

from fpga.derive_current_rtl_candidate import (
    EXPECTED_DIFFERENCES, audit_rtl_tree, check_base_source_record,
)
from fpga.prepare_soc_candidate import PRESERVE


class CurrentRtlCandidateTests(unittest.TestCase):
    def test_base_source_record_requires_exact_preserved_file(self):
        target = "rtl/ara/hardware/src/lane/vmfpu.sv"
        record = {"old_sha256": PRESERVE[target], "new_sha256": "new"}
        check_base_source_record(target, record, "original")
        self.assertEqual(record["pre_integration_source_sha256"], "original")

        normal = {"old_sha256": "old", "new_sha256": "new"}
        check_base_source_record(target, normal, "old")
        self.assertNotIn("pre_integration_source_sha256", normal)
        with self.assertRaisesRegex(ValueError, "base source manifest differs"):
            check_base_source_record(target, normal, "unrelated")
        with self.assertRaisesRegex(ValueError, "base source manifest differs"):
            check_base_source_record("rtl/ara/hardware/src/ara_sequencer.sv",
                                     record.copy(), "unrelated")

    def test_only_reviewed_rtl_differences_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen = root / "package"
            current = root / "current"
            for name in EXPECTED_DIFFERENCES | {"lane/alu.sv"}:
                for parent, content in ((frozen, b"old"), (current, b"new")):
                    path = parent / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content if name in EXPECTED_DIFFERENCES else b"same")
            for name in ("accel_dispatcher_ideal.sv", "ara_soc.sv", "ara_system.sv"):
                (current / name).write_bytes(b"host only")
            changed = audit_rtl_tree(frozen, current)
            self.assertEqual(set(changed), EXPECTED_DIFFERENCES)
            with self.assertRaisesRegex(ValueError, "unreviewed Ara RTL changes"):
                audit_rtl_tree(frozen, current, frozenset({"vlsu/vstu.sv"}))
            for name in EXPECTED_DIFFERENCES - {"sldu/sldu.sv"}:
                (current / name).write_bytes(b"old")
            self.assertEqual(set(audit_rtl_tree(frozen, current,
                                                 frozenset({"sldu/sldu.sv"}))),
                             {"sldu/sldu.sv"})
            (current / "lane/alu.sv").write_bytes(b"unexpected")
            with self.assertRaisesRegex(ValueError, "unreviewed Ara RTL changes"):
                audit_rtl_tree(frozen, current)
            (current / "lane/alu.sv").write_bytes(b"same")
            (current / "lane/new.sv").write_bytes(b"new")
            with self.assertRaisesRegex(ValueError, "file inventory differs"):
                audit_rtl_tree(frozen, current)


if __name__ == "__main__":
    unittest.main()
