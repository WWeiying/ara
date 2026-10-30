import unittest

from check import BLOCKS, ELIGIBLE, FNV_OFFSET, SEEDS, check_output, fold


def fixture():
    lines = []
    for run in range(4):
        mode, trace = divmod(run, 2)
        lines.append(f"M4_TU_RUN_BEGIN run={run} mode={mode} trace={trace}")
        hash_value = FNV_OFFSET
        for seq in range(1140):
            dataset, sub = divmod(seq, 15)
            frm, seed_index = divmod(sub, 3)
            seed = SEEDS[seed_index]
            vcsr, k = (frm + seed) & 7, BLOCKS[dataset] * 32
            lines.append(f"M4_TU_CASE_BEGIN seq={seq} dataset={dataset} k={k} frm={frm} flags={seed} vcsr={vcsr}")
            if trace:
                path = "rvv" if mode and frm == 0 and dataset in ELIGIBLE else "generic"
                lines.append(f"GGML_RISCV_QBS_M4_PREPARE enabled={mode} path={path} k={k}")
            value = seq + 1
            hash_value = fold(hash_value, value)
            lines.append(f"M4_TU_CASE_PASS seq={seq} digest={value:016x} fcsr={(frm << 5) | seed} vcsr={vcsr}")
        lines.append(f"M4_TU_CSR_PASS mode={mode} trace={trace} datasets=76 checks=1140 "
                     f"digest={hash_value:016x} bytes=exact fcsr=exact vcsr=exact")
        lines.append(f"M4_TU_RUN_END run={run} exit=0")
    lines.append("M4_TU_GUEST_EXIT=0")
    return "\n".join(lines)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = fixture()

    def reject(self, text):
        with self.assertRaises(ValueError):
            check_output(text)

    def test_accept(self):
        r = check_output(self.good)
        self.assertEqual((r["checks"], r["production_rvv_traces"], r["production_generic_traces"]),
                         (4560, 198, 2082))

    def test_every_label_suffix_is_rejected(self):
        for label in ("M4_TU_RUN_BEGIN", "M4_TU_CASE_BEGIN", "M4_TU_CASE_PASS", "M4_TU_CSR_PASS",
                      "M4_TU_RUN_END", "GGML_RISCV_QBS_M4_PREPARE", "M4_TU_GUEST_EXIT=0"):
            with self.subTest(label=label):
                self.reject(self.good.replace(label, label + "_BOGUS", 1))

    def test_fields_exact(self):
        for prefix in ("M4_TU_RUN_BEGIN", "M4_TU_CASE_BEGIN", "M4_TU_CASE_PASS", "M4_TU_CSR_PASS",
                       "M4_TU_RUN_END", "GGML_RISCV_QBS_M4_PREPARE"):
            line = next(l for l in self.good.splitlines() if l.startswith(prefix + " "))
            for bad in (line + " extra=0", line.rsplit(" ", 1)[0], line + " " + line.split()[1]):
                with self.subTest(prefix=prefix, bad=bad):
                    self.reject(self.good.replace(line, bad, 1))

    def test_missing_duplicate_records(self):
        for prefix in ("M4_TU_RUN_BEGIN", "M4_TU_CASE_BEGIN", "M4_TU_CASE_PASS", "M4_TU_CSR_PASS",
                       "M4_TU_RUN_END", "GGML_RISCV_QBS_M4_PREPARE", "M4_TU_GUEST_EXIT=0"):
            line = next(l for l in self.good.splitlines() if l.startswith(prefix))
            self.reject(self.good.replace(line, "", 1))
            self.reject(self.good.replace(line, line + "\n" + line, 1))

    def test_wrong_path_and_geometry(self):
        for old, new in (("path=rvv", "path=generic"), ("k=32 frm=0", "k=64 frm=0"),
                         ("dataset=0", "dataset=1"), ("frm=0 flags=0", "frm=1 flags=0"),
                         ("checks=1140", "checks=1139"), ("datasets=76", "datasets=75")):
            self.reject(self.good.replace(old, new, 1))

    def test_csr_and_digests(self):
        for old, new in (("fcsr=0 vcsr=0", "fcsr=32 vcsr=0"), ("fcsr=8 vcsr=0", "fcsr=0 vcsr=0"),
                         ("fcsr=31 vcsr=7", "fcsr=31 vcsr=6"), ("digest=0000000000000001", "digest=0000000000000002")):
            self.reject(self.good.replace(old, new, 1))

    def test_trace_when_disabled(self):
        self.reject(self.good.replace("M4_TU_CASE_PASS seq=0", "GGML_RISCV_QBS_M4_PREPARE enabled=0 path=generic k=32\nM4_TU_CASE_PASS seq=0", 1))

    def test_unknown_and_failure(self):
        for suffix in ("M4_TU_BOGUS value=1", "GGML_RISCV_QBS_COMMAND anything=1", "Kernel panic"):
            self.reject(self.good + "\n" + suffix)


if __name__ == "__main__":
    unittest.main()
