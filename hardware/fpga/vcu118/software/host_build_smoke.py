#!/usr/bin/env python3
"""Build scalar smoke and deliberate-trap ELFs; Windows users use the prebuilts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc", default=str(here.parents[3] / "install/riscv-gcc/bin/riscv64-unknown-elf-gcc"))
    parser.add_argument("--out", type=Path, default=here)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    flags = ["-march=rv64imac_zicsr_zifencei", "-mabi=lp64", "-mcmodel=medany", "-O2",
             "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-fno-builtin", "-fno-pic",
             "-fno-stack-protector", "-nostdlib", "-nostartfiles", "-Wl,--build-id=none",
             "-T", "host_smoke.ld", "host_start.S", "host_smoke.c"]
    record = {"compiler": subprocess.check_output([args.gcc, "--version"], text=True).splitlines()[0],
              "flags": flags, "sources": {}, "outputs": {}}
    for name in ("host_start.S", "host_smoke.c", "host_smoke.ld", "fpga_debug.h"):
        record["sources"][name] = hashlib.sha256((here / name).read_bytes()).hexdigest()
    for name, extra in (("host_smoke.elf", []), ("host_trap.elf", ["-DHOST_FORCE_TRAP=1"]),
                        ("host_ddr2_smoke.elf", ["-DHOST_DDR2_CANARY=1"])):
        target = (args.out / name).resolve()
        subprocess.run([args.gcc, *flags, *extra, "-o", str(target)], cwd=here, check=True)
        record["outputs"][name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (args.out / "host_smoke_build.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
