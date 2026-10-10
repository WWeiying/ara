"""Unit checks for cross-layer QBS real-DUT evidence auditing."""

import unittest
import hashlib
import tempfile
from pathlib import Path

from check_real_dut_evidence import audit_records, verify_manifest


class RealDutEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.case = {"case_id": "q3k_decode_attn_q_qbs", "k": 1536,
                     "rows": 256, "inputs": 1}
        self.log = [
            "QBS_REAL_BENCH case=q3k_decode_attn_q_qbs result=PASS "
            "k=1536 rows=256 inputs=1 outputs=256 result_count=256 "
            "tiles=1 operations=1 mismatches=0 qbs_status=0"
        ]
        self.trace = [
            "10,alloc,7,0,0,0,00b5045b",
            "20,write,7,0,0,4,00b5045b",
            "30,done,7,0,0,0,00b5045b",
        ]
        self.uvm = {"status": "PASS", "issues": []}

    def test_matching_layers_pass(self) -> None:
        self.assertEqual(audit_records(self.case, self.log, self.trace,
                                       self.uvm)["status"], "PASS")

    def test_four_input_command_uses_m4_encoding(self) -> None:
        self.case["inputs"] = 4
        self.log = [self.log[0].replace("inputs=1", "inputs=4")
                    .replace("outputs=256", "outputs=1024")
                    .replace("result_count=256", "result_count=1024")]
        self.trace = [line.replace("00b5045b", "06b5045b") for line in self.trace]
        self.assertEqual(audit_records(self.case, self.log, self.trace,
                                       self.uvm)["status"], "PASS")
        self.trace[0] = self.trace[0].replace("06b5045b", "00b5045b")
        self.assertEqual(audit_records(self.case, self.log, self.trace,
                                       self.uvm)["status"], "FAIL")

    def test_missing_qbs_completion_fails(self) -> None:
        self.assertEqual(audit_records(self.case, self.log, self.trace[:-1],
                                       self.uvm)["status"], "FAIL")

    def test_missing_benchmark_fails(self) -> None:
        self.assertEqual(audit_records(self.case, [], self.trace,
                                       self.uvm)["status"], "FAIL")

    def test_uvm_failure_fails(self) -> None:
        self.uvm["status"] = "FAIL"
        self.assertEqual(audit_records(self.case, self.log, self.trace,
                                       self.uvm)["status"], "FAIL")

    def test_manifest_requires_named_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.elf").write_bytes(b"elf")
            digest = hashlib.sha256(b"elf").hexdigest()
            manifest = root / "SHA256SUMS"
            manifest.write_text(f"{digest}  input.elf\n", encoding="utf-8")
            self.assertEqual(verify_manifest(manifest, root, {"input.elf"}), [])
            self.assertIn("missing SHA-256 manifest entry: trace.csv",
                          verify_manifest(manifest, root,
                                          {"input.elf", "trace.csv"}))

    def test_manifest_archived_source_requires_exact_recorded_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "runner.sh"
            archived = root / "runner-old.sh"
            manifest = root / "SHA256SUMS"
            current.write_bytes(b"new runner")
            archived.write_bytes(b"old runner")
            source_map = {str(current): archived}
            old_hash = hashlib.sha256(archived.read_bytes()).hexdigest()
            manifest.write_text(f"{old_hash}  {current}\n", encoding="utf-8")
            self.assertEqual(verify_manifest(manifest, root, set(), source_map), [])
            archived.write_bytes(b"altered archive")
            self.assertTrue(verify_manifest(manifest, root, set(), source_map))
            new_hash = hashlib.sha256(current.read_bytes()).hexdigest()
            manifest.write_text(f"{new_hash}  {current}\n", encoding="utf-8")
            self.assertEqual(verify_manifest(manifest, root, set(), source_map), [])

    def test_manifest_can_select_one_of_multiple_archived_runners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "runner.sh"
            old_a = root / "runner-a.sh"
            old_b = root / "runner-b.sh"
            manifest = root / "SHA256SUMS"
            current.write_bytes(b"new")
            old_a.write_bytes(b"unrelated")
            old_b.write_bytes(b"recorded")
            recorded_hash = hashlib.sha256(old_b.read_bytes()).hexdigest()
            manifest.write_text(f"{recorded_hash}  {current}\n", encoding="utf-8")
            self.assertEqual(verify_manifest(manifest, root, set(),
                                             {str(current): [old_a, old_b]}), [])
            old_b.write_bytes(b"changed")
            self.assertTrue(verify_manifest(manifest, root, set(),
                                            {str(current): [old_a, old_b]}))


if __name__ == "__main__":
    unittest.main()
