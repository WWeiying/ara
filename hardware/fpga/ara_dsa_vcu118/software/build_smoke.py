#!/usr/bin/env python3
"""Optional rebuild; the exported package includes the prebuilt smoke ELF."""
import argparse
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--gcc", default="riscv64-unknown-elf-gcc")
parser.add_argument("--objdump", default="riscv64-unknown-elf-objdump")
args = parser.parse_args()
here = Path(__file__).resolve().parent
cmd = [args.gcc, "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany",
       "-O2", "-ffreestanding", "-fno-builtin", "-fno-tree-vectorize", "-fno-stack-protector",
       "-fno-pie", "-no-pie", "-nostdlib", "-nostartfiles", "-static",
       "-Wl,--build-id=none", "-Wl,--no-relax", "-Wl,-Map=" + str(here / "smoke.map"),
       "-I" + str(here / "include"), "-T" + str(here / "smoke.ld"),
       str(here / "start.S"), str(here / "smoke.c"), "-o", str(here / "smoke.elf")]
subprocess.run(cmd, check=True)
with (here / "smoke.dump").open("w") as output:
    subprocess.run([args.objdump, "-d", str(here / "smoke.elf")], stdout=output, check=True)
print(here / "smoke.elf")
