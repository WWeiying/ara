#!/usr/bin/env python3
"""Host semantics and optional GNU RVV compilation, never target execution."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SDK_HEADER = Path("software/akv/experimental/quantized_kv/grouped_pv.h")
CROSS = Path(os.environ.get("GROUPED_PV_CC",
    "/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc"))
FLAGS = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-fno-fast-math",
         "-ffp-contract=off", "-frounding-math", "-fno-tree-vectorize",
         "-I" + str(ROOT)]


def command(args):
    p = subprocess.run([str(a) for a in args], text=True, capture_output=True,
                       timeout=120)
    if p.returncode:
        raise AssertionError(f"command failed: {args}\n{p.stdout}\n{p.stderr}")
    return p.stdout


class KernelTests(unittest.TestCase):
    def host(self, optimize):
        cc = os.environ.get("CC", "/usr/bin/gcc")
        with tempfile.TemporaryDirectory(prefix="grouped-pv-host-") as tmp:
            exe = Path(tmp) / "test"
            command([cc, *FLAGS, optimize, HERE / "test_kernel.c", "-lm", "-o", exe])
            out = command([exe])
            self.assertEqual(out, "GROUPED_PV_PASS backend=scalar cases=13824 "
                             "invalid=17 csr=host_fenv rounding=RNE\n")
            print(out.strip())

    def test_host_o0(self):
        self.host("-O0")

    def test_host_o3(self):
        self.host("-O3")

    def test_inactive_scale_mutation_rejected(self):
        with tempfile.TemporaryDirectory(prefix="grouped-pv-mutation-") as tmp:
            tmp = Path(tmp)
            src = (ROOT / SDK_HEADER).read_text()
            old = "if (rescale_mask & (1u << h)) {"
            self.assertEqual(src.count(old), 1)
            mutant = tmp / SDK_HEADER
            mutant.parent.mkdir(parents=True)
            mutant.write_text(src.replace(old, "if (1) {"))
            shutil.copyfile(HERE / "kernel.h", tmp / "kernel.h")
            shutil.copyfile(HERE / "test_kernel.c", tmp / "test_kernel.c")
            exe = tmp / "test"
            command([os.environ.get("CC", "/usr/bin/gcc"), "-I" + str(tmp), *FLAGS, "-O3",
                     tmp / "test_kernel.c", "-lm", "-o", exe])
            p = subprocess.run([exe], text=True, capture_output=True, timeout=120)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("FAIL", p.stderr)
            self.assertNotIn("GROUPED_PV_PASS", p.stdout)

    def test_rvv_compile_only(self):
        if not CROSS.is_file():
            self.skipTest(f"cross compiler unavailable: {CROSS}")
        objdump = CROSS.with_name(CROSS.name.replace("gcc", "objdump"))
        with tempfile.TemporaryDirectory(prefix="grouped-pv-rvv-compile-") as tmp:
            obj = Path(tmp) / "probe.o"
            command([CROSS, *FLAGS, "-O3", "-march=rv64gcv", "-mabi=lp64d",
                     "-DGROUPED_PV_COMPILE_ONLY", "-c", HERE / "test_kernel.c",
                     "-o", obj])
            dis = command([objdump, "-dr", obj])
            for opcode in ("vsetvli", "vle32.v", "vse32.v", "vfmul.vf", "vfmacc.vf"):
                self.assertIn(opcode, dis)
            self.assertNotIn("vfmadd.", dis)
            self.assertNotRegex(dis, r"R_RISCV_CALL[^\n]*(?:fmaf|memcpy)")
            self.assertRegex(dis, r"e32,\s*m4")
            # Compile the complete runnable fixture too; it is NOT executed here.
            command([CROSS, *FLAGS, "-O3", "-march=rv64gcv", "-mabi=lp64d",
                     "-c", HERE / "test_kernel.c", "-o", obj])
            full = command([objdump, "-dr", obj])
            refs = re.findall(r"^\s*[0-9a-f]+ <(reference[^>]*)>:", full, re.M)
            self.assertTrue(refs, "scalar oracle symbol missing")
            for symbol in refs:
                # A -dr listing includes local labels: do not truncate at the
                # first loop label and accidentally inspect just the prologue.
                body = command([objdump, "-dr", f"--disassemble={symbol}", obj])
                self.assertIn("fmul.s", body)
                self.assertIn("fmadd.s", body)
                self.assertNotRegex(body, r"\s(?:vset\w+|vf\w+|vl\w+|vs\w+)\s")
            print("GROUPED_PV_COMPILE_ONLY rv64gcv RVV_mul_FMA_present oracle_scalar=1 executed=0")


if __name__ == "__main__":
    unittest.main()
