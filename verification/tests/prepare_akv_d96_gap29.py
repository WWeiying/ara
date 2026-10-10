#!/usr/bin/env python3
"""Build/precheck one distinct AKV D96 test; never launch RTL or a service."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out/akv-d96-gap29-precheck-20260928-01"
HERE = ROOT / "verification/tests"


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(argv, label):
        argv = list(map(str, argv))
        commands.append({"command": argv, "cwd": str(ROOT)})
        (OUT / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=120)
        (OUT / (label + ".log")).write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(f"{label} failed: {result.returncode}; see {OUT}")
        return result

    source = ROOT / "apps/akv_d96_gap29/main.c"
    reference = ROOT / "software/akv/src/akv_v2_reference.c"
    host = OUT / "akv_d96_gap29.host"
    host_objects = []
    for index, path in enumerate((source, reference)):
        obj = OUT / f"host{index}.o"
        run(["cc", "-std=gnu11", "-O2", "-fno-fast-math", "-ffp-contract=off",
             "-fno-tree-vectorize", "-DAKV_GAP29_HOST", "-MD", "-c", path,
             "-o", obj], f"host{index}")
        host_objects.append(obj)
    run(["cc", *host_objects, "-o", host], "host-link")
    result = run([host], "reference")
    if b"rows=9 elements=864 errors=0" not in result.stdout:
        raise SystemExit("missing successful reference evidence")

    cc = ROOT / "install/riscv-llvm/bin/clang"
    common = ROOT / "apps/common"
    flags = ["--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
             "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-O2",
             "-std=gnu11", "-fno-vectorize", "-fno-slp-vectorize",
             "-fno-fast-math", "-ffp-contract=off", "-mno-implicit-float",
             "-fno-common", "-fno-builtin-printf", "-ffunction-sections",
             "-fdata-sections", "-DNR_LANES=4", "-DVLEN=1024",
             f"-I{common}", f"-I{ROOT / 'apps/include'}"]
    objects = []
    inputs = [source] + [common / name for name in (
        "crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")]
    for index, path in enumerate(inputs):
        obj = OUT / f"soc{index}.o"
        run([cc, *flags, "-MD", "-c", path, "-o", obj], f"soc{index}")
        objects.append(obj)
    elf = ROOT / "apps/bin/akv_d96_gap29"
    if elf.exists():
        raise SystemExit(f"refusing to replace existing ELF: {elf}")
    run([cc, *flags, "-fuse-ld=lld", "-static", "-nostartfiles",
         "-Wl,--gc-sections", f"-T{common / 'link.ld'}", *objects, "-lm",
         f"-L{(ROOT / 'install/riscv-llvm/lib/generic').resolve()}",
         "-lclang_rt.builtins-riscv64", "-o", elf], "soc-link")
    fit = ROOT / "verification/coverage/check_elf_fit.py"
    run([ROOT / "verification/tools/soc-venv/bin/python", fit, "--elf", elf,
         "--ram-bytes", "0x200000", "--output", OUT / "elf-fit.json"], "elf-fit")
    selection = HERE / "akv_d96_gap29_selection.json"
    tests = ["app:akv_d96_gap29"]
    selection.write_text(json.dumps({"tests": tests}, indent=2) + "\n")
    paths = {Path(__file__).resolve(), source, reference, elf, host, selection,
             common / "link.ld", fit, cc.resolve()}
    for dep in OUT.glob("*.d"):
        dependencies = shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1])
        paths.update((ROOT / item).resolve() for item in dependencies)
    paths.update(path for path in OUT.iterdir() if path.is_file())
    ready = {
        "status": "READY", "selection": str(selection), "tests": tests,
        "files": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(paths)},
        "software_reference_results": [{
            "test": tests[0], "status": "PASS", "returncode": 0,
            "log": str(OUT / "reference.log"), "rows": 9, "elements": 864,
            "reference": str(reference), "scope": "host V2 model vs independent bit-pattern oracle"}],
        "elf_fit": str(OUT / "elf-fit.json"), "timeout_s": 300,
        "rtl_runtime_measured": False, "rtl_changed": False,
        "vcs_launched": False, "custom_instruction_execution_prechecked": False,
        "launch_gate": "521-case original-image batch complete AND explicit manual user approval",
        "image_policy": "original frozen image underlying 473 PASS; no repaired image",
        "shape": {"q_rows": 3, "kv_length": 3, "head_dim": 96,
                  "stride_bytes": 192, "v2_fills": 1, "row_loads": 9, "releases": 1},
        "coverage_targets": ["D96 V2 descriptor acceptance", "D96 row decode",
                             "Q/K/V row replay including dimensions 64 through 95"],
        "coverage_note": "source-level targets, not claimed unhit DVE point IDs"
    }
    (HERE / "akv_d96_gap29_ready.json").write_text(json.dumps(ready, indent=2) + "\n")
    print(f"READY: {elf}; host reference PASS; no RTL launched")


if __name__ == "__main__":
    main()
