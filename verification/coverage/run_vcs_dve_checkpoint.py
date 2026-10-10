#!/usr/bin/env python3
"""Prepare only by default; explicitly build/replay five audited PASS ELFs in VCS.

Execute as systemd main process with ARA_CHECKPOINT_UNIT, KillMode=control-group,
Restart=no, RemainAfterExit=no. Serial short replays stop on the first non-PASS.
--use-built adopts the separately coordinated build in this output after its
service is inactive. No checker/RTL modifications, URG, or Verilator execution.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(ROOT / "verification"))
from ara_verify.artifacts import sha256, simulation_image
from ara_verify.vcs_source_manifest import collect
from run_coverage_checkpoint import check_service, checked_output, save
from vcs_coverage_exec import METRICS

REFERENCE = ROOT / "verification/out/seed509-fix-20260926-01"
BATCH = ROOT / "verification/out/batch-exploration-20260926-04"
ISA = "rv64gcv_zvfh_zvl1024b"
PREFIXES = ("short_memory_cross-coverage300-seed601-", "short_control_cross-coverage300-seed703-",
            "fp32-coverage300-seed1101-", "fp64-coverage300-seed1201-")


def read(path):
    return json.loads(Path(path).read_text())


def pins(paths):
    return {str(Path(p).resolve(strict=True)): sha256(Path(p)) for p in paths}


def check(files):
    for path, expected in files.items():
        if sha256(Path(path)) != expected:
            raise RuntimeError(f"frozen input changed: {path}")


def inventory(directory):
    return pins(sorted(p for p in directory.rglob("*") if p.is_file()))


def compile_command(output):
    original = read(REFERENCE / "compile.command.json")["command"]
    replacements = {"code_coverage": "1", "buildpath": str(output / "build"),
                    "sim_dir": str(output / "sim")}
    return [f"{arg.split('=', 1)[0]}={replacements[arg.split('=', 1)[0]]}"
            if "=" in arg and arg.split("=", 1)[0] in replacements else arg for arg in original]


def run(command, log, timeout):
    save(log.with_suffix(".command.json"), {"command": command, "cwd": str(ROOT), "timeout_s": timeout})
    with log.open("w") as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                       timeout=timeout, check=True)


def audit_ok(report, name, artifact):
    rows = report.get("cases", [])
    if (report.get("status") != "PASS" or report.get("errors") or len(rows) != 1 or
            report.get("case_count") != 1 or report.get("passed_cases") != 1 or
            report.get("failed_cases") != 0 or rows[0].get("name") != name or
            rows[0].get("status") != "PASS" or rows[0].get("errors") or
            Path(rows[0]["artifact_dir"]).resolve() != artifact.resolve() or
            any(report.get("policy", {}).get(k) is not True for k in
                ("require_complete", "require_trace", "require_vector", "require_full_match"))):
        raise RuntimeError("missing matching complete independent scalar/vector PASS audit")


def sources(manifest):
    data = read(manifest)
    actual = collect(Path(data["filelist"]), Path(data["repo_root"]),
                     [Path(p) for p in data["extra_sources"]])
    if actual != data["files"]:
        raise RuntimeError(f"source manifest drift: {manifest}")
    return data


def prepare(output):
    if (output / "plan.json").exists():
        raise ValueError("plan already exists")
    output.mkdir(parents=True, exist_ok=True)  # May already contain the separately launched build.
    reference = sources(REFERENCE / "sim/vcs_source_manifest.json")
    checkpoint = read(BATCH / "checkpoint.json")
    selected = [("seed509", REFERENCE / "results/seed509/summary.json",
                 REFERENCE / "results/seed509/independent_audit.json")]
    for prefix in PREFIXES:
        matches = [(name, row) for name, row in checkpoint["cases"].items() if name.startswith(prefix)]
        if len(matches) != 1 or matches[0][1]["status"] != "PASS":
            raise RuntimeError(f"missing unique PASS sample: {prefix}")
        name, row = matches[0]
        selected.append((name, Path(row["summary"]), Path(row["audit"])))
    files = pins([SCRIPT, HERE / "vcs_coverage_exec.py", HERE / "run_dve_coverage.sh",
                  HERE / "export_dve_coverage.tcl", ROOT / "verification/verify.py",
                  ROOT / "verification/run_coverage_checkpoint.py", REFERENCE / "compile.command.json",
                  REFERENCE / "sim/simulator.conf", REFERENCE / "sim/vcs_source_manifest.json",
                  REFERENCE / "sim/simv.daidir/vcs_rebuild", BATCH / "checkpoint.json"])
    files.update(pins((ROOT / "verification/ara_verify").glob("*.py")))
    files.update({row["path"]: row["sha256"] for row in reference["files"]})
    reference_image = simulation_image(REFERENCE / "sim/simv")
    files.update(reference_image)
    cases = []
    for name, summary, audit in selected:
        rows = read(summary)
        if len(rows) != 1 or rows[0]["status"] != "PASS":
            raise RuntimeError("source summary is not one PASS case")
        row = rows[0]
        artifact = Path(row["artifact_dir"])
        audit_ok(read(audit), row["name"], artifact)
        metadata = read(artifact / "inputs.json")
        if metadata["simv"]["image_sha256"] != reference_image:
            raise RuntimeError("source sample was not run on seed509 frozen configuration")
        elf, spike = artifact / "input.elf", Path(metadata["spike"]["path"])
        check({str(elf): metadata["binary"]["sha256"], str(spike): metadata["spike"]["sha256"]})
        frozen = output / "inputs" / (name + ".elf")
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(elf, frozen)
        check({str(frozen): metadata["binary"]["sha256"]})
        replay = output / "inputs" / (name + ".json")
        save(replay, [{"name": row["name"], "profile": row.get("profile", ""),
                       "seed": row["seed"], "status": "PASS", "elf": str(frozen)}])
        files.update(pins([summary, audit, artifact / "inputs.json", elf, frozen, replay, spike]))
        cases.append({"name": name, "testcase": row["name"], "summary": str(replay),
                      "source_summary": str(summary), "source_audit": str(audit), "spike": str(spike),
                      "elf_sha256": metadata["binary"]["sha256"], "prior_rtl_s": row.get("rtl_elapsed_s")})
    plan = {"cases": cases, "files": files, "compile": compile_command(output), "spike_isa": ISA,
            "metrics": METRICS, "reference": str(REFERENCE), "policy": "STOP_ON_FIRST_NON_PASS"}
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pins([output / "plan.json"]))
    check(files)
    save(output / "status.json", {"status": "PREPARED", "phase": "VCS coverage", "total": len(cases),
                                  "simulations_started": False})


def frozen(output):
    check(read(output / "plan.sha256.json"))
    plan = read(output / "plan.json")
    check(plan["files"])
    return plan


def normalized_vcs(directory, remove_coverage=False):
    lines = (directory / "sim/simv.daidir/vcs_rebuild").read_text().splitlines()
    commands = [shlex.split(line) for line in lines if line.startswith("vcs ")]
    if len(commands) != 1 or commands[0][-1] != "2>&1":
        raise RuntimeError("unrecognized VCS rebuild command")
    words = commands[0][:-1]
    if remove_coverage:
        for option, expected in (("-cm", METRICS), ("-cm_dir", str(directory / "sim/simv.vdb"))):
            if words.count(option) != 1 or words[words.index(option) + 1] != expected:
                raise RuntimeError(f"missing or wrong VCS instrumentation: {option}")
            index = words.index(option)
            del words[index:index + 2]
    return [word.replace(str(directory), "<IMAGE>") for word in words]


def check_build(output):
    manifest = output / "sim/vcs_source_manifest.json"
    before = sources(manifest)
    if normalized_vcs(output, True) != normalized_vcs(REFERENCE):
        raise RuntimeError("VCS flags changed beyond coverage and independent directories")
    if (output / "sim/simulator.conf").read_bytes() != (REFERENCE / "sim/simulator.conf").read_bytes():
        raise RuntimeError("candidate QBS/AKV2/L2 configuration differs")
    if (output / "build/vcs/bender_script_default").read_bytes() != (REFERENCE / "build/vcs/bender_script_default").read_bytes():
        raise RuntimeError("candidate actual Bender filelist/defines differ")
    design = output / "sim/simv.vdb"
    if not (design / "snps/coverage/db/design/verilog.design.xml").is_file():
        raise RuntimeError("missing instrumented VCS design database")
    pure_design(design)
    # This is the NEW build's actual pre-VCS manifest, not the reference ledger.
    save(output / "source_manifest.before.json", before)
    after = dict(before, files=collect(Path(before["filelist"]), ROOT,
                                      [Path(p) for p in before["extra_sources"]]))
    save(output / "source_manifest.after.json", after)
    if before != after:
        raise RuntimeError("build source changed")
    return simulation_image(output / "sim/simv")


def pure_design(design):
    if any((design / "snps/coverage/db/testdata").glob("*/*.data.xml")):
        raise RuntimeError("design VDB is contaminated with runtime coverage")


def replay_command(output, case):
    return [sys.executable, str(ROOT / "verification/verify.py"), "replay-failed-rvv",
            "--summary", case["summary"], "--include-passed", "--case", case["testcase"],
            "--simv", str(output / "inputs/coverage_simv"), "--spike", case["spike"],
            "--spike-isa", ISA, "--jobs", "1", "--timeout", "900", "--spike-timeout", "120",
            "--watchdog-cycles", "250000", "--output", str(output / "results" / case["name"])]


def quiescent_build(unit):
    result = subprocess.run(["systemctl", "--user", "show", unit, "-p", "ActiveState", "-p", "MainPID",
                             "-p", "ControlGroup"], capture_output=True, text=True, check=True, timeout=10)
    state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if state.get("ActiveState") not in ("inactive", "failed") or state.get("MainPID") != "0":
        raise RuntimeError("separate build service is still active; do not replay yet")
    group = state.get("ControlGroup", "")
    if group:
        directory = (Path("/sys/fs/cgroup") / group.lstrip("/")).resolve()
        if directory == Path("/sys/fs/cgroup") or not directory.is_relative_to("/sys/fs/cgroup"):
            raise RuntimeError("unsafe build cgroup path")
        if directory.exists() and any(p.read_text().strip() for p in directory.rglob("cgroup.procs")):
            raise RuntimeError("build service still has descendants")


def execute(output, use_built, build_unit):
    state = read(output / "status.json")
    try:
        check_service()
        if state["status"] != "PREPARED":
            raise RuntimeError("output must be PREPARED; no automatic retries")
        plan = frozen(output)
        state.update(status="RUNNING", phase="compile")
        save(output / "status.json", state)
        if use_built:
            quiescent_build(build_unit)
        else:
            if (output / "sim").exists() or (output / "build").exists():
                raise RuntimeError("build exists; use explicit --use-built after coordinated completion")
            run(plan["compile"], output / "compile.log", 7200)
        image = check_build(output)
        frozen(output)
        config = output / "inputs/coverage-wrapper.json"
        save(config, {"simv": str(output / "sim/simv"), "image": image, "results": str(output / "results")})
        wrapper = output / "inputs/coverage_simv"
        shutil.copyfile(HERE / "vcs_coverage_exec.py", wrapper)
        wrapper.chmod(0o755)
        Path(str(wrapper) + ".daidir").symlink_to(output / "sim/simv.daidir", target_is_directory=True)
        runtime = dict(image, **pins([wrapper, config]))
        save(output / "image.json", runtime)
        databases, accepted = [output / "sim/simv.vdb"], []
        for case in plan["cases"]:
            frozen(output)
            check(runtime)
            sources(output / "sim/vcs_source_manifest.json")
            state.update(phase="replay", active_case=case["name"], simulations_started=True)
            save(output / "status.json", state)
            target = output / "results" / case["name"]
            run(replay_command(output, case), output / "logs" / f"{case['name']}.log", 1200)
            audit = target / "independent_audit.json"
            run([sys.executable, str(ROOT / "verification/verify.py"), "audit", "--run", str(target),
                 "--require-trace", "--require-vector", "--require-full-match", "--output", str(audit)],
                output / "logs" / f"{case['name']}-audit.log", 300)
            artifact = target / "tests" / case["testcase"]
            audit_ok(read(audit), case["testcase"], artifact)
            rows = read(target / "summary.json")
            if len(rows) != 1 or rows[0]["status"] != "PASS" or sha256(artifact / "input.elf") != case["elf_sha256"]:
                raise RuntimeError("replay did not independently pass with frozen ELF")
            vdb = artifact / "code.vdb"
            testroot = vdb / "snps/coverage/db/testdata"
            tests = sorted(p.name for p in testroot.iterdir() if p.is_dir()) if testroot.is_dir() else []
            datafiles = list((testroot / case["testcase"]).glob("*.data.xml"))
            if tests != [case["testcase"]] or not datafiles or any(p.stat().st_size == 0 for p in datafiles):
                raise RuntimeError("missing/incomplete or unexpected per-case coverage test")
            check(runtime)
            frozen(output)
            record = {"name": case["name"], "status": "PASS", "vdb": str(vdb),
                      "files": pins([audit, target / "summary.json", artifact / "inputs.json",
                                     artifact / "coverage.command.json"]), "vdb_files": inventory(vdb)}
            save(output / "outcomes" / (case["name"] + ".json"), record)
            accepted.append(record)
            databases.append(vdb)
            state.update(completed=len(accepted))
            save(output / "status.json", state)
        pure_design(databases[0])
        before = {str(db): inventory(db) for db in databases}
        for record in accepted:
            check(record["files"])
            if before[record["vdb"]] != record["vdb_files"]:
                raise RuntimeError("completed VDB changed before DVE")
        save(output / "dve_inputs.before.json", before)
        save(output / "dve_exporter.json", pins([HERE / "run_dve_coverage.sh", HERE / "export_dve_coverage.tcl"]))
        state.update(phase="DVE")
        save(output / "status.json", state)
        run(["bash", str(HERE / "run_dve_coverage.sh"), str(output / "dve"), *map(str, databases)],
            output / "logs/dve.log", 300)
        after = {str(db): inventory(db) for db in databases}
        save(output / "dve_inputs.after.json", after)
        if before != after:
            raise RuntimeError("DVE modified coverage input databases")
        selected = (output / "dve/selected_tests.txt").read_text().splitlines()
        expected = [str(Path(record["vdb"]).with_suffix("") / case["testcase"])
                    for record, case in zip(accepted, plan["cases"])]
        if selected != expected:
            raise RuntimeError("DVE selected tests differ from independently passed set")
        with (output / "dve/summary.csv").open(newline="") as stream:
            if len(list(csv.reader(stream))) < 2:
                raise RuntimeError("DVE summary is empty")
        check(runtime)
        frozen(output)
        sources(output / "sim/vcs_source_manifest.json")
        save(output / "collection.json", {"status": "PASS", "samples": accepted, "metrics_requested": METRICS,
             "source_before": str(output / "source_manifest.before.json"),
             "source_after": str(output / "source_manifest.after.json"),
             "reports": pins([output / "dve/summary.csv", output / "dve/selected_tests.txt"]),
             "scope": "DVE reported metrics only; NA is unavailable, not coverage closure"})
        state.update(status="PASS", phase="complete", active_case=None)
        save(output / "status.json", state)
        return 0
    except Exception as error:
        state.update(status="STOPPED", reason=str(error))
        save(output / "status.json", state)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--use-built", action="store_true")
    parser.add_argument("--build-unit", default="ara-vcs-dve-build-20260927-01.service")
    args = parser.parse_args()
    output = checked_output(args.output)
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.execute:
        return execute(output, args.use_built, args.build_unit)
    if args.use_built:
        parser.error("--use-built requires --execute")
    prepare(output)
    print(f"PREPARED, NOT LAUNCHED: {output}")
    print(shlex.join(compile_command(output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
