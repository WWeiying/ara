#!/usr/bin/env python3
"""Re-run the scalar MMU case with its independent path oracle, not vector UVM."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification"))
from uvm.run_upstream_smoke_20261009 import digest, run, save
from ara_verify.dependency_patches import load_registry, patch_state
from cva6.check_linux_relocate import audit, parse_dump, require

def check_fetch(text, symbols):
    ends = re.findall(r"^\[IFETCH_PAYLOAD_END\] normal=(\d+) exceptions=(\d+) unknown=(\d+) legacy_warnings=(\d+) errors=(\d+)$", text, re.M)
    require(len(ends) == 1, "missing/duplicate fetch-probe final summary")
    normal, exceptions, unknown, warnings, errors = map(int, ends[0])
    require(normal > 0 and exceptions > 0 and errors == 0, "invalid fetch-probe totals")
    rows = re.findall(r"^\[IFETCH_PAYLOAD\] cycle=(\d+) va=([0-9a-f]+) ex=([01xz]) cause=([0-9a-fxz]+) tval=([0-9a-fxz]+) unknown=([01]) legacy_warning=([01])$", text, re.M)
    require(len(rows) == exceptions, "unexpected unknown normal fetch or incomplete exception trace")
    require(sum(int(r[5]) for r in rows) == unknown and sum(int(r[6]) for r in rows) == warnings,
            "fetch trace/summary mismatch")
    for _, va, ex, cause, tval, _, _ in rows:
        require(ex == "1" and int(cause, 16) == 12, "fetch response is not an instruction page fault")
        # The 32-bit fetch windows can include the next word of the faulting instruction.
        require(int(va, 16) in (symbols["linux_virtual_entry"], symbols["linux_virtual_entry"] + 4),
                "unexpected faulting fetch address")
        require(int(tval, 16) == int(va, 16), "fetch exception address mismatch")
    require(text.count("[l1 dcache] reading invalid instructions:") == warnings,
            "legacy warnings not fully accounted for by exception responses")
    return dict(normal_responses=normal, exception_responses=exceptions,
                unknown_payloads=unknown, explained_legacy_warnings=warnings, errors=errors)


def audit_result(run_dir, dump):
    test = run_dir / "tests/rvv_linux_mmu_relocate"
    inputs = json.loads((test / "inputs.json").read_text())
    require(all(digest(Path(p)) == sha for p, sha in inputs["simv"]["image_sha256"].items()),
            "simulation image changed")
    result = audit(run_dir, dump)
    symbols, _ = parse_dump(dump.read_text())
    result["fetch_payload"] = check_fetch((test / "console.log").read_text(), symbols)
    result["run_directory"] = str(run_dir)
    evidence = [run_dir / "summary.json", test / "inputs.json", test / "input.elf",
                test / "console.log", test / "commit_trace.csv", dump,
                *sorted((test / "work").glob("state_prereq.*.log"))]
    result["evidence_sha256"] = {str(p): digest(p) for p in evidence}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-run", type=Path,
                        help="audit an existing completed scalar run without re-simulation")
    parser.add_argument("--dump", type=Path, default=ROOT / "apps/bin/rv64uv-ara-linux_mmu_relocate.dump")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(status="PREFLIGHT", started=time.time())
    try:
        # apps/bin ELFs are stripped after the build emits their symbol-bearing dump.
        # Freeze that dump; the independent oracle checks every .text encoding vs ELF.
        dump = out / "input.dump"
        shutil.copy2(args.dump, dump)
        parse_dump(dump.read_text())
        if args.audit_run:
            result = audit_result(args.audit_run.resolve(), dump)
            result["audit_script_sha256"] = digest(Path(__file__))
            save(out / "host_audit.json", result)
            state.update(status="PASS", result=result)
            return 0
        registry = load_registry(ROOT)
        for name in ("cva6", "fpnew", "axi"):
            require(patch_state(ROOT, name, ROOT / "hardware/deps" / name,
                                registry[name]["revision"]) == "applied", "dependency drift: " + name)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "verification")
        extras = [ROOT / "verification/uvm" / n for n in (
            "cva6_state_prereq_probe.sv", "sv39_prereq_probe.sv", "trap_prereq_probe.sv",
            "ifetch_payload_probe.sv")]
        elf = ROOT / "apps/bin/rv64uv-ara-linux_mmu_relocate"
        pins = {str(p): digest(p) for p in [elf, dump, Path(__file__),
                ROOT / "verification/cva6/check_linux_relocate.py", *extras]}
        save(out / "input_pins.json", pins)
        command = ["make", "-C", str(ROOT / "hardware"), "compile", "config=default",
                   "nr_lanes=4", "vlen=1024", "qbs=1", "akv=1", "akv_v2=1",
                   "sim_l2_mb=2", "mc=0", "code_coverage=0", "fail_on_assert=1",
                   "store_b_ab_baseline=0", "no_fsdb=1", "verify_axi_delay=1",
                   "verify_uvm_cvxif=0", "verify_source_manifest=1",
                   f"buildpath={out}/build", f"sim_dir={out}/sim",
                   "verify_extra_sources=" + " ".join(map(str, extras))]
        save(out / "compile_command.json", command)
        state["status"] = "BUILDING"
        save(out / "status.json", state)
        require(run(command, ROOT, out / "compile.log", env, 1800) == 0, "compile failed")
        state["status"] = "RUNNING"
        save(out / "status.json", state)
        command = [sys.executable, str(ROOT / "verification/verify.py"), "run",
                   "linux-mmu-relocate", "--simv", str(out / "sim/simv"), "--skip-build",
                   "--commit-trace", "--timeout", "300", "--output", str(out / "run")]
        for kind in ("csr", "trap_ctrl", "mmu", "ptw"):
            command.extend(["--probe-kind", kind])
        require(run(command, ROOT, out / "run.log", env, 360) == 0, "scalar VCS runner failed")
        frozen = out / "run/tests/rvv_linux_mmu_relocate/input.elf"
        require(digest(frozen) == pins[str(elf)], "ELF changed before snapshot")
        result = audit_result(out / "run", dump)
        require(all(digest(Path(p)) == sha for p, sha in pins.items()), "inputs changed during run")
        save(out / "host_audit.json", result)
        state.update(status="PASS", result=result)
    except Exception as error:
        state.update(status="FAIL", reason=f"{type(error).__name__}: {error}")
    finally:
        state["finished"] = time.time()
        save(out / "status.json", state)
        print(json.dumps(state), flush=True)
    return 0 if state["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
