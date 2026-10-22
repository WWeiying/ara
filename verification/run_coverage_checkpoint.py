#!/usr/bin/env python3
"""Bounded VCS/Spike gate, then same-checkpoint Verilator coverage replay.

Run under a dedicated systemd service with KillMode=control-group. Any failed
step exits the service, including failures of the fail-fast child supervisor.
No RTL is modified and no failed test is retried automatically.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from ara_verify.artifacts import sha256, simulation_image
from ara_verify.rvv_replay import failed_random_cases

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
VERIFY = [PYTHON, str(ROOT / "verification/verify.py")]
SPIKE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike")


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def checked_output(path):
    output = path.resolve()
    base = (ROOT / "verification/out").resolve()
    if output == base or not output.is_relative_to(base):
        raise ValueError("output must be beneath ROOT/verification/out")
    return output


def stop(output, phase, error):
    path = output / "checkpoint.json"
    try:
        checkpoint = json.loads(path.read_text())
        if not isinstance(checkpoint, dict):
            checkpoint = {}
    except (OSError, ValueError):
        checkpoint = {}
    checkpoint.update(status="STOPPED", phase=phase,
                      reason=f"{type(error).__name__}: {error}",
                      policy="waiting for user instructions; no automatic repair")
    save(path, checkpoint)


def check_service():
    unit = os.environ.get("ARA_CHECKPOINT_UNIT", "")
    invocation = os.environ.get("INVOCATION_ID", "")
    if not unit.endswith(".service") or unit.startswith("-") or not invocation:
        raise RuntimeError("ARA_CHECKPOINT_UNIT and INVOCATION_ID must identify the driver service")
    expected = {"KillMode": "control-group", "Restart": "no", "RemainAfterExit": "no",
                "MainPID": str(os.getpid()), "InvocationID": invocation}
    result = subprocess.run(
        ["systemctl", "--user", "show", unit, "--no-pager",
         *[f"--property={key}" for key in expected]],
        check=True, capture_output=True, text=True, timeout=10)
    actual = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if any(actual.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"unsafe or mismatched systemd service: {actual}")


def image_identity(path):
    if not os.access(path, os.X_OK) or not Path(str(path) + ".daidir").is_dir():
        raise RuntimeError(f"missing executable or runtime database: {path}")
    return simulation_image(path)


def pin_inputs(output, images, files, checkpoint):
    save(output / "prepared-inputs.json", {
        "schema_version": 1,
        "images": {str(path): image_identity(path) for path in images},
        "files": {str(path): sha256(path) for path in sorted(set(files))},
        "checkpoint": checkpoint,
    })


def check_inputs(output):
    saved = json.loads((output / "prepared-inputs.json").read_text())
    if saved["schema_version"] != 1 or not saved["images"] or not saved["files"]:
        raise ValueError("invalid prepared input manifest")
    for path, expected in saved["images"].items():
        if image_identity(Path(path)) != expected:
            raise RuntimeError(f"prepared image changed: {path}")
    for path, expected in saved["files"].items():
        if sha256(Path(path)) != expected:
            raise RuntimeError(f"prepared input changed: {path}")
    checkpoint = json.loads((output / "checkpoint.json").read_text())
    for key, expected in saved["checkpoint"].items():
        if key != "status" and checkpoint.get(key) != expected:
            raise RuntimeError(f"prepared checkpoint field changed: {key}")


def check_coverage_image(output):
    record = json.loads((output / "coverage-image.json").read_text())
    if simulation_image(Path(record["path"])) != record["image_sha256"]:
        raise RuntimeError("coverage image changed after build")


def run(command):
    print(json.dumps([str(x) for x in command]), flush=True)
    subprocess.run([str(x) for x in command], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--steps", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--execute-prepared", action="store_true")
    args = parser.parse_args()
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.steps:
        output = checked_output(args.steps.resolve().parent.parent)
        check_inputs(output)
        if args.steps.name.startswith("coverage-") and args.steps.name != "coverage-build.json":
            check_coverage_image(output)
        for command in json.loads(args.steps.read_text()):
            run(command)
        return
    if not args.output:
        parser.error("--output is required")
    output = checked_output(args.output)
    if args.execute_prepared:
        execute(output)
        return
    output.mkdir(parents=True, exist_ok=False)
    try:
        prepare(output)
    except Exception as error:
        stop(output, "prepare", error)
        raise
    if not args.prepare_only:
        execute(output)


def prepare(output):
    simdir = ROOT / "verification/out/merged-store-fp16-image-20260926-01/sim"
    simv = simdir / "simv"
    check = [PYTHON, "-m", "ara_verify.vcs_source_manifest", "--output",
             str(simdir / "vcs_source_manifest.json"), "--check"]
    run(check)
    spike = SPIKE
    generator = ROOT / "verification/out/integrated-random-short-control-preflight-20260925-01/vcs_simv"
    for binary in (simv, spike, generator):
        if not os.access(binary, os.X_OK):
            raise RuntimeError(f"missing executable: {binary}")
    build = ROOT / "verification/out/integrated-verilator-coverage-20260925-01/build"
    covdir = build / "verilator"
    covsim = covdir / "Vara_tb_verilator"
    provenance = output / "coverage-source.json"
    # Preserve the previous executable before incrementally rebuilding in place.
    if covsim.exists():
        shutil.copy2(covsim, output / "previous-coverage-image")
    make = ["make", "-C", str(ROOT / "hardware"), f"buildpath={build}",
            "qbs=1", "akv=1", "akv_v2=1", "sim_l2_mb=2", "veril_coverage=1",
            "veril_cxx_opt=-O3", "veril_jobs=12", "veril_clean=0"]
    capture = [PYTHON, str(ROOT / "verification/coverage/build_provenance.py"),
               "--filelist", str(covdir / "bender_script_default"),
               "--repo-root", str(ROOT), "--build-dir", str(covdir),
               "--output", str(provenance)]
    jobs = []
    coverage_jobs = []
    pinned_files = [spike, simdir / "vcs_source_manifest.json",
                    simdir / "simulator.conf", Path(__file__).resolve(),
                    ROOT / "verification/riscv_dv/testlist.yaml"]

    def job(target, name, steps):
        path = output / "steps" / f"{name}.json"
        save(path, steps)
        pinned_files.append(path)
        target.append({"name": name, "cwd": str(ROOT),
                       "command": [PYTHON, str(Path(__file__).resolve()), "--steps", str(path)]})

    job(jobs, "coverage-build", [make + ["verilate_prepare"], capture,
                                 make + ["verilate"],
                                 [PYTHON, "verification/coverage/build_provenance.py",
                                  "--output", str(provenance), "--check"]])
    common = ["--simv", str(simv), "--spike", str(spike),
              "--spike-isa", "rv64gcv_zvfh_zvl1024b", "--timeout", "1800",
              "--spike-timeout", "120", "--watchdog-cycles", "250000"]
    selected = []

    def case(name, command, random, collect):
        result = output / "functional" / name
        audit = result / "independent_audit.json"
        audit_command = VERIFY + ["audit", "--run", str(result), "--require-trace",
                                  "--output", str(audit)]
        if random:
            audit_command += ["--require-vector", "--require-full-match"]
        job(jobs, name, [check, command + ["--output", str(result)], audit_command, check])
        if collect:
            selected.append(name)
            replay = [PYTHON, "verification/coverage/run_directed_coverage.py",
                      "--summary", str(result / "summary.json"), "--audit", str(audit),
                      "--simv", str(covsim), "--source-manifest", str(provenance),
                      "--ram-bytes", "2097152", "--jobs", "1", "--term-cycles", "250000",
                      "--timeout", "3600", "--output", str(output / "coverage" / name)]
            if random:
                replay += ["--random-source"]
            job(coverage_jobs, "coverage-" + name, [replay])

    # Interleave control and memory seeds so all initial slots cover both paths.
    for seed in range(501, 511):
        for kind in ("control", "memory"):
            name = f"short-{kind}-{seed}"
            command = VERIFY + ["run-rvv", "--test", f"ara_dsa_rvv1_short_{kind}_cross",
                                "--iterations", "1", "--seed", str(seed), "--simulator", "vcs",
                                "--generator-simv", str(generator), "--vector-signature",
                                "--defined-scalar-sources", "--vector-commit-compare"] + common
            case(name, command, True, seed in (501, 502))
    for label, source in (
        ("arithmetic", "integrated-wred-m8-arithmetic10-replay-20260925-02"),
        ("loadstore", "integrated-wred-m8-loadstore10-replay-20260925-01"),
        ("fp32", "integrated-wred-m8-fp32-10-replay-20260925-01"),
        ("fp64", "integrated-wred-m8-fp64-10-replay-20260925-01"),
        ("vtype", "integrated-wred-m8-vtype10-replay-20260925-01"),
    ):
        summary = ROOT / "verification/out" / source / "summary.json"
        first = json.loads(summary.read_text())[0]["name"]
        pinned_files.append(summary)
        pinned_files.extend(item.elf for item in failed_random_cases(
            summary, [first], include_passed=True))
        case("replay-" + label, VERIFY + ["replay-failed-rvv", "--summary", str(summary),
             "--case", first, "--include-passed", "--jobs", "1"] + common, True, True)
    for name in ("villegal_vstart_ops", "vmask_dest_overlap_illegal", "vregister_group_illegal",
                 "vwiden_overlap_edges", "vnclip_edges"):
        pinned_files.append(ROOT / "apps/bin" / f"rv64uv-ara-{name}")
        case(name, VERIFY + ["run", "--test", "rvv:" + name, "--simv", str(simv),
             "--skip-build", "--commit-trace", "--jobs", "1", "--timeout", "900"], False, True)
    save(output / "functional-plan.json", jobs)
    save(output / "coverage-plan.json", coverage_jobs)
    checkpoint = {"status": "PREPARED", "functional_cases": len(jobs)-1,
         "coverage_cases": selected, "coverage_scope": "line/expression; not toggle/FSM/assertion",
         "rtl_changes": False, "coverage_image": str(covsim),
         "policy": "stop on first non-PASS; no automatic RTL fixes"}
    save(output / "checkpoint.json", checkpoint)
    pinned_files.extend(output / f"{phase}-plan.json" for phase in ("functional", "coverage"))
    pin_inputs(output, [simv, generator], pinned_files, checkpoint)


def execute(output):
    output = checked_output(output)
    phase = "preflight"
    started = False
    try:
        check_service()
        check_inputs(output)
        checkpoint = json.loads((output / "checkpoint.json").read_text())
        if checkpoint["status"] != "PREPARED":
            raise RuntimeError("checkpoint is not PREPARED; automatic resume is forbidden")
        started = True
        _execute(output, checkpoint)
    except Exception as error:
        if started:
            try:
                phase = json.loads((output / "checkpoint.json").read_text()).get("phase", phase)
            except (OSError, ValueError, AttributeError):
                pass
        stop(output, phase, error)
        raise


def _execute(output, checkpoint):
    supervisor = [PYTHON, "verification/run_failfast_checkpoint.py"]
    for phase in ("functional", "coverage"):
        checkpoint.update(status="RUNNING", phase=phase)
        save(output / "checkpoint.json", checkpoint)
        check_inputs(output)
        if phase == "coverage":
            image = Path(checkpoint["coverage_image"])
            save(output / "coverage-image.json", {
                "path": str(image), "image_sha256": simulation_image(image)})
        try:
            run(supervisor + ["--plan", str(output / f"{phase}-plan.json"),
                              "--jobs", "5" if phase == "functional" else "3",
                              "--output", str(output / f"{phase}-scheduler")])
        except subprocess.CalledProcessError:
            checkpoint.update(status="STOPPED", reason="non-PASS; waiting for user instructions",
                              first_failure=str(output / f"{phase}-scheduler/STOP.json"))
            save(output / "checkpoint.json", checkpoint)
            raise
    reporter = ROOT / "install/verilator/bin/verilator_coverage"
    checkpoint.update(phase="merge")
    save(output / "checkpoint.json", checkpoint)
    merge = [PYTHON, "verification/coverage/merge_verilator_coverage.py"]
    for name in checkpoint["coverage_cases"]:
        replay = json.loads((output / "coverage" / name / "case_replay.json").read_text())
        for case in replay["cases"]:
            merge += ["--case", case["result"]]
    merge += ["--output", str(output / "merged"), "--verilator-coverage", str(reporter),
              "--hierarchy-prefix", "ara_tb_verilator.dut.i_ara_soc",
              "--include-path", "/hardware/src/", "--include-path", "/hardware/deps/cva6/"]
    run(merge)
    checkpoint.update(phase="audit")
    save(output / "checkpoint.json", checkpoint)
    run([PYTHON, "verification/coverage/audit_merged.py", "--audit", str(output / "merged/audit.json"),
         "--minimum-cases", str(len(checkpoint["coverage_cases"])),
         "--report", str(output / "merged/independent_audit.json")])
    checkpoint.update(phase="review")
    save(output / "checkpoint.json", checkpoint)
    run([PYTHON, "verification/coverage/review_uncovered.py", "--audit", str(output / "merged/audit.json"),
         "--minimum-cases", str(len(checkpoint["coverage_cases"])),
         "--output", str(output / "merged/review.json")])
    check_inputs(output)
    check_coverage_image(output)
    checkpoint["status"] = "PASS"
    save(output / "checkpoint.json", checkpoint)


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, OSError, ValueError, RuntimeError) as error:
        print(f"CHECKPOINT_STOP: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
