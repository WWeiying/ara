#!/usr/bin/env python3
"""Freeze 21 repaired PASS inputs, replay a new probe/coverage image, export DVE.

Default: prepare only, preserving an independently running build. Execute under
systemd (ARA_CHECKPOINT_UNIT, KillMode=control-group, Restart=no). --use-built
--build-unit waits at most 7200s and NEVER builds. No old VDB is admitted. The
three repaired stimuli remain replacements, not PASS claims for their originals.
--adopt-built explicitly accepts a garbage-collected build unit without claiming
retained process-exit evidence; quiescence and full image checks remain mandatory.
"""
import argparse
import csv
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import run_vcs_dve_checkpoint as base
import run_vcs_dve_batch as coverage
import run_remaining15_validation as prior
import run_remaining5_closure as closure
from ara_verify.artifacts import sha256, simulation_image
from ara_verify.model import TestCase
from ara_verify.runner import RegressionRunner, RunOptions
from run_failfast_checkpoint import stop_groups

ROOT, HERE = base.ROOT, base.HERE
SCRIPT = Path(__file__).resolve()
REFERENCE = ROOT / "verification/out/fault-vstart-20260927-01"
SOURCES = (ROOT / "verification/out/remaining15-validation-20260927-01",
           ROOT / "verification/out/remaining5-closure-20260927-01")
FIRST = {*(f"seed{s}" for s in (1417, 701, 704, 707, 709, 712, 716, 1406, 1420)),
         "vslide_mask_edges", "vreduction_lmul_edges", "vreduction_overlap_edges",
         "vslide1up_vredand", "vew64_widen_illegal", "vlsseg", "axpy"}
SECOND = {"seed1401-original", "seed1402-original", "seed1409-replacement",
          "seed1410-replacement", "seed1412-replacement"}
PROBES = {"seed1401-original", "seed1402-original"}
DVE = HERE / "dve_hierarchy"
read, save, check, pins = base.read, base.save, base.check, base.pins
require = prior.require


def compile_command(output):
    changes = {"code_coverage": "1", "buildpath": str(output / "build"), "sim_dir": str(output / "sim")}
    original = read(REFERENCE / "compile.command.json")["command"]
    for key in changes:
        require(sum(arg.startswith(key + "=") for arg in original) == 1, "ambiguous build option")
    return [f"{arg.split('=', 1)[0]}={changes[arg.split('=', 1)[0]]}"
            if arg.split("=", 1)[0] in changes else arg for arg in original]


def selected_sources():
    """Old PASS selects immutable stimulus only; never reuses an old verdict/VDB."""
    jobs, files, spikes = {}, {}, set()
    for directory, expected in zip(SOURCES, (FIRST, SECOND)):
        checkpoint, frozen = read(directory / "checkpoint.json"), read(directory / "frozen.json")
        require(checkpoint["status"] == "SELECTED_PASS", "source repair batch not complete PASS")
        require(sha256(directory / "frozen.json") == checkpoint["frozen_sha256"], "source ledger drift")
        require(set(frozen["jobs"]) == expected, "source selection is not the exact repair set")
        spikes.add(frozen["spike"])
        files[frozen["spike"]] = frozen["files"][frozen["spike"]]
        files.update(pins([directory / p for p in ("checkpoint.json", "frozen.json", "candidate.json")]))
        for name, original in frozen["jobs"].items():
            spec = dict(original, name=name, source_batch=str(directory),
                        fault_vstart_probe=name in PROBES, replacement=original.get("replacement", False))
            require(spec["replacement"] == name.endswith("-replacement"), "replacement identity differs")
            require(bool(original.get("fault_vstart_probe", False)) == (name in PROBES), "probe policy differs")
            verdict_path = directory / "verdicts" / (name + ".json")
            verdict = read(verdict_path)
            require(verdict["status"] == "PASS" and verdict["elf_sha256"] == spec["elf_sha256"],
                    "source verdict/ELF not PASS")
            check({spec["elf"]: spec["elf_sha256"]})
            evidence = [verdict_path, Path(spec["elf"])]
            result = directory / "results" / name
            if spec["kind"] == "axpy":
                report = read(result / "uvm_result.json")
                require(report["status"] == "PASS" and not report["issues"] and
                        report["elf_sha256"] == spec["elf_sha256"], "source AXPY is not PASS")
                runtime = result / "work/input.elf"
                require(report["sim_image_sha256"] == read(directory / "candidate.json")["image"],
                        "source AXPY image differs")
                evidence += [result / "uvm_result.json", result / "cycle_comparison.json"]
                require(read(result / "cycle_comparison.json")["status"] == "PASS", "source AXPY gate failed")
            else:
                rows = read(result / "summary.json")
                require(len(rows) == 1 and rows[0]["status"] == "PASS", "source result not one PASS")
                row, artifact = rows[0], Path(rows[0]["artifact_dir"]).resolve()
                require(artifact.is_relative_to(result.resolve()), "source artifact escaped result")
                require(row["name"] == spec.get("case", spec.get("test")), "source case differs")
                if spec["kind"] == "replay":
                    require(row["seed"] == spec["seed"], "source seed differs")
                coverage.audit_ok(read(result / "independent_audit.json"),
                                  dict(spec, source_name=row["name"]), artifact)
                metadata = read(artifact / "inputs.json")
                require(metadata["binary"]["sha256"] == spec["elf_sha256"] and
                        metadata["simv"]["image_sha256"] == read(directory / "candidate.json")["image"],
                        "source execution identity differs")
                runtime = artifact / "input.elf"
                evidence += [result / "summary.json", result / "independent_audit.json", artifact / "inputs.json"]
            check({str(runtime): spec["elf_sha256"]})
            evidence.append(runtime)
            if name in PROBES:
                evidence.append(Path(spec["diagnostic_probe"]))
            jobs[name] = spec
            files.update(pins(evidence))
    require(len(spikes) == 1 and len(jobs) == 21, "expected 21 jobs sharing one frozen Spike")
    check(files)
    return jobs, files, spikes.pop()


def tool_paths():
    imported = {Path(m.__file__).resolve() for m in list(sys.modules.values())
                if getattr(m, "__file__", None) and Path(m.__file__).resolve().is_relative_to(ROOT / "verification")}
    return sorted(imported | set((ROOT / "verification/ara_verify").rglob("*.py")) |
                  {SCRIPT, ROOT / "verification/verify.py", ROOT / "verification/uvm/run_real_dut_case.sh",
                   HERE / "vcs_coverage_exec.py", DVE / "run_dve_coverage.sh", DVE / "export_dve_coverage.tcl",
                   Path(sys.executable).resolve()})


def prepare(output):
    require(not any((output / p).exists() for p in ("plan.json", "inputs", "results", "status.json")),
            "prepared/used output exists; no overwrite or retry")
    reference = base.sources(REFERENCE / "sim/vcs_source_manifest.json")
    command = compile_command(output)
    existing = output / "compile.command.json"
    if existing.exists():
        require(read(existing)["command"] == command, "independent compile command differs")
    jobs, files, spike = selected_sources()
    output.mkdir(parents=True, exist_ok=True)
    (output / "inputs").mkdir()
    for name, spec in jobs.items():
        source, target = Path(spec["elf"]), output / "inputs" / (name + ".elf")
        shutil.copyfile(source, target)
        check({str(target): spec["elf_sha256"]})
        spec.update(source_elf=str(source), elf=str(target), coverage_test=name.replace("-", "_"))
        spec["timeout_s"] = spec.get("timeout_s", 900 if spec["kind"] == "axpy" else 300)
        files.update(pins([target]))
        if spec["kind"] == "replay":
            # Rename only the replay label, not the ELF or original case provenance.
            spec["source_case"] = spec["case"]
            spec["case"] = spec["coverage_test"]
            spec["summary"] = str(output / "inputs" / (name + ".json"))
            save(Path(spec["summary"]), [{"name": spec["case"], "seed": spec["seed"],
                 "status": "PASS", "elf": spec["elf"]}])
            files.update(pins([Path(spec["summary"])]))
    tools = tool_paths()
    files.update(pins(tools + [REFERENCE / p for p in
         ("compile.command.json", "sim/vcs_source_manifest.json", "sim/simulator.conf", "sim/simv.daidir/vcs_rebuild")]))
    files.update({r["path"]: r["sha256"] for r in reference["files"]})
    if existing.exists():
        files.update(pins([existing]))
    plan = {"schema_version": 1, "jobs": jobs, "files": files, "spike": spike,
            "compile": command, "reference": str(REFERENCE), "tools": [str(p) for p in tools],
            "checker_inventory": sorted(str(p) for p in (ROOT / "verification/ara_verify").rglob("*.py")),
            "workers": 8, "metrics": base.METRICS, "policy": "STOP_ON_ANY_NON_PASS",
            "old_vdb_reuse": False, "historical_pass_is_selection_only": True}
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pins([output / "plan.json"]))
    frozen(output)
    save(output / "status.json", {"status": "PREPARED", "total": 21, "workers": 8,
                                  "simulations_started": False})


def frozen(output, runtime=False):
    check(read(output / "plan.sha256.json"))
    plan = read(output / "plan.json")
    check(plan["files"])
    require(sorted(str(p) for p in (ROOT / "verification/ara_verify").rglob("*.py")) ==
            plan["checker_inventory"], "checker file inventory drift")
    base.sources(REFERENCE / "sim/vcs_source_manifest.json")
    if runtime:
        check(read(output / "runtime.sha256.json"))
        record = read(output / "runtime.json")
        check(record["files"])
        require(simulation_image(output / "sim/simv") == record["image"], "runtime image inventory drift")
        require(simulation_image(output / "inputs/coverage_simv") == record["wrapper_image"],
                "wrapper image inventory drift")
        base.sources(output / "sim/vcs_source_manifest.json")
    return plan


def wait_build(unit, output, timeout_s=7200, adopt_built=False):
    require(bool(unit) and 0 < timeout_s <= 7200, "bounded build service wait required")
    deadline = time.monotonic() + timeout_s
    while True:
        command = ["systemctl", "--user", "show", unit]
        for key in ("LoadState", "ActiveState", "MainPID", "Result", "ExecMainStatus", "ExecMainCode",
                    "ExecMainStartTimestampMonotonic"):
            command += ["-p", key]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        save(output / "build-service.json", dict(state, unit=unit))
        if adopt_built and state.get("LoadState") == "not-found":
            require(state.get("ActiveState") == "inactive" and state.get("MainPID") == "0",
                    "garbage-collected build is not quiescent")
            base.quiescent_build(unit)
            save(output / "build-service.json", dict(state, unit=unit, explicit_adoption=True,
                 process_exit_evidence="NOT_RETAINED_UNIT_GC", image_validation="REQUIRED_BEFORE_REPLAY"))
            return
        require(state.get("LoadState") == "loaded", "build unit missing; completion NOT_PROVEN")
        if state.get("ActiveState") in ("inactive", "failed"):
            require(state.get("ActiveState") == "inactive" and state.get("MainPID") == "0" and
                    state.get("Result") == "success" and state.get("ExecMainStatus") == "0" and
                    state.get("ExecMainCode") == "1" and
                    int(state.get("ExecMainStartTimestampMonotonic", "0")) > 0,
                    "independent build did not exit successfully")
            base.quiescent_build(unit)
            return
        require(time.monotonic() < deadline, "build wait exceeded bound; completion NOT_PROVEN")
        time.sleep(min(10, max(0, deadline - time.monotonic())))


def check_build(output):
    require(read(output / "compile.command.json")["command"] == compile_command(output), "build command drift")
    before = base.sources(output / "sim/vcs_source_manifest.json")
    reference = base.sources(REFERENCE / "sim/vcs_source_manifest.json")
    normalized = lambda data, root: {r["path"].replace(str(root) + "/", "<IMAGE>/"): r["sha256"]
                                     for r in data["files"]}
    require(normalized(before, output) == normalized(reference, REFERENCE), "reference/candidate source set differs")
    require(base.normalized_vcs(output, True) == base.normalized_vcs(REFERENCE), "VCS flags differ beyond coverage")
    for path in ("sim/simulator.conf", "build/vcs/bender_script_default"):
        require((output / path).read_bytes() == (REFERENCE / path).read_bytes(), "configuration/filelist differs")
    design = output / "sim/simv.vdb"
    require((design / "snps/coverage/db/design/verilog.design.xml").is_file(), "missing instrumented design")
    base.pure_design(design)
    save(output / "source_manifest.checked.json", before)
    image = simulation_image(output / "sim/simv")
    require(len(image) > 1, "compiled runtime libraries missing")
    wrapper = output / "inputs/coverage_simv"
    shutil.copyfile(HERE / "vcs_coverage_exec.py", wrapper)
    wrapper.chmod(0o755)
    Path(str(wrapper) + ".daidir").symlink_to(output / "sim/simv.daidir", target_is_directory=True)
    shutil.copyfile(output / "sim/simulator.conf", output / "inputs/simulator.conf")
    save(output / "inputs/coverage-wrapper.json", {"simv": str(output / "sim/simv"), "image": image,
                                                  "results": str(output / "results")})
    wrapper_image = simulation_image(wrapper)
    save(output / "candidate.json", {"image": wrapper_image, "real_image": image})
    paths = [output / p for p in ("candidate.json", "compile.command.json", "sim/simulator.conf",
             "sim/vcs_source_manifest.json", "sim/simv.daidir/vcs_rebuild", "source_manifest.checked.json",
             "inputs/simulator.conf", "inputs/coverage-wrapper.json", "inputs/coverage_simv")]
    files = dict(pins(paths), **image)
    files.update({r["path"]: r["sha256"] for r in before["files"]})
    record = {"image": image, "wrapper_image": wrapper_image, "files": files,
              "design_files": base.inventory(design)}
    save(output / "runtime.json", record)
    save(output / "runtime.sha256.json", pins([output / "runtime.json"]))
    return record


def commands(output, spec, plan):
    target, wrapper = output / "results" / spec["name"], output / "inputs/coverage_simv"
    verify = [sys.executable, str(ROOT / "verification/verify.py")]
    if spec["kind"] == "axpy":
        command = ["bash", str(ROOT / "verification/uvm/run_real_dut_case.sh"), str(wrapper), spec["elf"],
                   spec["coverage_test"], str(target)]
        audit = [sys.executable, str(ROOT / "verification/ara_verify/uvm_dut.py"),
                 "--require-events", "--require-backend", "--require-axi", "--require-axi-write",
                 "--vector-trace", str(target / "work/vector_trace.csv"), "--log", str(target / "work/run.vcs.log"),
                 "--simv", str(wrapper), "--elf", str(target / "work/input.elf"),
                 "--output", str(target / "independent_uvm_audit.json")]
        # uvm_dut uses package-relative imports; invoke as a module in worker().
        audit[1:2] = ["-m", "ara_verify.uvm_dut"]
        return command, audit
    audit = verify + ["audit", "--run", str(target), "--require-trace", "--output",
                      str(target / "independent_audit.json")]
    if spec["kind"] == "directed":
        command = [sys.executable, str(SCRIPT), "--output", str(output), "--directed", spec["name"]]
    else:
        command = verify + ["replay-failed-rvv", "--summary", spec["summary"], "--include-passed",
                  "--case", spec["case"], "--simv", str(wrapper), "--spike", plan["spike"],
                  "--spike-isa", base.ISA, "--jobs", "1", "--timeout", str(spec["timeout_s"]),
                  "--spike-timeout", "60", "--watchdog-cycles", "100000", "--output", str(target)]
        if spec["fault_vstart_probe"]:
            command.append("--fault-vstart-probe")
        audit += ["--require-vector", "--require-full-match"]
    return command, audit


def directed(output, name):
    spec = frozen(output, True)["jobs"][name]
    require(spec["kind"] == "directed", "not a selected directed case")
    options = RunOptions(repo_root=ROOT, output_root=output / "results" / name, config="default",
                         jobs=1, seed=1, dry_run=False, build_only=False, skip_build=True,
                         simv=output / "inputs/coverage_simv", commit_trace=True, timeout_s=spec["timeout_s"],
                         code_coverage=False)
    test = TestCase(name=spec["test"], kind="rvv", build_target="unused-no-build", binary=Path(spec["elf"]),
                    testcase=spec["coverage_test"], timeout_s=spec["timeout_s"])
    results = RegressionRunner(options, [test], sys.argv).run()
    require(len(results) == 1 and results[0].status == "PASS", "directed selfcheck failed")


def worker(output, name):
    outcome = {"name": name, "status": "FAIL", "admitted": False}
    try:
        plan = frozen(output, True)
        spec, target = plan["jobs"][name], output / "results" / name
        require(not target.exists(), "existing result; no automatic retries")
        command, audit = commands(output, spec, plan)
        env = {"PYTHONPATH": str(ROOT / "verification"), "ARA_VCS_TIMEOUT_SECONDS": str(spec["timeout_s"])}
        require(coverage.invoke(command, output / "logs" / (name + ".log"), spec["timeout_s"] + 600, env) == 0,
                "replay/selfcheck process failed")
        require(coverage.invoke(audit, output / "logs" / (name + "-audit.log"), 300, env) == 0,
                "independent audit process failed")
        prior.validate_result(output, name, plan)
        if spec["kind"] == "axpy":
            require(read(target / "independent_uvm_audit.json") == read(target / "uvm_result.json"),
                    "independent UVM recheck differs")
            artifact = target / "work"
            work = artifact
        else:
            row = read(target / "summary.json")[0]
            artifact = Path(row["artifact_dir"]).resolve()
            coverage.audit_ok(read(target / "independent_audit.json"), dict(spec, source_name=row["name"]), artifact)
            work = artifact / "work" if spec["kind"] == "directed" else artifact
            if spec["kind"] == "replay":
                require(row["spike_returncode"] == row["rtl_returncode"] == 0 and
                        row["spike_timed_out"] is False and row["rtl_timed_out"] is False,
                        "reference/RTL completion not proven")
                enabled = "+ARA_FAULT_VSTART_PROBE" in read(artifact / "rtl.command.json")["command"]
                require(enabled == spec["fault_vstart_probe"], "runtime probe opt-in differs")
                if enabled:
                    save(target / "fault_vstart_capture.json", closure.check_probe(artifact, Path(spec["diagnostic_probe"])))
        vdb = work / "code.vdb"
        vdb_files = coverage.valid_vdb(vdb, spec["coverage_test"], str(output / "sim/simv"))
        launch = read(work / "coverage.command.json")
        require(launch["command"][0] == str(output / "sim/simv"), "wrapper did not execute new image")
        evidence = [p for p in target.rglob("*") if p.is_file() and not p.is_relative_to(vdb)]
        frozen(output, True)
        outcome.update(status="PASS", admitted=True, kind=spec["kind"], replacement=spec["replacement"],
                       original_status_unchanged=spec.get("original_outcome", {}).get("status"),
                       elf_sha256=spec["elf_sha256"], files=pins(evidence), vdb=str(vdb),
                       vdb_files=vdb_files, coverage_test=spec["coverage_test"])
        save(output / "outcomes" / (name + ".json"), outcome)
        return 0
    except Exception as error:
        outcome["reason"] = f"{type(error).__name__}: {error}"
        save(output / "outcomes" / (name + ".json"), outcome)
        return 1


def schedule(output, names, jobs):
    require(1 <= jobs <= 8, "worker count must be 1..8")
    rows = [{"name": name, "status": "PENDING"} for name in names]
    active, index, cancelled = {}, 0, []
    handlers = {sig: signal.signal(sig, lambda sig, frame: cancelled.append(sig))
                for sig in (signal.SIGINT, signal.SIGTERM)}
    def publish():
        save(output / "scheduler/status.json", {"workers": jobs, "cases": rows})
    try:
        while active or index < len(rows):
            # Reap every completed child before dispatch: no post-failure refill.
            done = [(i, child.poll()) for i, child in active.items()]
            for i, rc in done:
                if rc is not None:
                    rows[i].update(status="PASS" if rc == 0 else "FAIL", returncode=rc)
            if cancelled or any(rc is not None and rc != 0 for _, rc in done):
                raise RuntimeError("repair fail-fast: child failure or cancellation")
            for i, rc in done:
                if rc is not None:
                    del active[i]
            publish()
            if index < len(rows) and len(active) < jobs:
                log = output / "logs" / (rows[index]["name"] + "-worker.log")
                with log.open("w") as stream:
                    child = subprocess.Popen([sys.executable, "-B", str(SCRIPT), "--output", str(output),
                            "--worker", rows[index]["name"]], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True)
                active[index] = child
                rows[index].update(status="RUNNING", pid=child.pid)
                index += 1
                continue
            if active:
                time.sleep(0.2)
    finally:
        if active:
            save(output / "scheduler/cleanup.json", stop_groups(active))
        for row in rows:
            if row["status"] in ("RUNNING", "PENDING"):
                row["status"] = "CANCELLED"
        publish()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def merge(output, plan, runtime):
    outcomes = [read(output / "outcomes" / (name + ".json")) for name in plan["jobs"]]
    require(len(outcomes) == 21, "all 21 outcomes required before DVE")
    databases = {str(output / "sim/simv.vdb"): runtime["design_files"]}
    for name, item in zip(plan["jobs"], outcomes):
        require(item["name"] == name and item["status"] == "PASS" and item["admitted"] is True,
                "non-PASS case cannot enter verified coverage")
        vdb = Path(item["vdb"]).resolve()
        require(vdb.is_relative_to(output / "results" / name) and vdb.name == "code.vdb" and
                str(vdb) not in databases, "foreign/old/duplicate VDB rejected")
        check(item["files"])
        require(coverage.valid_vdb(vdb, item["coverage_test"], str(output / "sim/simv")) == item["vdb_files"],
                "case VDB changed")
        databases[str(vdb)] = item["vdb_files"]
    base.pure_design(output / "sim/simv.vdb")
    require(all(base.inventory(Path(p)) == hashes for p, hashes in databases.items()), "VDB drift before DVE")
    save(output / "dve-inputs.before.json", databases)
    target = output / "dve"
    require(coverage.invoke(["bash", str(DVE / "run_dve_coverage.sh"), str(target), *databases],
                output / "logs/dve.log", 720, {"DVE_COVERAGE_TIMEOUT": "600"}) == 0, "DVE export failed")
    expected = [str(Path(o["vdb"]).with_suffix("") / o["coverage_test"]) for o in outcomes]
    require((target / "selected_tests.txt").read_text().splitlines() == expected, "DVE selected unexpected tests")
    with (target / "summary.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(rows and {"Line", "Condition", "FSM", "Toggle", "Branch"} <= rows[0].keys(),
            "DVE did not export the five requested metric columns")
    after = {p: base.inventory(Path(p)) for p in databases}
    save(output / "dve-inputs.after.json", after)
    require(after == databases, "DVE modified an input VDB")
    frozen(output, True)
    stack, probe_rows = [], []
    for row in rows:
        depth = int(row["Depth"])
        stack[depth:] = [row]
        if "ara_fault_vstart_probe" in row["Name"]:
            probe_rows.append({"path": ".".join(r["Name"].strip() for r in stack),
                               "row": row, "ancestors": stack[:-1]})
    summary = {"status": "PASS", "total": 21, "passed": 21, "replacement_cases": 3,
               "metrics_requested": base.METRICS, "coverage_top": rows[0],
               "scope": "NEW_IMAGE_INDEPENDENT_PASS_ONLY; originals of replacements remain unchanged",
               "unavailable_metrics": "NA is unavailable, not covered; no assertion coverage claim",
               "hierarchy_scope": "Raw full hierarchy includes TB/UVM and bound fault-vstart probe; "
                  "ancestor scores include probe contributions. No subtraction or pure-DUT score claim. "
                  "This 21-case subset is not cumulative with or directly comparable to old 427-case coverage.",
               "probe_enabled_cases": sorted(PROBES), "probe_hierarchy_rows": probe_rows,
               "image": runtime["image"], "cases": outcomes,
               "reports": pins([p for p in target.rglob("*") if p.is_file() and
                                 p.suffix in (".csv", ".txt", ".log")])}
    save(output / "collection.json", summary)
    save(output / "summary.json", summary)
    return summary


def execute(output, use_built, build_unit, wait_s, jobs, adopt_built=False):
    state = read(output / "status.json")
    require(state["status"] == "PREPARED", "only fresh PREPARED output may execute")
    base.check_service()
    with (ROOT / "verification/out/.batch-vcs.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            plan = frozen(output)
            use_built = use_built or adopt_built
            state.update(status="RUNNING", phase="waiting-build" if use_built else "build", workers=jobs)
            save(output / "status.json", state)
            if use_built:
                wait_build(build_unit, output, wait_s, adopt_built=adopt_built)
            else:
                require(not (output / "sim").exists() and not (output / "build").exists(),
                        "existing build requires --use-built; will not rebuild")
                base.run(plan["compile"], output / "compile.log", 7200)
            frozen(output)
            runtime = check_build(output)
            frozen(output, True)
            (output / "logs").mkdir(exist_ok=True)
            state.update(phase="replay+audit", simulations_started=True)
            save(output / "status.json", state)
            schedule(output, list(plan["jobs"]), jobs)
            state.update(phase="DVE")
            save(output / "status.json", state)
            merge(output, plan, runtime)
            state.update(status="PASS", phase="complete", passed=21)
            save(output / "status.json", state)
        except Exception as error:
            state.update(status="FAIL", reason=f"{type(error).__name__}: {error}", verified_coverage=False)
            save(output / "status.json", state)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--worker")
    mode.add_argument("--directed")
    parser.add_argument("--use-built", action="store_true")
    parser.add_argument("--adopt-built", action="store_true",
                        help="never compile; explicitly allow a GC'ed build unit, with full image validation")
    parser.add_argument("--build-unit")
    parser.add_argument("--build-wait-s", type=int, default=7200)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=8)
    args = parser.parse_args()
    output = base.checked_output(args.output)
    if args.worker:
        return worker(output, args.worker)
    if args.directed:
        directed(output, args.directed)
    elif args.execute:
        require(not (args.use_built or args.adopt_built) or args.build_unit, "built-image reuse requires --build-unit")
        execute(output, args.use_built, args.build_unit, args.build_wait_s, args.jobs, args.adopt_built)
    else:
        prepare(output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"STOP: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
