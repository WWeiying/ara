#!/usr/bin/env python3
"""Build only new memory-gap ELFs; leave existing runtime objects/tools alone."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from generate_rvv_memory_gaps import ROOT, DEST, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="stem; default all 40")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spike", action="store_true",
                        help="also build HTIF ELFs and run Spike (30s per case)")
    args = parser.parse_args()
    names = [case[0] for case in cases()]
    selected = args.case or names
    if any(name not in names for name in selected):
        parser.error("unknown case")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    apps = ROOT / "apps"
    common = apps / "common"
    isa = apps / "riscv-tests/isa"
    runtime = apps / "riscv-tests/benchmarks/common"
    llvm = ROOT / "install/riscv-llvm"
    cc = llvm / "bin/clang"
    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
             "--target=riscv64-unknown-elf", "-mcmodel=medany", "-mno-relax",
             "-O2", "-std=gnu99", "-fno-vectorize", "-fno-slp-vectorize",
             "-mno-implicit-float", "-fno-common", "-fno-builtin-printf",
             "-ffunction-sections", "-fdata-sections", "-DNR_LANES=4", "-DVLEN=1024"]
    includes = [f"-I{apps / 'include'}", f"-I{common}",
                f"-I{isa / 'macros/scalar'}", f"-I{isa / 'macros/vector'}"]
    # The legacy HTIF linker script only collects .text/.bss/.tbss, not .*.
    spike_flags = [flag for flag in flags
                   if flag not in ("-ffunction-sections", "-fdata-sections")]
    commands = []

    def command(argv):
        commands.append([str(arg) for arg in argv])
        (out / "build_commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        subprocess.run(argv, check=True, cwd=ROOT)

    objects = []
    for filename in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c",
                     "print_trap_cause.c"):
        obj = out / (filename + ".o")
        command([cc, *flags, *includes, "-c", common / filename, "-o", obj])
        objects.append(obj)
    spike_objects = []
    if args.spike:
        for filename in ("crt.S", "syscalls.c"):
            obj = out / ("spike_" + filename + ".o")
            command([cc, *spike_flags, f"-I{apps / 'riscv-tests/env'}", f"-I{runtime}",
                     "-DPREALLOCATE=1", "-D__SPIKE__=1", "-c", runtime / filename,
                     "-o", obj])
            spike_objects.append(obj)
    results = []
    for name in selected:
        source = DEST / (name + ".c")
        elf = apps / "bin" / ("rv64uv-ara-" + name)
        elf.parent.mkdir(exist_ok=True)
        command([cc, *flags, *includes, "-fuse-ld=lld", "-static", "-nostartfiles",
                 "-Wl,--gc-sections", f"-T{common / 'link.ld'}",
                 source, *objects, "-lm", f"-L{llvm.resolve() / 'lib/generic'}",
                 "-lclang_rt.builtins-riscv64", "-o", elf])
        print(f"built {elf}", flush=True)
        if args.spike:
            spike_elf = out / (name + ".spike")
            command([cc, *spike_flags, *includes, f"-I{runtime}",
                     f"-I{apps / 'riscv-tests/env'}", "-D__SPIKE__=1",
                     "-DPREALLOCATE=1", "-fuse-ld=lld", "-static", "-nostdlib",
                     f"-T{runtime / 'test.ld'}", source, *spike_objects,
                     "-o", spike_elf])
            argv = [str(ROOT / "install/riscv-isa-sim/bin/spike"),
                    "--isa=rv64gcv_zfh", "--varch=vlen:1024,elen:64",
                    str(spike_elf)]
            started = time.monotonic()
            result = subprocess.run(argv, capture_output=True, timeout=30)
            (out / (name + ".spike.log")).write_bytes(result.stdout + result.stderr)
            results.append({"test": "rvv:" + name, "command": argv,
                            "returncode": result.returncode,
                            "seconds": round(time.monotonic() - started, 3)})
            (out / "spike_results.json").write_text(json.dumps(results, indent=2) + "\n")
            if result.returncode or b"PASSED:" not in result.stdout + result.stderr:
                raise SystemExit(f"Spike preflight failed: {name}; see {out}")
            print(f"Spike PASS {name}", flush=True)


if __name__ == "__main__":
    main()
