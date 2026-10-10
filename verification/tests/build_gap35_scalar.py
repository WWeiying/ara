#!/usr/bin/env python3
"""Build only gap35 scalar cases and run bounded, same-source Spike prechecks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "apps/riscv-tests/isa/rv64uv"
NAMES = ["scalar_gap35_memory", "scalar_gap35_alu_control", "scalar_gap35_illegal"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    common = ROOT / "apps/common"
    runtime = ROOT / "apps/riscv-tests/benchmarks/common"
    llvm = ROOT / "install/riscv-llvm"
    cc = llvm / "bin/clang"
    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "--target=riscv64-unknown-elf",
             "-mcmodel=medany", "-mno-relax", "-O2", "-std=gnu99", "-fno-vectorize",
             "-fno-slp-vectorize", "-mno-implicit-float", "-fno-common",
             "-fno-builtin-printf", "-DNR_LANES=4", "-DVLEN=1024"]
    includes = [f"-I{ROOT / p}" for p in ("apps/include", "apps/common",
                "apps/riscv-tests/isa/macros/scalar", "apps/riscv-tests/env",
                "apps/riscv-tests/benchmarks/common")]
    sources = [DEST / (name + ".c") for name in NAMES] + [DEST / "scalar_gap35_common.h"]
    sources += [common / n for n in ("crt0.S", "printf.c", "string.c", "serial.c",
                                     "util.c", "print_trap_cause.c", "link.ld")]
    sources += [runtime / n for n in ("crt.S", "syscalls.c", "test.ld")]
    pins = {str(p): sha(p) for p in sources}
    (out / "sources.json").write_text(json.dumps(pins, indent=2) + "\n")
    commands, results = [], []

    def command(argv, log=None, timeout=60):
        argv = list(map(str, argv))
        commands.append(argv)
        (out / "build_commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout)
        if log:
            log.write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"command failed: {argv}\n{result.stderr.decode(errors='replace')}")
        return result

    objects, spike_objects = [], []
    for filename in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c"):
        obj = out / (filename + ".o")
        command([cc, *flags, *includes, "-c", common / filename, "-o", obj])
        objects.append(obj)
    spike_flags = [*flags, "-D__SPIKE__=1", "-DPREALLOCATE=1"]
    for filename in ("crt.S", "syscalls.c"):
        obj = out / ("spike_" + filename + ".o")
        command([cc, *spike_flags, *includes, "-c", runtime / filename, "-o", obj])
        spike_objects.append(obj)
    for name in NAMES:
        source = DEST / (name + ".c")
        elf = ROOT / "apps/bin" / ("rv64uv-ara-" + name)
        elf.parent.mkdir(exist_ok=True)
        command([cc, *flags, *includes, "-fuse-ld=lld", "-static", "-nostartfiles",
                 f"-T{common / 'link.ld'}", source, *objects, "-lm",
                 f"-L{llvm.resolve() / 'lib/generic'}", "-lclang_rt.builtins-riscv64",
                 "-o", elf], out / (name + ".build.log"))
        spike_elf = out / (name + ".spike")
        command([cc, *spike_flags, *includes, "-fuse-ld=lld", "-static", "-nostdlib",
                 f"-T{runtime / 'test.ld'}", source, *spike_objects, "-o", spike_elf],
                out / (name + ".spike.build.log"))
        for path in (elf, spike_elf):
            command([llvm / "bin/llvm-objdump", "-d", "--mattr=+c,+d", "-M", "no-aliases", path],
                    out / (path.name + ".dis"))
        log = out / (name + ".spike.log")
        argv = [ROOT / "install/riscv-isa-sim/bin/spike", "--isa=rv64gcv_zfh",
                "--pmpregions=0", "--varch=vlen:1024,elen:64", spike_elf]
        started = time.monotonic()
        result = command(argv, log, timeout=30)
        if f"PASSED: {name}".encode() not in result.stdout + result.stderr:
            raise RuntimeError(f"missing Spike pass marker: {log}")
        results.append(dict(test="rvv:" + name, elf=str(elf), elf_sha256=sha(elf),
                            spike_elf=str(spike_elf), spike_sha256=sha(spike_elf),
                            spike_log=str(log), command=list(map(str, argv)),
                            returncode=result.returncode,
                            seconds=round(time.monotonic() - started, 3),
                            status="SPIKE_PASS_RTL_NOT_RUN"))
        (out / "spike_results.json").write_text(json.dumps(results, indent=2) + "\n")
        print("Spike PASS", name, elf, flush=True)
    if any(sha(Path(p)) != digest for p, digest in pins.items()):
        raise RuntimeError("source changed during precheck")
    (out / "ready.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
