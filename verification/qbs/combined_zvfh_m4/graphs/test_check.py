"""Host protocol tests; synthetic fixtures are not graph execution evidence."""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_ggml_tile_context import fixture
from check import check_output, tile


def evidence(reverse_parallel=False):
    lines = []
    for prepare in (0, 1):
        lines.append(f"Q8K_GRAPH_GROUP_BEGIN prepare={prepare}")
        run = None
        for line in fixture(reverse_parallel=reverse_parallel).splitlines():
            lines.append(line)
            if line.startswith("QBS_TILE_RUN_BEGIN "):
                run = int(line.split()[1].split("=")[1])
            elif line.startswith("QBS_TILE_GRAPH_BEGIN "):
                case = int(line.split()[1].split("=")[1])
                shape = tile.SHAPES[case]
                if shape.kind == "q4_K" and not tile._wide_selected(shape, tile.RUNS[run][1]):
                    lines.extend([f"GGML_RISCV_QBS_Q8K_M4_PREPARE enabled={prepare} "
                                  f"path={'rvv' if prepare else 'generic'} "
                                  f"k={shape.blocks * shape.elements}"] * (shape.m // 4))
        lines.append(f"Q8K_GRAPH_GROUP_END prepare={prepare} exit=0")
    lines.append("Q8K_GRAPH_GUEST_EXIT=0")
    return "\n".join(lines)


class CombinedGraphCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = evidence()

    def reject(self, text):
        with self.assertRaises(ValueError):
            check_output(text)

    def test_complete(self):
        result = check_output(self.good)
        self.assertEqual(result["graphs"], 384)
        self.assertEqual(result["q8k_calls_per_mode"], 52)
        self.assertEqual(result["q8_0_graphs"], 264)
        self.assertEqual([r["context_eligible_graphs"] for r in result["groups"][0]["runs"]],
                         [0, 26, 0, 20, 0, 0])

    def test_parallel_command_order(self):
        self.assertEqual(check_output(evidence(True))["state"], "PASS")

    def test_bad_q8k_selection(self):
        marker = "GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=1 path=rvv k=512"
        for replacement in ("", marker + "\n" + marker, marker.replace("rvv", "generic"),
                            marker.replace("enabled=1", "enabled=0"), marker.replace("512", "256"),
                            marker + " extra=1", "bad-prefix " + marker):
            with self.subTest(replacement=replacement):
                self.reject(self.good.replace(marker, replacement, 1))

    def test_q8_0_optin_trace_forbidden(self):
        marker = "GGML_RISCV_QBS_M4_PREPARE enabled=1 path=rvv k=896"
        self.reject(self.good.replace("QBS_TILE_GRAPH_PASS outputs=148 ",
                                      marker + "\nQBS_TILE_GRAPH_PASS outputs=148 ", 1))

    def test_trace_in_wrong_graph_or_outside_group(self):
        marker = "GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=0 path=generic k=512"
        self.reject(self.good + "\n" + marker)
        # Preserve total call count while moving one trace to a Q8_0 graph.
        bad = self.good.replace(marker + "\n", "", 1)
        bad = bad.replace("QBS_TILE_GRAPH_PASS outputs=37 ",
                          marker + "\nQBS_TILE_GRAPH_PASS outputs=37 ", 1)
        self.reject(bad)

    def test_pair_output_and_activation_digests(self):
        off, on = self.good.split("Q8K_GRAPH_GROUP_BEGIN prepare=1", 1)
        for prefix in ("QBS_TILE_GRAPH_PASS", "GGML_RISCV_QBS_LIFETIME "):
            changed = re.sub(r"(^" + prefix + r"[^\n]*?digest=)[0-9a-f]{16}",
                             lambda m: m[1] + "f" + m[0][-15:], on, flags=re.M)
            self.assertNotEqual(changed, on)
            self.reject(off + "Q8K_GRAPH_GROUP_BEGIN prepare=1" + changed)

    def test_q8_0_coverage_and_numerics_required(self):
        for old, new in (("case=0 type=q8_0", "case=0 type=q4_K"),
                         ("outputs=37 ", "outputs=36 "), ("max_error=1e-7", "max_error=nan"),
                         ("QBS_TILE_GRAPH_SUITE_PASS cases=32", "QBS_TILE_GRAPH_SUITE_PASS cases=31")):
            with self.subTest(old=old):
                self.reject(self.good.replace(old, new, 1))

    def test_work_lifetime_and_summary_mutations(self):
        for old, new in (("emulated=0", "emulated=1"), ("segmented=0", "segmented=1"),
                         ("access=3", "access=2"), ("activation_seq=1", "activation_seq=2"),
                         ("weight_profile=6", "weight_profile=1"),
                         ("cross_op_fill=0", "cross_op_fill=1"),
                         ("graph_epochs=32", "graph_epochs=31")):
            with self.subTest(old=old):
                self.reject(self.good.replace(old, new, 1))

    def test_truncation_exit_and_failure(self):
        for text in (self.good.rsplit("Q8K_GRAPH_GROUP_END", 1)[0],
                     self.good.replace("GROUP_END prepare=1 exit=0", "GROUP_END prepare=1 exit=1"),
                     self.good + "\nQ8K_GRAPH_GUEST_EXIT=0", self.good + "\nKernel panic",
                     self.good.replace("QBS_TILE_RUN_BEGIN run=0 ",
                                       "Q8K_GRAPH_UNKNOWN\nQBS_TILE_RUN_BEGIN run=0 ", 1),
                     self.good.replace("QBS_TILE_RUN_END run=5 exit=0", "", 1)):
            self.reject(text)


if __name__ == "__main__":
    unittest.main()
