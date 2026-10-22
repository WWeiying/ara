#!/usr/bin/env python3
"""One fresh compile/run of the actual CVA6 dispatcher, isolated and bounded."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from ara_verify.dependency_patches import load_registry, patch_state
from cva6.checker import ERROR_PATTERN, check_evidence
from cva6.stimulus import render, schedule

CORE = "hardware/deps/cva6/core/"
COMMON = "hardware/deps/common_cells/"
SOURCES = (
    COMMON + "src/cf_math_pkg.sv",
    CORE + "include/config_pkg.sv",
    CORE + "include/cv64a6_imafdcv_sv39_config_pkg.sv",
    CORE + "include/riscv_pkg.sv",
    CORE + "include/ariane_pkg.sv",
    CORE + "include/build_config_pkg.sv",
    "hardware/deps/fpnew/src/fpnew_pkg.sv",
    COMMON + "src/delta_counter.sv", COMMON + "src/counter.sv",
    COMMON + "src/spill_register_flushable.sv", COMMON + "src/spill_register.sv",
    CORE + "cva6_fifo_v3.sv", CORE + "acc_dispatcher.sv",
    "verification/cva6/acc_dispatcher_contract_tb.sv",
)
EXTRA = (
    CORE + "cva6.sv", COMMON + "include/common_cells/registers.svh",
    COMMON + "include/common_cells/assertions.svh", "hardware/include/ara/intf_typedef.svh",
    "verification/patches/dependencies.json", "verification/patches/cva6-local-fixes.patch",
    "verification/cva6/README.md", "verification/cva6/run_contract.py",
    "verification/cva6/checker.py", "verification/cva6/stimulus.py",
)
TYPE_NAMES = ("branchpredict_sbe_t", "exception_t", "scoreboard_entry_t", "fu_data_t",
              "dcache_req_i_t", "dcache_req_o_t")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def extract_types(source):
    # CVA6 defines these as flat parameter structs, not exported package types.
    result = ["// Generated verbatim from frozen cva6.sv; Solderpad Hardware License 0.51."]
    for name in TYPE_NAMES:
        pattern = (r"(?:localparam|parameter)\s+type\s+" + name +
                   r"\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*,")
        matches = re.findall(pattern, source)
        if len(matches) != 1:
            raise ValueError(f"cannot unambiguously extract actual packed type {name}")
        result.append(f"typedef {matches[0]} {name};")
    return "\n".join(result) + "\n"


def validate_output(path):
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("output must not traverse symlinks")
    if not path.resolve().is_relative_to(ROOT / "verification/out") or path == ROOT / "verification/out":
        raise ValueError("output must be a new directory under verification/out in this worktree")
    if path.exists():
        raise ValueError("output exists; refusing stale evidence or overwrite")
    return path


def execute(argv, directory, timeout):
    directory.mkdir()
    record = {"argv": list(map(str, argv)), "cwd": str(directory), "timeout_s": timeout,
              "started_at": datetime.now(timezone.utc).isoformat()}
    save(directory / "command.json", record)
    start = time.monotonic()
    with (directory / "console.log").open("wb") as log:
        process = subprocess.Popen(record["argv"], cwd=directory, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            record["returncode"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            record["returncode"] = -1
            record["timeout"] = True
        finally:
            # Clean descendants as well, even if the driver has already exited.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            process.wait()
    record["elapsed_s"] = time.monotonic() - start
    record["log_sha256"] = digest((directory / "console.log").read_bytes())
    save(directory / "result.json", record)
    return record


def run(output):
    output = validate_output(output)
    spec = load_registry(ROOT)["cva6"]
    if patch_state(ROOT, "cva6", ROOT / "hardware/deps/cva6", spec["revision"]) != "applied":
        raise ValueError("requires the reviewed, applied CVA6 patch")
    vcs = shutil.which("vcs")
    if not vcs:
        raise ValueError("VCS not found")
    output.mkdir(parents=True)
    inputs = output / "inputs"
    records = {}
    for name in SOURCES + EXTRA:
        original = ROOT / name
        if any(p.is_symlink() for p in (original, *original.parents)):
            raise ValueError(f"linked input: {name}")
        if not original.resolve().is_relative_to(ROOT):
            raise ValueError(f"input outside verification worktree: {name}")
        content = original.read_bytes()
        target = inputs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        records[name] = digest(content)
    generated = inputs / "generated"
    generated.mkdir()
    (generated / "contract_types.svh").write_text(extract_types((inputs / CORE / "cva6.sv").read_text()))
    planned = schedule()
    (generated / "stimulus.txt").write_text(render(planned))
    save(generated / "stimulus.json", planned)
    manifest = {"scope": "actual acc_dispatcher directed unit contract only", "patch": spec,
                "sources": records, "cycles_planned": len(planned),
                "generated": {p.name: digest(p.read_bytes()) for p in generated.iterdir()},
                "compile_count": 1, "run_count": 1}
    save(output / "manifest.json", manifest)
    build = output / "build"
    command = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-assert", "svaext",
               "+define+ARIANE_ACCELERATOR_PORT=1", "-top", "acc_dispatcher_contract_tb",
               "-o", str(build / "simv"), "-Mdir=" + str(build / "csrc")]
    for name in (COMMON + "include", "hardware/include", CORE + "include", "generated"):
        command.append("+incdir+" + str(inputs / name))
    command += [str(inputs / name) for name in SOURCES]
    compiled = execute(command, build, 180)
    if compiled["returncode"] or ERROR_PATTERN.search((build / "console.log").read_text()):
        raise ValueError("VCS compilation failed; see build/console.log")
    simulation = output / "run"
    executed = execute([build / "simv", "+STIMULUS=" + str(generated / "stimulus.txt")], simulation, 30)
    report = check_evidence((simulation / "console.log").read_text(),
                            (simulation / "trace.jsonl").read_text(),
                            json.loads((simulation / "config.json").read_text()),
                            returncode=executed["returncode"], expected_stimulus=planned)
    if any(digest((ROOT / name).read_bytes()) != sha for name, sha in records.items()):
        raise ValueError("source changed during isolated run")
    report.update(compile_seconds=compiled["elapsed_s"], run_seconds=executed["elapsed_s"],
                  manifest_sha256=digest((output / "manifest.json").read_bytes()))
    save(output / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("timeline", "transactions")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.output)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"CVA6_CONTRACT_FAIL: {error}", file=sys.stderr)
        # Never overwrite a previous run when preflight rejected an existing path.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
