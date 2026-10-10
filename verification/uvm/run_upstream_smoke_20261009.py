#!/usr/bin/env python3
"""Build one pinned current VCS image and run bounded integration self-checks."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification"))
from ara_verify.dependency_patches import load_registry, patch_state

CASES = (
    "rv64uv-ara-vsmul", "rv64uv-ara-vfncvt", "rv64uv-ara-vfcvt",
    "rv64uv-ara-vfmacc", "rv64uv-ara-vfdiv", "rv64uv-ara-linux_mmu_relocate",
    "vsaxpy_asm", "qbs_control_smoke", "akv_context_smoke", "qbs_akv_handoff_smoke",
)
SCALAR_CASE = "rv64uv-ara-linux_mmu_relocate"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def run(command, cwd, log, env, timeout):
    with log.open("w") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            return 124


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=5, choices=range(1, 9))
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = {"status": "PREFLIGHT", "pid": os.getpid(), "started": time.time(),
             "cases": {}, "scope": "program self-checks and real-boundary protocol monitors; no code coverage"}
    try:
        registry = load_registry(ROOT)
        for name in ("cva6", "fpnew", "axi"):
            if patch_state(ROOT, name, ROOT / "hardware/deps" / name,
                           registry[name]["revision"]) != "applied":
                raise RuntimeError("unregistered dependency: " + name)
        frozen = out / "elf"
        frozen.mkdir()
        pins = {}
        for case in CASES:
            source = ROOT / "apps/bin" / case
            shutil.copy2(source, frozen / case)
            pins[case] = {"source": str(source), "sha256": digest(frozen / case)}
        helper = ROOT / "verification/uvm/run_real_dut_case.sh"
        save(out / "input_pins.json", {"elf": pins, "helper_sha256": digest(helper),
             "registry_sha256": digest(ROOT / "verification/patches/dependencies.json"),
             "worker_sha256": digest(Path(__file__))})
        env = os.environ.copy()
        env.update(PYTHONPATH=str(ROOT / "verification"), ARA_VCS_TIMEOUT_SECONDS="300")
        extra = " ".join(str(ROOT / "verification/uvm" / name) for name in (
            "ara_cvxif_if.sv", "ara_cvxif_uvm_pkg.sv", "ara_acc_contract_monitor.sv",
            "ara_cvxif_dut_bind.sv"))
        command = ["make", "-C", str(ROOT / "hardware"), "compile", "config=default",
                   "nr_lanes=4", "vlen=1024", "qbs=1", "akv=1", "akv_v2=1",
                   "sim_l2_mb=2", "mc=0", "code_coverage=0", "fail_on_assert=1",
                   "store_b_ab_baseline=0", "no_fsdb=1", "verify_axi_delay=1",
                   "verify_uvm_cvxif=1", "verify_source_manifest=1",
                   f"buildpath={out}/build", f"sim_dir={out}/sim",
                   "verify_extra_sources=" + extra]
        save(out / "compile_command.json", command)
        state["status"] = "BUILDING"
        save(out / "status.json", state)
        rc = run(command, ROOT, out / "compile.log", env, 1800)
        if rc:
            raise RuntimeError(f"compile exit={rc}")
        state["status"] = "RUNNING"
        save(out / "status.json", state)

        def case_run(case):
            target = out / "tests" / case
            if case == SCALAR_CASE:
                # A scalar MMU program cannot satisfy vector traffic requirements.
                # Its stronger oracle checks SATP/traps/retired PCs and remapped memory.
                helper_scalar = ROOT / "verification/cva6/run_upstream_relocate_20261009.py"
                python = ROOT / "verification/tools/soc-venv/bin/python"
                started = time.time()
                rc = run([str(python), str(helper_scalar), "--output", str(target)],
                         ROOT, out / f"{case}.log", env, 2400)
                receipt = target / "host_audit.json"
                result = json.loads(receipt.read_text()) if receipt.is_file() else None
                passed = (rc == 0 and result and result.get("status") == "PASS" and
                          result.get("binary_sha256") == pins[case]["sha256"])
                return case, {"exit": rc, "seconds": time.time() - started,
                              "status": "PASS" if passed else "FAIL",
                              "receipt": str(receipt), "result": result}
            command = ["bash", str(helper), str(out / "sim/simv"),
                       str(frozen / case), case, str(target)]
            started = time.time()
            rc = run(command, ROOT, out / f"{case}.log", env, 360)
            receipt = target / "uvm_result.json"
            result = json.loads(receipt.read_text()) if receipt.is_file() else None
            return case, {"exit": rc, "seconds": time.time() - started,
                          "status": "PASS" if rc == 0 and result and result.get("status") == "PASS" else "FAIL",
                          "receipt": str(receipt), "result": result}

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(case_run, name) for name in CASES]
            for future in as_completed(futures):
                name, result = future.result()
                state["cases"][name] = result
                save(out / "status.json", state)
        state["status"] = "PASS" if all(r["status"] == "PASS" for r in state["cases"].values()) else "FAIL"
    except Exception as error:
        state.update(status="ERROR", reason=f"{type(error).__name__}: {error}")
    finally:
        state["finished"] = time.time()
        save(out / "status.json", state)
        print(json.dumps({"status": state["status"], "output": str(out)}), flush=True)
    return 0 if state["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
