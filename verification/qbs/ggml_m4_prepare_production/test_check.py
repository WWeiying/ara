import unittest

from check import check_native_output, check_output, tile
from test_ggml_tile_context import fixture


def evidence():
    lines = ["M4_PRODUCTION_NATIVE_BEGIN",
             "M4_PRODUCTION_BYTES_PASS checks=3420 vector=594 fallback=2826 bytes=exact fcsr=exact vcsr=exact",
             "M4_PRODUCTION_NATIVE_END exit=0"]
    for prepare in (0, 1):
        lines.append(f"M4_PRODUCTION_GRAPH_BEGIN prepare={prepare}")
        run = 0
        for line in fixture().splitlines():
            lines.append(line)
            if line.startswith("QBS_TILE_RUN_BEGIN "):
                run = int(line.split()[1].split("=")[1])
            if line.startswith("QBS_TILE_GRAPH_BEGIN "):
                case = int(line.split()[1].split("=")[1])
                shape = tile.SHAPES[case]
                if shape.kind == "q8_0" and not tile._wide_selected(shape, tile.RUNS[run][1]):
                    lines.extend([f"GGML_RISCV_QBS_M4_PREPARE enabled={prepare} "
                                  f"path={'rvv' if prepare else 'generic'} k={shape.blocks * 32}"] * (shape.m // 4))
        lines.append(f"M4_PRODUCTION_GRAPH_END prepare={prepare} exit=0")
    lines.append("M4_PRODUCTION_GUEST_EXIT=0")
    return "\n".join(lines)


class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = evidence()

    def reject(self, text):
        with self.assertRaises(ValueError):
            check_output(text)

    def test_accept(self):
        report = check_output(self.good)
        self.assertEqual(report["graphs"], 384)
        self.assertEqual(report["native_checks"], 3420)
        self.assertGreater(report["prepare_calls_per_mode"], 0)

    def test_native_only(self):
        native = self.good.split("M4_PRODUCTION_GRAPH_BEGIN", 1)[0] + "M4_PRODUCTION_NATIVE_GUEST_EXIT=0"
        self.assertEqual(check_native_output(native)["checks"], 3420)
        for bad in (native.replace("594", "593"), native + "\nM4_PRODUCTION_NATIVE_GUEST_EXIT=0",
                    native + "\nGGML_RISCV_QBS_M4_PREPARE enabled=1 path=rvv k=896"):
            with self.assertRaises(ValueError):
                check_native_output(bad)

    def test_preparation_missing_extra_and_fields(self):
        line = "GGML_RISCV_QBS_M4_PREPARE enabled=1 path=rvv k=896"
        for bad in ("", line + "\n" + line, line + " unknown=1", line.replace(" k=896", ""),
                    line.replace("path=rvv", "path=generic"), line.replace("enabled=1", "enabled=0"),
                    line.replace("896", "32"), line + " k=896", line.replace("PREPARE ", "PREPARE_BAD ")):
            with self.subTest(bad=bad):
                self.reject(self.good.replace(line, bad, 1))

    def test_no_trace_is_not_a_pass(self):
        self.reject("\n".join(l for l in self.good.splitlines() if not l.startswith("GGML_RISCV_QBS_M4_PREPARE")))

    def test_wrong_native_counts_and_csr(self):
        for old, new in (("3420", "3419"), ("594", "0"), ("2826", "0"),
                         ("vcsr=exact", "vcsr=unchecked"), ("fcsr=exact", "fcsr=exact extra=1")):
            self.reject(self.good.replace(old, new, 1))

    def test_missing_extra_native_pass(self):
        line = next(l for l in self.good.splitlines() if l.startswith("M4_PRODUCTION_BYTES_PASS"))
        self.reject(self.good.replace(line, "", 1))
        self.reject(self.good.replace(line, line + "\n" + line, 1))

    def test_native_graph_counts_still_checked(self):
        self.reject(self.good.replace("outputs=37 ", "outputs=36 ", 1))
        self.reject(self.good.replace("emulated=0", "emulated=1", 1))
        self.reject(self.good.replace("native_qbexec=72", "native_qbexec=71", 1))

    def test_cross_mode_mismatch(self):
        prefix, suffix = self.good.split("M4_PRODUCTION_GRAPH_BEGIN prepare=1", 1)
        # Keep internal context OFF/ON pairs consistent; only preparation modes differ.
        suffix = suffix.replace("digest=000000000020", "digest=000000000030")
        self.reject(prefix + "M4_PRODUCTION_GRAPH_BEGIN prepare=1" + suffix)

    def test_boundaries(self):
        for marker in ("M4_PRODUCTION_NATIVE_BEGIN", "M4_PRODUCTION_NATIVE_END exit=0",
                       "M4_PRODUCTION_GRAPH_BEGIN prepare=1", "M4_PRODUCTION_GRAPH_END prepare=0 exit=0",
                       "M4_PRODUCTION_GUEST_EXIT=0"):
            self.reject(self.good.replace(marker, "", 1))
            self.reject(self.good.replace(marker, marker + "\n" + marker, 1))
        self.reject(self.good + "\nM4_PRODUCTION_UNKNOWN x=1")
        self.reject(self.good + "\nGGML_RISCV_QBS_M4_PREPARE enabled=1 path=rvv k=896")


if __name__ == "__main__":
    unittest.main()
