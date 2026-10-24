#!/usr/bin/env python3
"""Bounded host GCC / package-only VCS tests. All outputs are private."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ABI_FILES = ("config/qbs_abi.json", "scripts/gen_qbs_abi.py",
             "hardware/include/qbs_pkg.sv", "apps/common/qbs_abi.h",
             "software/qbs/include/qbs/qbs_abi.h")
VLENS = (0, 32, 128, 512, 1023, 1024, 1025, 2048, 4096)
C_PASS = "QBACC_ABI_C_PASS encodings=262144 capabilities=2304"
SV_PASS = "QBACC_ABI_SV_PASS encodings=262144 capabilities=2304"


def check_c(log):
    lines = log.splitlines()
    keys = [(v, i) for v in VLENS for i in range(256) if i != 4]
    if len(lines) != len(keys) + 1 or lines[-1] != C_PASS:
        raise ValueError("C output length/terminal marker")
    result = []
    for line, (v, i) in zip(lines[:-1], keys):
        match = re.fullmatch(r"CAP vlen=(\d+) index=(\d+) word=([0-9a-f]{16})", line)
        if match is None or (int(match[1]), int(match[2])) != (v, i):
            raise ValueError("C capability fields/order")
        result.append(int(match[3], 16))
    return result


def check_sv(log):
    markers = [line for line in log.splitlines() if "QBACC_ABI" in line]
    if markers != [SV_PASS]:
        raise ValueError("SV exact PASS marker/count")
    if re.search(r"(?im)\b(?:error|fatal|fail(?:ed)?|unknown)\b", log):
        raise ValueError("SV error diagnostics")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path, required=True,
                        help="Pre-change source copy preserving repository paths")
    args = parser.parse_args()
    out = args.output.resolve()
    baseline = args.baseline_dir.resolve()
    # Validate all inputs before creating output. Existing outputs are never reused.
    sources = [ROOT / name for name in ABI_FILES]
    sources += [ROOT / "verification/qbs/qbs_ref.c", ROOT / "verification/qbs/qbs_ref.h"]
    sources += sorted(HERE.glob("*.py")) + [HERE / "test.c", HERE / "test.sv", HERE / "README.md"]
    sources += [baseline / name for name in ABI_FILES]
    before = {str(path): digest(path) for path in sources}
    gcc, vcs = shutil.which("gcc"), shutil.which("vcs")
    if not gcc or not vcs:
        raise RuntimeError("host gcc and VCS required")
    out.mkdir(parents=True, exist_ok=False)
    commands = []
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CCACHE_DISABLE="1")

    def run(command, name, cwd=out, timeout=300):
        command = [str(item) for item in command]
        commands.append({"argv": command, "cwd": str(cwd), "timeout_s": timeout})
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        with (out / (name + ".log")).open("w") as log:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"{name} exited {result.returncode}; see log")
        return (out / (name + ".log")).read_text()

    (out / "sources-before.json").write_text(json.dumps(before, indent=2) + "\n")
    run([sys.executable, ROOT / "scripts/gen_qbs_abi.py", "--check"], "generated-check")
    run([sys.executable, "-m", "unittest", "discover", "-s", HERE,
         "-p", "test_*.py", "-v"], "unit-tests")
    run([gcc, "--version"], "gcc-version")
    reference = ROOT / "verification/qbs/qbs_ref.c"
    variants = [("baseline", baseline / "apps/common/qbs_abi.h", ["-DTEST_BASELINE"])]
    for header_name, relative in (("apps", "apps/common/qbs_abi.h"),
                                  ("runtime", "software/qbs/include/qbs/qbs_abi.h")):
        for enabled in (False, True):
            name = f"{header_name}-{'enabled' if enabled else 'default'}"
            flags = ["-DARA_QBS_VRF_CONTINUATION"] if enabled else []
            variants.append((name, ROOT / relative, flags))
    baseline_caps = None
    artifacts = {}
    for name, header, defines in variants:
        binary = out / (name + ".elf")
        run([gcc, "-std=c11", "-O2", "-DNDEBUG", "-Wall", "-Wextra", "-Werror",
             "-pedantic", "-ffp-contract=off", "-frounding-math",
             "-I", header.parent, "-I", reference.parent,
             # Force the selected header in both TUs, including qbs_ref.c whose
             # header otherwise uses a fixed relative apps/common include.
             "-include", header, *defines, HERE / "test.c", reference,
             "-lm", "-o", binary], name + "-build")
        caps = check_c(run([binary], name + "-run", timeout=30))
        if baseline_caps is None:
            baseline_caps = caps
        elif caps != baseline_caps:
            raise ValueError(f"{name}: existing capability words changed")
        artifacts[str(binary)] = digest(binary)

    # Only rename the archived package namespace so both revisions coexist.
    old_pkg = (baseline / "hardware/include/qbs_pkg.sv").read_text()
    if old_pkg.count("package qbs_pkg;") != 1 or old_pkg.count("endpackage : qbs_pkg") != 1:
        raise ValueError("baseline SV package boundaries")
    renamed = old_pkg.replace("package qbs_pkg;", "package qbacc_legacy_pkg;").replace(
        "endpackage : qbs_pkg", "endpackage : qbacc_legacy_pkg")
    legacy_pkg = out / "qbacc_legacy_pkg.sv"
    legacy_pkg.write_text(renamed)
    for qbs in (False, True):
        for continuation in (False, True):
            name = f"sv-qbs{int(qbs)}-continuation{int(continuation)}"
            build = out / name
            build.mkdir()
            flags = []
            if qbs:
                flags.append("+define+ARA_QBS_ENABLE")
            if continuation:
                flags.append("+define+ARA_QBS_VRF_CONTINUATION")
            log = run([vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                       *flags, legacy_pkg, ROOT / "hardware/include/qbs_pkg.sv",
                       HERE / "test.sv", "-top", "qbacc_abi_tb", "-o", build / "simv"],
                      name + "-build", cwd=build)
            if re.search(r"(?im)^\s*(?:Error|Fatal)(?:\b|\[)", log):
                raise ValueError(f"{name}: compile errors")
            check_sv(run([build / "simv"], name + "-run", cwd=build, timeout=30))
            artifacts[str(build / "simv")] = digest(build / "simv")
    after = {str(path): digest(path) for path in sources}
    (out / "sources-after.json").write_text(json.dumps(after, indent=2) + "\n")
    if before != after:
        raise RuntimeError("source drift during ABI gate")
    (out / "result.json").write_text(json.dumps({
        "status": "PASS", "c_variants": 5, "sv_variants": 4,
        "encodings_per_variant": 262144, "capabilities_per_variant": 2304,
        "artifacts": artifacts, "sources": after,
    }, indent=2) + "\n")
    print(f"QBACC_ABI_SUITE_PASS output={out}")


if __name__ == "__main__":
    main()
