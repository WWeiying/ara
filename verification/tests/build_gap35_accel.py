#!/usr/bin/env python3
"""Build three selfchecking accelerator ELFs and host prechecks, never run RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
NAMES = ["qbs_gap35_descriptor", "qbs_gap35_wide_tail", "akv_gap35_descriptor"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / "verification/out") or not out.name.startswith("gap35-accel-"):
        parser.error("output must be a new verification/out/gap35-accel-* directory")
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(argv, label, timeout=120, check=True):
        argv = [str(a) for a in argv]
        commands.append({"command": argv, "cwd": str(ROOT), "timeout_s": timeout})
        save(out / "commands.json", commands)
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout)
        (out / f"{label}.log").write_bytes(proc.stdout + proc.stderr)
        if check and proc.returncode:
            raise SystemExit(f"{label} failed ({proc.returncode}): {out / (label + '.log')}")
        return proc

    common = ROOT / "apps/common"
    llvm = (ROOT / "install/riscv-llvm").resolve()
    cc = llvm / "bin/clang"
    flags = ["--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
             "-mcmodel=medany", "-mno-relax", "-O2", "-std=gnu11",
             "-fno-vectorize", "-fno-slp-vectorize", "-fno-fast-math", "-ffp-contract=off",
             "-mno-implicit-float", "-fno-common", "-fno-builtin-printf", "-ffunction-sections",
             "-DNR_LANES=4", "-DVLEN=1024", f"-I{common}", f"-I{ROOT / 'apps/include'}"]
    objects = []
    for filename in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c"):
        obj = out / (filename + ".o")
        run([cc, *flags, "-MD", "-c", common / filename, "-o", obj], filename)
        objects.append(obj)
    records = []
    for name in NAMES:
        source = ROOT / "apps" / name / "main.c"
        reference = ROOT / ("verification/qbs/qbs_ref.c" if name.startswith("qbs") else
                            "software/akv/src/akv_v2_reference.c")
        host = out / (name + ".host")
        run(["cc", "-std=gnu11", "-O2", "-fno-fast-math", "-ffp-contract=off",
             "-fno-tree-vectorize", "-Wall", "-Wextra", "-Wno-unused-function",
             "-DGAP35_HOST", f"-I{common}", source, reference, "-lm", "-o", host], name + ".host-build")
        result = run([host], name + ".reference", timeout=30)
        if f"PASSED: {name} ".encode() not in result.stdout or b"errors=0" not in result.stdout:
            raise SystemExit("missing successful host selfcheck marker")
        obj = out / (name + ".o")
        run([cc, *flags, "-Wall", "-Wextra", "-Wno-unused-function", "-MD", "-c", source,
             "-o", obj], name + ".compile")
        elf = out / (name + ".elf")
        run([cc, *flags, "-fuse-ld=lld", "-static", "-nostartfiles", "-Wl,--gc-sections",
             f"-Wl,-Map={out / (name + '.map')}", f"-T{common / 'link.ld'}", obj, *objects,
             "-lm", f"-L{llvm / 'lib/generic'}", "-lclang_rt.builtins-riscv64", "-o", elf], name + ".link")
        run([llvm / "bin/llvm-objdump", "-d", elf], name + ".disassembly")
        fit = out / (name + ".elf-fit.json")
        run([ROOT / "verification/tools/soc-venv/bin/python", ROOT / "verification/coverage/check_elf_fit.py",
             "--elf", elf, "--ram-bytes", "0x200000", "--output", fit], name + ".elf-fit")
        deps = {source, reference, common / "link.ld", Path(__file__).resolve()}
        if name.startswith("akv"):
            deps.update((ROOT / "software/akv/include/akv/akv.h",
                         ROOT / "software/akv/include/akv/akv_abi.h"))
        for dep in [out / (name + ".d"), *[out / (p.name[:-2] + ".d") for p in objects]]:
            deps.update(Path(p).resolve() for p in shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1]))
        record = {"name": name, "binary": str(elf), "binary_sha256": sha(elf),
                  "sources": sorted(map(str, deps)), "source_hashes": {str(p): sha(p) for p in sorted(deps)},
                  "host_result": result.stdout.decode().strip(), "host_reference": str(reference),
                  "host_log": str(out / (name + ".reference.log")), "elf_fit": str(fit),
                  "disassembly": str(out / (name + ".disassembly.log")),
                  "custom_instruction_execution_prechecked": False, "vcs_launched": False}
        save(out / (name + ".precheck.json"), record)
        records.append(record)
        print(name, result.stdout.decode().strip(), "ELF fit PASS", flush=True)
    save(out / "build-results.json", {"status": "BUILT_HOST_PRECHECK_PASS", "cases": records,
         "rtl_status": "NOT_RUN", "scope": "Host data/reference precheck, not proof of custom ISA execution. AKV V1 snapshots and rejection lifecycle are test-side adapters; V2 data uses existing reference API."})


if __name__ == "__main__":
    main()
