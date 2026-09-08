import tempfile
import unittest
from pathlib import Path

from run_d256_efficiency import collect


class CollectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "decode_attention_core_akv_v2_kv17_20260907_000000"
        self.run.mkdir()
        (self.run / "complete").touch()
        self.text = (
            "ATTENTION_DISPATCH native_v2=1 groups=1\n"
            "[AKV_PERF] command=6 success=1 fault=0 v2_column_load=1\n"
            "LLAMA_OPERATOR operator/decode/attention_core/akv_v2 PASS cycles=100 mismatches=0\n"
            "Core Test *** SUCCESS\n"
        )
        (self.run / "ara.log").write_text(self.text)
        (self.run / "llm_perf_report_test.log").write_text(
            "[LLM_PERF] case=test phase=total cycles=137\n")

    def test_collect_exact_run(self):
        rows = collect(self.root, "akv_v2", 17)
        self.assertEqual(rows[0]["kernel_cycles"], "100")
        self.assertEqual(rows[0]["akv_command_count"], 1)

    def test_missing_complete_rejected(self):
        (self.run / "complete").unlink()
        with self.assertRaises(RuntimeError):
            collect(self.root, "akv_v2", 17)

    def test_hidden_fallback_rejected(self):
        (self.run / "ara.log").write_text(self.text.replace("native_v2=1", "native_v2=0"))
        with self.assertRaises(RuntimeError):
            collect(self.root, "akv_v2", 17)

    def test_command_fault_rejected(self):
        (self.run / "ara.log").write_text(self.text.replace("fault=0", "fault=1"))
        with self.assertRaises(RuntimeError):
            collect(self.root, "akv_v2", 17)

    def test_missing_native_counters_rejected(self):
        (self.run / "ara.log").write_text("\n".join(
            line for line in self.text.splitlines()
            if not line.startswith("[AKV_PERF]")))
        with self.assertRaises(RuntimeError):
            collect(self.root, "akv_v2", 17)

    def test_mismatch_rejected(self):
        (self.run / "ara.log").write_text(self.text.replace("mismatches=0", "mismatches=1"))
        with self.assertRaises(RuntimeError):
            collect(self.root, "akv_v2", 17)


if __name__ == "__main__":
    unittest.main()
