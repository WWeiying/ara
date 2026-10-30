#!/usr/bin/env python3
"""Host preflight tests and GNU RV64GCV object/disassembly checks; no simulator."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gcc", type=Path, default=Path(
        "/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc"))
    args = parser.parse_args()
    out = args.output.resolve()
    gcc = args.gcc.resolve(strict=True)
    if not gcc.name.endswith("gcc") or "zcc" in str(gcc).lower():
        raise ValueError("GNU toolchain required")
    objdump = gcc.with_name(gcc.name.removesuffix("gcc") + "objdump")
    host = Path(shutil.which("gcc"))
    sources = [HERE / name for name in (
        "panel.S", "vrf_panel.c", "vrf_panel.h", "test_preflight.c", "build.py", "README.md")]
    sources += [ROOT / "software/qbs/include/qbs/qbs_abi.h"]
    before = {str(p): sha(p) for p in sources}
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(argv, name):
        argv = list(map(str, argv))
        commands.append(argv)
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        with (out / (name + ".log")).open("x") as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
        return (out / (name + ".log")).read_text()

    (out / "sources-before.json").write_text(json.dumps(before, indent=2) + "\n")
    run([gcc, "--version"], "gnu-version")
    run([host, "--version"], "host-version")
    common = ["-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
              "-DNDEBUG", "-I", ROOT / "software/qbs/include"]
    run([host, *common, HERE / "vrf_panel.c", HERE / "test_preflight.c",
         "-o", out / "preflight"], "host-build")
    log = run([out / "preflight"], "host-test")
    if log != "QBS_VRF_PANEL_PREFLIGHT_PASS cases=2130\n":
        raise ValueError("unexpected preflight output/count")
    arch = ["-march=rv64gcv", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax",
            "-ffreestanding", "-fno-builtin", "-fno-tree-vectorize",
            "-fno-tree-loop-distribute-patterns", "-fno-fast-math", "-ffp-contract=off"]
    run([gcc, *common, *arch, "-c", HERE / "vrf_panel.c", "-o", out / "wrapper.o"],
        "wrapper-build")
    run([gcc, *arch, "-c", HERE / "panel.S", "-o", out / "panel.o"], "assembly-build")
    run([gcc, *arch, "-nostdlib", "-r", out / "wrapper.o", out / "panel.o",
         "-o", out / "vrf_panel.o"], "relocatable-link")
    dis = run([objdump, "-dr", out / "panel.o"], "assembly-disassembly")
    wrapper = run([objdump, "-dr", out / "wrapper.o"], "wrapper-disassembly")
    functions = re.findall(r"^[0-9a-f]+ <((?:panel_run|qbs_vrf_panel_)[^>]*)>:",
                           wrapper, re.MULTILINE)
    if sorted(functions) != ["panel_run", "qbs_vrf_panel_direct_run", "qbs_vrf_panel_run"]:
        raise ValueError("expected one shared core and two API adapters, no clones")
    if len(re.findall(r"R_RISCV_CALL_PLT\s+qbs_vrf_panel_asm\b", wrapper)) != 1:
        raise ValueError("expected one shared assembly call site")
    for name in ("qbs_vrf_panel_run", "qbs_vrf_panel_direct_run"):
        adapter = wrapper.split("<" + name + ">:", 1)[1]
        adapter = re.split(r"\n[0-9a-f]+ <[^>]+>:", adapter)[0]
        tail_relocations = re.findall(r"R_RISCV_CALL_PLT\s+(\S+)", adapter)
        if tail_relocations != ["panel_run"] or not re.search(r"\bjr\s+t1\b", adapter) or \
                re.search(r"\b(?:sp|call|jal|jalr)\b", adapter):
            raise ValueError("API adapter is not a stackless tail jump to shared core")
    run([objdump, "-dr", out / "vrf_panel.o"], "combined-disassembly")
    leaf = dis.split("<qbs_vrf_panel_asm>:", 1)[1].split("<qbs_vrf_panel_info>:", 1)[0]
    for word in ("06b5045b", "06b5085b", "16b5045b", "16b5085b"):
        if len(re.findall(r"\b" + word + r"\b", leaf)) != 1:
            raise ValueError("wrong custom instruction encoding/count: " + word)
    stores = re.findall(r"\bvse32\.v\s+v(\d+),", leaf)
    if stores != ["8", "9", "10", "11", "16", "17", "18", "19"]:
        raise ValueError("wrong final store sequence")
    if len(re.findall(r"\bfence\s+rw,rw", leaf)) != 2 or "vmv.x.s" not in leaf:
        raise ValueError("missing setup/store drain")
    if len(re.findall(r"\bvsetvli\b", leaf)) != 3:
        raise ValueError("unexpected vector configuration count")
    if re.search(r"\b(?:s(?:[0-9]|10|11)|sp|call|jal|jalr|fadd\.[sd]|v[f]?add\.[a-z]+)\b", leaf):
        raise ValueError("leaf contains calls, callee-saved accesses or arithmetic reduction")
    after = {str(p): sha(p) for p in sources}
    (out / "sources-after.json").write_text(json.dumps(after, indent=2) + "\n")
    if before != after:
        raise ValueError("source drift")
    artifacts = {str(out / name): sha(out / name) for name in
                 ("preflight", "wrapper.o", "panel.o", "vrf_panel.o")}
    (out / "result.json").write_text(json.dumps({
        "status": "PASS", "preflight_cases": 2130, "execution": "host mocks only",
        "sources": after, "artifacts": artifacts,
        "tools": {str(gcc): sha(gcc), str(objdump): sha(objdump)},
    }, indent=2) + "\n")
    print(f"QBS_VRF_PANEL_BUILD_PASS output={out}")


if __name__ == "__main__":
    main()
