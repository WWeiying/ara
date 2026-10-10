"""Checks for the independent RVV/AKV-v2 Attention evidence parser."""

import tempfile
import unittest
from pathlib import Path

from compare_akv_real_dut_pair import (assembly_inputs, custom_allocations,
                                       operator_record)


class AkvPairEvidenceTests(unittest.TestCase):
    def test_assembly_config_and_tensor_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.S"
            path.write_text(
                ".global llama_case_config\nllama_case_config:\n"
                ".long 1363889487\n.long 1\n.long 7\n.long 8\n"
                ".balign 8\n.incbin \"/capture/q.bin\"\n",
                encoding="utf-8")
            self.assertEqual(assembly_inputs(path),
                             ([1363889487, 1, 7, 8], [Path("/capture/q.bin")]))

    def test_operator_requires_native_akv_and_golden_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(
                "ATTENTION_DISPATCH native_v2=1 portable=0\n"
                "LLAMA_OPERATOR operator/decode/attention_core/akv_v2 "
                "PASS cycles=35912 mismatches=0\n", encoding="utf-8")
            issues = []
            self.assertEqual(operator_record(path, "akv_v2", issues), 35912)
            self.assertEqual(issues, [])
            path.write_text(
                "ATTENTION_DISPATCH native_v2=0 portable=0\n"
                "LLAMA_OPERATOR operator/decode/attention_core/akv_v2 "
                "PASS cycles=35912 mismatches=0\n", encoding="utf-8")
            issues = []
            self.assertEqual(operator_record(path, "akv_v2", issues), 35912)
            self.assertTrue(issues)

    def test_trace_separates_akv_from_other_custom2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            path.write_text(
                "cycle,event,seq,vid,lane,source,insn\n"
                "1,alloc,1,0,0,0,00b5605b\n"
                "2,alloc,2,0,0,0,0005745b\n"
                "3,alloc,3,0,0,0,00b5045b\n"
                "4,alloc,4,0,0,0,0205375b\n"
                "5,alloc,5,0,0,0,0000505b\n"
                "4,write,2,0,0,0,0005745b\n", encoding="utf-8")
            self.assertEqual(custom_allocations(path), {
                "fill_v2": 1, "column_v2": 1, "value_load": 1,
                "release": 1, "other_custom2": 1})


if __name__ == "__main__":
    unittest.main()
