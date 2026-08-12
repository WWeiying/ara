import json
import tempfile
import unittest
from pathlib import Path

from ara_verify.stimulus_coverage import (
    analyze_stimulus,
    merge_stimulus_coverage,
    write_stimulus_coverage,
)


class StimulusCoverageTests(unittest.TestCase):
    def test_reports_instructions_in_main_and_generated_subroutines(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.S"
            source.write_text(
                "vadd.vv v1, v2, v3\n"
                "vsetvli x1, x2, e64, m8, ta, ma\n"
                "main:\n"
                "  vsetvli x1, x2, e32, m4, ta, mu\n"
                "  vmand.mm v3, v1, v2\n"
                "  vle32.v v4, (x10)\n"
                "  vlse16.v v6, (x11), x12\n"
                "  vsuxei32.v v4, (x13), v8, v0.t\n"
                "test_done:\n"
                "  vmxor.mm v1, v2, v3\n"
                "  vsetivli x1, 4, e16, mf2, ta, ma\n"
                "sub_1:\n"
                "  vsub.vv v7, v8, v9\n"
                ".section .data\n"
                "  vadd.vv v10, v11, v12\n",
                encoding="utf-8",
            )

            report = analyze_stimulus(source)

            self.assertEqual(report["vector_instruction_count"], 6)
            self.assertEqual(report["configuration_instruction_count"], 1)
            self.assertEqual(report["masked_instruction_count"], 1)
            self.assertEqual(report["families"]["mask_logical"], 1)
            self.assertEqual(report["memory_modes"], {
                "indexed": 1, "strided": 1, "unit_stride": 1,
            })
            self.assertEqual(report["sew"], {"e32": 1})
            self.assertEqual(report["lmul"], {"m4": 1})
            self.assertNotIn("vmxor.mm", report["mnemonics"])
            self.assertEqual(report["mnemonics"]["vsub.vv"], 1)
            self.assertEqual(report["mnemonics"].get("vadd.vv", 0), 0)

    def test_writes_aggregate_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            assembly = output / "asm_test"
            assembly.mkdir()
            for index in range(2):
                (assembly / f"profile_{index}.S").write_text(
                    "main:\n  vsetivli x1, 4, e8, m1, tu, mu\n"
                    "  vasubu.vv v3, v1, v2\ntest_done:\n",
                    encoding="utf-8",
                )

            path = write_stimulus_coverage(output, "profile")
            report = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(report["source_count"], 2)
            self.assertEqual(report["vector_instruction_count"], 4)
            self.assertEqual(report["aggregate"]["families"]["fixed_point"], 2)
            self.assertEqual(report["aggregate"]["mnemonics"]["vasubu.vv"], 2)

    def test_merges_profile_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for index, mnemonic in enumerate(("vadd.vv", "vsub.vv")):
                output = root / f"profile_{index}"
                assembly = output / "asm_test"
                assembly.mkdir(parents=True)
                (assembly / f"profile_{index}_0.S").write_text(
                    "main:\n"
                    "  vsetvli t0, a0, e32, m1, tu, mu\n"
                    f"  {mnemonic} v1, v2, v3\n"
                    "test_done:\n",
                    encoding="utf-8",
                )
                paths.append(write_stimulus_coverage(output, f"profile_{index}"))

            merged = merge_stimulus_coverage(paths)

            self.assertEqual(merged["profile_count"], 2)
            self.assertEqual(merged["source_count"], 2)
            self.assertEqual(merged["vector_instruction_count"], 4)
            self.assertEqual(merged["aggregate"]["mnemonics"]["vadd.vv"], 1)
            self.assertEqual(merged["aggregate"]["mnemonics"]["vsub.vv"], 1)
