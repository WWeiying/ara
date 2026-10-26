"""Host-only synthetic protocol mutation tests, not numerical execution evidence."""
from pathlib import Path
import unittest

import check_native as checker


def transcript(vlen=1024):
    lines = ["boot noise"]
    for mode in (0, 1):
        lines += [f"Q8K_COMBINED_MODE_BEGIN mode={mode}",
                  f"Q8K_COMBINED_BEGIN mode={mode} vlen={vlen} cases=50"]
        for index, (name, k, eligible) in enumerate(checker.CASES):
            for frm in range(5):
                for env, seed in enumerate(checker.SEEDS):
                    path = "rvv" if mode and eligible and k and frm == 0 else "generic"
                    fcsr = (frm << 5) | seed
                    lines += [
                        f"Q8K_COMBINED_CALL id={index} name={name} k={k} "
                        f"eligible={int(eligible)} frm={frm} env={env} seed={seed}",
                        f"GGML_RISCV_QBS_Q8K_M4_PREPARE enabled={mode} path={path} k={k}",
                        f"Q8K_COMBINED_CALL_PASS id={index} frm={frm} env={env} "
                        f"ef={fcsr} af={fcsr} ev={env} av={env} {checker.EXACT} "
                        f"signedmax={int(frm == 0 and name.startswith('first_max_'))} "
                        f"fma={int(frm == 0 and name == 'fma_rounding')} "
                        f"underflow={int(frm == 0 and name == 'fused_underflow')} "
                        f"input_digest={index+1:016x} digest={index*40+frm*8+env:016x}"]
        lines += [f"Q8K_COMBINED_PASS mode={mode} cases=50 checks=2000",
                  f"Q8K_COMBINED_MODE_END mode={mode} exit=0"]
    lines.append("Q8K_COMBINED_GUEST_EXIT=0")
    return "\n".join(lines) + "\n"


class CheckNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid = transcript()

    def reject(self, text):
        with self.assertRaises(ValueError):
            checker.check_output(text)

    def test_valid_both_vlens(self):
        for vlen in (128, 1024):
            result = checker.check_output(transcript(vlen))
            self.assertEqual(result["state"], "PASS")
            self.assertEqual(result["checks"], 4000)
            self.assertEqual(result["real_cases"], 6)
            self.assertEqual([m["vector"] for m in result["modes"]], [0, 312])
            self.assertEqual([m["fallback"] for m in result["modes"]], [2000, 1688])

    def test_inventory(self):
        self.assertEqual(len(checker.CASES), 50)
        self.assertEqual(sum(bool(k and eligible) for _, k, eligible in checker.CASES), 39)
        self.assertEqual([k for _, k, _ in checker.CASES[-6:]], [1536]*4 + [8960]*2)
        self.assertEqual(checker.SEEDS, (0, 1, 2, 4, 8, 16, 31, 0))

    def test_missing_duplicate_and_reordered_records(self):
        lines = self.valid.splitlines()
        for position in (1, 2, 3, 4, 5, 12004, len(lines)-1):
            with self.subTest(position=position, mutation="missing"):
                self.reject("\n".join(lines[:position] + lines[position+1:]))
            with self.subTest(position=position, mutation="duplicate"):
                self.reject("\n".join(lines[:position] + [lines[position]] + lines[position:]))
        lines[4], lines[7] = lines[7], lines[4]
        # Identical adjacent trace text cannot distinguish these calls; move a PASS instead.
        lines[5], lines[8] = lines[8], lines[5]
        self.reject("\n".join(lines))

    def test_mutated_fields(self):
        mutations = [
            ("MODE_BEGIN mode=0", "MODE_BEGIN mode=1"),
            ("vlen=1024", "vlen=256"),
            ("vlen=1024", "vlen=128"),
            ("name=zero", "name=missing"),
            ("eligible=1 frm=0", "eligible=0 frm=0"),
            ("frm=0 env=0 seed=0", "frm=0 env=0 seed=1"),
            ("enabled=0 path=generic", "enabled=0 path=rvv"),
            ("enabled=1 path=rvv", "enabled=1 path=generic"),
            ("enabled=1 path=generic", "enabled=1 path=rvv"),
            ("enabled=1 path=rvv", "enabled=0 path=rvv"),
            ("path=generic k=256", "path=generic k=512"),
            ("QBS_Q8K_M4_PREPARE", "QBS_M4_PREPARE"),
            ("ef=0 af=0", "ef=0 af=1"),
            ("ef=0 af=0", "ef=32 af=32"),
            ("ef=1 af=1", "ef=0 af=0"),
            ("ev=0 av=0", "ev=0 av=1"),
            ("ev=1 av=1", "ev=0 av=0"),
            ("packedbytes=exact", "packedbytes=wrong"),
            ("scales=exact", "scales=wrong"),
            ("bsums=exact", "bsums=wrong"),
            ("input=exact", "input=wrong"),
            ("canaries=exact", "canaries=wrong"),
            ("signedmax=1", "signedmax=0"),
            ("fma=1", "fma=0"),
            ("underflow=1", "underflow=0"),
            ("input_digest=0000000000000001", "input_digest=0000000000000002"),
            ("digest=0000000000000000", "digest=000000000000000a"),
            ("digest=0000000000000000", "digest=xyz"),
            ("cases=50 checks=2000", "cases=50 checks=1999"),
            ("MODE_END mode=0 exit=0", "MODE_END mode=0 exit=1"),
            ("GUEST_EXIT=0", "GUEST_EXIT=1"),
        ]
        for old, new in mutations:
            with self.subTest(old=old, new=new):
                self.assertIn(old, self.valid)
                self.reject(self.valid.replace(old, new, 1))

    def test_underflow_witness(self):
        # Even paired, equal FCSRs must not introduce UF in the fused witness.
        lines = self.valid.splitlines()
        for index, line in enumerate(lines):
            if "CALL_PASS id=8 frm=0 env=0 " in line:
                lines[index] = line.replace("ef=0 af=0", "ef=2 af=2")
        self.reject("\n".join(lines))

    def test_csr_pair_mismatch(self):
        # Both local FCSRs agree and preserve rounding/sticky, but modes differ.
        self.reject(self.valid.replace("ef=0 af=0", "ef=1 af=1", 1))

    def test_all_calls_required(self):
        lines = self.valid.splitlines()
        for index, line in enumerate(lines):
            if "CALL id=44 " in line:
                self.reject("\n".join(lines[:index] + lines[index+3:]))
                break
        else:
            self.fail("Real case missing from fixture")

    def test_diagnostics_and_unattributed_traces(self):
        for extra in ("Q8K_COMBINED_FAIL reason=test", "Kernel panic", "Illegal instruction",
                      "Assertion x failed", "Segmentation fault", "qemu: fatal",
                      "Q8K_COMBINED_UNKNOWN", "Q8K_COMBINED_GUEST_EXIT=0",
                      "GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=1 path=rvv k=256"):
            with self.subTest(extra=extra):
                self.reject(self.valid + extra + "\n")

    def test_production_entrypoint_only(self):
        source = Path(__file__).with_name("native.cpp").read_text()
        self.assertIn("template <int64_t INTER_SIZE, ggml_type PARAM_TYPE>", source)
        self.assertIn("ggml_quantize_mat_t<1, GGML_TYPE_Q8_K>(x, y, 4, k);", source)
        self.assertIn("ggml_quantize_mat_q8_K_4x1_ara_generic(x, y, k);", source)
        self.assertNotIn("qbs_q8k_m4_prepare_candidate", source)
        self.assertNotIn("setenv(", source)


if __name__ == "__main__":
    unittest.main()
