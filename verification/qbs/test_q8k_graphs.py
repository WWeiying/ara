import unittest

from build_q8k_graphs import graph_production
from check_q8k_graphs import check_output, tile
from test_ggml_tile_context import fixture


def evidence():
    result = []
    for prepare in (0, 1):
        result.append(f"Q8K_GRAPH_GROUP_BEGIN prepare={prepare}")
        run = 0
        for line in fixture().splitlines():
            result.append(line)
            if line.startswith("QBS_TILE_RUN_BEGIN "):
                run = int(line.split()[1].split("=")[1])
            elif line.startswith("QBS_TILE_GRAPH_BEGIN "):
                case = int(line.split()[1].split("=")[1])
                shape = tile.SHAPES[case]
                if not tile._wide_selected(shape, tile.RUNS[run][1]):
                    tag = "Q8K_M4" if shape.kind == "q4_K" else "M4"
                    result.extend([f"GGML_RISCV_QBS_{tag}_PREPARE enabled={prepare} "
                                   f"path={'rvv' if prepare else 'generic'} "
                                   f"k={shape.blocks * shape.elements}"] * (shape.m // 4))
        result.append(f"Q8K_GRAPH_GROUP_END prepare={prepare} exit=0")
    result.append("Q8K_GRAPH_GUEST_EXIT=0")
    return "\n".join(result)


class GraphGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = evidence()

    def test_complete(self):
        report = check_output(self.good)
        self.assertEqual(report["graphs"], 384)
        self.assertEqual(report["q8k_calls_per_mode"], 52)

    def test_bad_missing_duplicate_selection(self):
        marker = "GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=1 path=rvv k=512"
        for replacement in ("", marker + "\n" + marker,
                            marker.replace("rvv", "generic"), marker.replace("512", "256"),
                            marker + " extra=1"):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                check_output(self.good.replace(marker, replacement, 1))

    def test_graph_fallback_and_truncation(self):
        for bad in (self.good.replace("emulated=0", "emulated=1", 1),
                    self.good.replace("outputs=37 ", "outputs=36 ", 1),
                    self.good.rsplit("Q8K_GRAPH_GROUP_END", 1)[0],
                    self.good + "\nQ8K_GRAPH_GUEST_EXIT=0"):
            with self.assertRaises(ValueError):
                check_output(bad)

    def test_observer_is_thread_local(self):
        text = ("static bool q8k_production_vector_path;\n"
                "        ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, n_per_row);\n"
                "    }\n}\n\ntemplate <int M, int N>")
        new = graph_production(text)
        self.assertIn("static thread_local bool q8k_production_vector_path;", new)
        self.assertIn("GGML_RISCV_QBS_Q8K_M4_PREPARE", new)
        with self.assertRaises(ValueError):
            graph_production("unrecognized production source")


if __name__ == "__main__":
    unittest.main()
