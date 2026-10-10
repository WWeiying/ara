#!/usr/bin/env python3
"""Isolated Clang/HTIF builds following build_rvv_memory_gaps.py; never runs VCS."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "apps/riscv-tests/isa/rv64uv"
NAMES = ["vgap35_" + n for n in (
    "mask_ta", "carry_ta", "slide_bound", "vstart_csr", "memory_noop", "carry_illegal")]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=NAMES, action="append")
    parser.add_argument("--spike", type=Path, required=True,
                        help="campaign-pinned vstart-capable Spike, not the legacy install")
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to(ROOT / "verification/out") and out.name.startswith("gap35-rvv-")
    out.mkdir(parents=True, exist_ok=True)
    campaign = json.loads((ROOT / "verification/out/repaired-aligned-600-20260930-01/plan.json").read_text())
    oracle = next(c for c in campaign["cases"] if c.get("spike"))
    spike = args.spike.resolve(strict=True)
    assert str(spike) == oracle["spike"] and digest(spike) == oracle["spike_sha256"]
    apps = ROOT / "apps"
    common = apps / "common"
    isa = apps / "riscv-tests/isa"
    runtime = apps / "riscv-tests/benchmarks/common"
    llvm = ROOT / "install/riscv-llvm"
    cc = llvm / "bin/clang"
    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "--target=riscv64-unknown-elf",
             "-mcmodel=medany", "-mno-relax", "-O2", "-std=gnu99", "-fno-vectorize",
             "-fno-slp-vectorize", "-mno-implicit-float", "-fno-common", "-fno-builtin-printf",
             "-DNR_LANES=4", "-DVLEN=1024"]
    inc = [f"-I{apps / 'include'}", f"-I{common}", f"-I{isa / 'macros/scalar'}",
           f"-I{isa / 'macros/vector'}"]
    section_flags = ["-ffunction-sections", "-fdata-sections"]
    commands = []

    def command(argv):
        argv = list(map(str, argv))
        commands.append(argv)
        save(out / "build_commands.json", commands)
        result = subprocess.run(argv, cwd=ROOT, capture_output=True)
        with (out / "build.log").open("ab") as stream:
            stream.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"command failed: {argv}; see {out / 'build.log'}")
        return result

    objects, spike_objects = [], []
    for filename in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c"):
        obj = out / (filename + ".o")
        command([cc, *flags, *section_flags, *inc, "-c", common / filename, "-o", obj])
        objects.append(obj)
    for filename in ("crt.S", "syscalls.c"):
        obj = out / ("spike_" + filename + ".o")
        command([cc, *flags, f"-I{apps / 'riscv-tests/env'}", f"-I{runtime}",
                 "-DPREALLOCATE=1", "-D__SPIKE__=1", "-c", runtime / filename, "-o", obj])
        spike_objects.append(obj)

    results = []
    for name in args.case or NAMES:
        source = DEST / (name + ".c")
        elf = out / ("rv64uv-ara-" + name)
        spike_elf = out / (name + ".spike")
        command([cc, *flags, *section_flags, *inc, "-fuse-ld=lld", "-static", "-nostartfiles",
                 "-Wl,--gc-sections", f"-T{common / 'link.ld'}", source, *objects,
                 "-lm", f"-L{llvm.resolve() / 'lib/generic'}", "-lclang_rt.builtins-riscv64",
                 "-o", elf])
        command([cc, *flags, *inc, f"-I{runtime}", f"-I{apps / 'riscv-tests/env'}",
                 "-D__SPIKE__=1", "-DPREALLOCATE=1", "-fuse-ld=lld", "-static", "-nostdlib",
                 f"-T{runtime / 'test.ld'}", source, *spike_objects, "-o", spike_elf])
        dis = command([llvm / "bin/llvm-objdump", "-d", elf])
        (out / (name + ".dis")).write_bytes(dis.stdout)
        argv = [str(spike), "--isa=rv64gcv_zfh_zvl1024b", str(spike_elf)]
        started = time.monotonic()
        result = subprocess.run(argv, capture_output=True, timeout=30)
        log = out / (name + ".spike.log")
        log.write_bytes(result.stdout + result.stderr)
        passed = result.returncode == 0 and b"PASSED:" in log.read_bytes()
        row = {"test": "rvv:" + name, "status": "PASS" if passed else "FAIL",
               "returncode": result.returncode, "seconds": round(time.monotonic() - started, 3),
               "command": argv, "binary": str(elf), "binary_sha256": digest(elf),
               "spike_tool_sha256": digest(spike),
               "spike_binary": str(spike_elf), "spike_sha256": digest(spike_elf),
               "log": str(log), "source_hashes": {str(p): digest(p) for p in
                    (source, DEST / "vgap35_common.h", Path(__file__).resolve())}}
        results.append(row)
        save(out / "spike_results.json", results)
        print(name, row["status"], row["seconds"], flush=True)
        if not passed:
            raise SystemExit(f"Spike preflight failed: {name}; see {log}")


if __name__ == "__main__":
    main()
