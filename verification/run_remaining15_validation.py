#!/usr/bin/env python3
"""Prepare a bounded repair validation, then execute only under systemd.

Review/prepare (no compilation or simulation):
  python3 verification/run_remaining15_validation.py --prepare-only --patch-ready \
    --output verification/out/remaining15-UNIQUE --allow-dispatcher-change \
    [--image verification/out/remaining15-image-UNIQUE] [--confirmed-seed N]

Execute the prepared snapshot in a new service, not a shell background job:
  systemd-run --user --unit=ara-remaining15-UNIQUE --service-type=exec \
    -p KillMode=control-group -p Restart=no -p TimeoutStopSec=5s \
    --setenv=ARA_CHECKPOINT_UNIT=ara-remaining15-UNIQUE.service \
    --working-directory=/absolute/worktree /usr/bin/python3 \
    /absolute/worktree/verification/run_remaining15_validation.py \
    --execute-prepared --patch-ready --output /absolute/NEW_PREPARED_DIRECTORY

Only selected validations can pass. Unscheduled historical failures remain
PENDING. No regeneration, automatic repair, retry, coverage or old-result edits.
Default order: seed1417, six control seeds, directed/AXPY gates, optional replays.
The archived vlsseg ELF uses an explicit 900s budget; no application is rebuilt.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from ara_verify.artifacts import check_inputs, sha256, simulation_image
from ara_verify.catalog import load_catalog
from ara_verify.model import TestCase
from ara_verify.plan import _full_architecture_match, _full_vector_match
from ara_verify.runner import RegressionRunner, RunOptions
from ara_verify.spike_probe import probe_paths
from ara_verify.vcs_source_manifest import collect
from run_coverage_checkpoint import check_service, save
from run_seed509_validation import compile_command, cycles, vcs_argv


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
OUT = ROOT / "verification/out"
REFERENCE = OUT / "seed509-fix-20260926-01"
BATCH = OUT / "batch-exploration-20260926-04"
AXPY = OUT / "merged-store-fp16-smoke-20260926-01/axpy"
DIRECTED = ("vslide_mask_edges", "vreduction_lmul_edges", "vreduction_overlap_edges")
NEW_DIRECTED = OUT / "vslide1up-vredand-20260927-01"
CONTROL_DIRECTED = OUT / "control6-ew64-unit-20260927-01"
CONTROLS = (701, 704, 707, 709, 712, 716)
OOB_SEEDS = (1409, 1410, 1412)
SLDU = ROOT / "hardware/src/sldu/sldu.sv"
DISPATCHER = ROOT / "hardware/src/ara_dispatcher.sv"
PYTHON = sys.executable


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def checked_output(path):
    path = path.resolve()
    require(path != OUT.resolve() and path.is_relative_to(OUT.resolve()),
            "output must be a new directory below verification/out")
    return path


def current_sources(manifest):
    return collect(Path(manifest["filelist"]), Path(manifest["repo_root"]),
                   [Path(p) for p in manifest["extra_sources"]])


def authorized_sources(previous, current, allow_dispatcher=False):
    before = {r["path"]: r["sha256"] for r in previous}
    after = {r["path"]: r["sha256"] for r in current}
    require(len(before) == len(previous) and len(after) == len(current), "duplicate source paths")
    require(before.keys() == after.keys(), "source inventory changed")
    changed = sorted(p for p in before if before[p] != after[p])
    allowed = {str(SLDU)} | ({str(DISPATCHER)} if allow_dispatcher else set())
    require(set(changed) <= allowed, f"unauthorized compile-source changes: {changed}")
    return changed


def select_cases(plan, checkpoint, confirmed):
    require(checkpoint["status"] in {"STOPPED", "COMPLETE_WITH_FAILURES", "PASS"},
            "historical batch must not be active")
    names = [r["name"] for r in plan["cases"]]
    require(len(names) == len(set(names)), "duplicate batch case names")
    require(set(checkpoint["cases"]) == set(names) and checkpoint["completed"] == len(names),
            "batch checkpoint is incomplete or differs from plan")
    remaining = [r for r in plan["cases"] if checkpoint["cases"][r["name"]]["status"] != "PASS"]
    require(len(confirmed) == len(set(confirmed)) and not ({1417, *CONTROLS} & set(confirmed)),
            "duplicate confirmed seed or default seed redundantly selected")
    require(not set(confirmed) & set(OOB_SEEDS), "OOB/reference-retry seeds are not RTL repair PASS targets")
    selected = []
    for seed in [1417, *CONTROLS, *confirmed]:
        matches = [r for r in remaining if r["kind"] == "random" and r.get("seed") == seed]
        require(len(matches) == 1, f"seed {seed} must identify exactly one unresolved random case")
        selected.append(matches[0])
    return remaining, selected


def snapshot_elf(source, destination, files):
    expected = sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.exists(), f"input destination already exists: {destination}")
    shutil.copy2(source, destination)
    require(sha256(source) == expected == sha256(destination), f"ELF changed while freezing: {source}")
    files.update((source, destination))
    return {"elf": str(destination), "elf_sha256": expected, "original_elf": str(source)}


def old_replay(row, outcome, batch, identity, reference_image):
    origin = Path(outcome.get("source_batch", str(batch))).resolve()
    require(origin.is_relative_to(OUT.resolve()), "historical source escaped verification/out")
    run = origin / "cases" / row["name"]
    artifact = Path(outcome["artifact_dir"]).resolve()
    require(artifact.is_relative_to(run.resolve()), "historical artifact escaped its case")
    if not (artifact / "inputs.json").is_file():
        candidates = list((run / "tests").glob("*/inputs.json"))
        require(len(candidates) == 1, "historical infrastructure failure has no unique frozen ELF")
        artifact = candidates[0].parent.resolve()
    files = {artifact / "input.elf", artifact / "inputs.json", artifact / "rtl.command.json"}
    if origin != batch:
        for path in files:
            require(identity.get("reused_evidence", {}).get(str(path)) == sha256(path),
                    f"historical reuse pin missing/changed: {path}")
    inputs = read(artifact / "inputs.json")
    elf = artifact / "input.elf"
    require(inputs["binary"]["path"] == str(elf) and sha256(elf) == inputs["binary"]["sha256"],
            "old private ELF differs")
    require(inputs["simv"]["image_sha256"] == reference_image, "old case used a different RTL image")
    spike = Path(inputs["spike"]["path"])
    require(sha256(spike) == inputs["spike"]["sha256"], "old Spike changed")
    command = read(artifact / "rtl.command.json")["command"]
    require(command[0] == str(REFERENCE / "sim/simv") and
            f"+ntb_random_seed={row['seed']}" in command and f"+PRELOAD={elf}" in command,
            "old invocation does not bind seed, ELF and image")
    files.add(spike)
    if outcome.get("summary"):
        summary = Path(outcome["summary"])
        require(summary.resolve() == (run / "summary.json").resolve(), "old summary escaped case")
        rows = read(summary)
        require(len(rows) == 1 and rows[0]["seed"] == row["seed"] and
                Path(rows[0]["artifact_dir"]).resolve() == artifact, "old summary identity differs")
        files.add(summary)
    return elf, spike, artifact.name, files


def baseline(files):
    report = read(AXPY / "uvm_result.json")
    log, elf = AXPY / "run.vcs.log", AXPY / "input.elf"
    require(report["status"] == "PASS" and report["issues"] == [] and cycles(log) == 2810,
            "retained AXPY baseline is not a 2810-cycle PASS")
    require(report["elf_sha256"] == sha256(elf) and report["log_sha256"] == sha256(log),
            "AXPY baseline ELF/log drift")
    image = report["sim_image_sha256"]
    launchers = [Path(p) for p in image if Path(p).name == "simv"]
    require(len(launchers) == 1 and simulation_image(launchers[0]) == image,
            "AXPY baseline runtime image drift")
    files.update((elf, log, AXPY / "uvm_result.json"))
    return image


def prepare(output, batch=BATCH, confirmed=(), allow_dispatcher=False, workers=5, image=None):
    require(1 <= workers <= 5, "workers must be 1..5")
    output = checked_output(output)
    batch = batch.resolve()
    require(batch.is_relative_to(OUT.resolve()), "batch must be in this worktree's verification/out")
    image = image.resolve() if image else output
    require(image.is_relative_to(OUT.resolve()) and image != OUT.resolve(), "image must be in this worktree's verification/out")
    prebuilt = image != output
    if prebuilt:
        require((image / "sim/simv").is_file(), "prebuilt image is not ready")
    require(not output.exists(), "output already exists; no automatic resume or overwrite")
    output.mkdir(parents=True)
    try:
        plan, checkpoint, identity = [read(batch / f) for f in ("plan.json", "checkpoint.json", "identity.json")]
        remaining, selected = select_cases(plan, checkpoint, list(confirmed))
        require(read(REFERENCE / "validation.json")["status"] == "PASS", "reference validation is not PASS")
        reference_image = simulation_image(REFERENCE / "sim/simv")
        require(reference_image == read(REFERENCE / "image.json") ==
                identity["images"][str(REFERENCE / "sim/simv")], "seed509 reference image differs")
        manifest_path = REFERENCE / "sim/vcs_source_manifest.json"
        manifest = read(manifest_path)
        sources = current_sources(manifest)
        changed = authorized_sources(manifest["files"], sources, allow_dispatcher)
        catalog = load_catalog(ROOT, ROOT / "verification/suites.json")
        for name in DIRECTED:
            require("rvv:" + name in catalog.tests, f"directed catalog ID not ready: rvv:{name}")
            require(catalog.tests["rvv:" + name].binary.is_file(), f"directed ELF not ready: rvv:{name}")
        files = {SCRIPT, manifest_path, REFERENCE / "validation.json", REFERENCE / "image.json",
                 REFERENCE / "sim/simulator.conf", REFERENCE / "sim/simv.daidir/vcs_rebuild",
                 REFERENCE / "build/vcs/bender_script_default",
                 *(batch / f for f in ("plan.json", "checkpoint.json", "identity.json")),
                 ROOT / "verification/verify.py", ROOT / "verification/suites.json",
                 ROOT / "verification/run_seed509_validation.py", ROOT / "verification/run_coverage_checkpoint.py",
                 ROOT / "verification/run_failfast_checkpoint.py", ROOT / "verification/uvm/run_real_dut_case.sh",
                 ROOT / "apps/riscv-tests/isa/rv64uv/Makefrag",
                 ROOT / "install/riscv-gcc/bin/riscv64-unknown-elf-readelf",
                 ROOT / "install/riscv-llvm/bin/llvm-objdump", *probe_paths(ROOT)}
        files.update((ROOT / "verification/ara_verify").glob("*.py"))
        jobs, spike = {}, None
        for row in selected:
            elf, reference_spike, case, evidence = old_replay(
                row, checkpoint["cases"][row["name"]], batch, identity, reference_image)
            require(spike is None or spike == reference_spike, "selected replays use different Spike")
            spike = reference_spike
            name = f"seed{row['seed']}"
            frozen = snapshot_elf(elf, output / "inputs" / f"{name}.elf", files)
            summary = output / "inputs" / f"{name}-summary.json"
            save(summary, [{"name": case, "profile": row["test"], "seed": row["seed"],
                            "status": checkpoint["cases"][row["name"]]["status"], "elf": frozen["elf"]}])
            files.update(evidence | {summary})
            jobs[name] = {**frozen, "kind": "replay", "seed": row["seed"], "case": case,
                          "summary": str(summary), "original_case": row["name"]}
        for name in DIRECTED:
            files.add(ROOT / "apps/riscv-tests/isa/rv64uv" / f"{name}.c")
            jobs[name] = {**snapshot_elf(catalog.tests["rvv:" + name].binary,
                                        output / "inputs" / f"{name}.elf", files),
                          "kind": "directed", "test": "rvv:" + name}
        new_manifest = read(NEW_DIRECTED / "manifest.json")
        new_elf = NEW_DIRECTED / "inputs/vslide1up_vredand.elf"
        require(new_manifest["status"] == "PASS" and new_manifest["golden"] == "Spike" and
                new_manifest["cases"] == 64 and new_manifest["checks"] == 256 and
                sha256(new_elf) == new_manifest["elf_sha256"], "Kant directed ELF/golden manifest differs")
        files.update(p for p in NEW_DIRECTED.rglob("*") if p.is_file())
        jobs["vslide1up_vredand"] = {**snapshot_elf(new_elf, output / "inputs/vslide1up_vredand.elf", files),
                                    "kind": "directed", "test": "rvv:vslide1up_vredand"}
        control_proof = read(CONTROL_DIRECTED / "result.json")
        control_elf = CONTROL_DIRECTED / "vew64_widen_illegal.elf"
        require(control_proof["status"] == "PASS_SPIKE_ONLY" and
                control_proof["illegal_checks"] == control_proof["legal_checks"] == 6 and
                control_proof["elf_sha256"] == sha256(control_elf) and
                control_proof["golden_sha256"] == sha256(CONTROL_DIRECTED / "vew64_widen_illegal.spike.elf"),
                "Franklin directed ELF/golden proof differs")
        files.update(p for p in CONTROL_DIRECTED.rglob("*") if p.is_file())
        jobs["vew64_widen_illegal"] = {**snapshot_elf(control_elf, output / "inputs/vew64_widen_illegal.elf", files),
                                      "kind": "directed", "test": "rvv:vew64_widen_illegal"}
        old_segment = [r for r in remaining if r.get("test") == "rvv:vlsseg"]
        require(len(old_segment) == 1, "expected one unresolved archived vlsseg")
        segment = old_segment[0]
        segment_artifact = Path(checkpoint["cases"][segment["name"]]["artifact_dir"]).resolve()
        segment_elf = segment_artifact / "input.elf"
        segment_inputs = read(segment_artifact / "inputs.json")
        require(sha256(segment_elf) == segment["elf_sha256"] == segment_inputs["binary"]["sha256"] and
                segment_inputs["simv"]["image_sha256"] == reference_image, "archived vlsseg identity differs")
        files.add(segment_artifact / "inputs.json")
        jobs["vlsseg"] = {**snapshot_elf(segment_elf, output / "inputs/vlsseg.elf", files),
                          "kind": "directed", "test": "rvv:vlsseg", "timeout_s": 900,
                          "original_case": segment["name"],
                          "reason": "Original 300s budget exhausted; unchanged ELF, explicit 900s validation."}
        baseline_image = baseline(files)
        jobs["axpy"] = {**snapshot_elf(AXPY / "input.elf", output / "inputs/axpy.elf", files),
                        "kind": "axpy"}
        phases = [("seed1417", ["seed1417"], 1),
                  ("control", [f"seed{s}" for s in CONTROLS], workers),
                  ("regression", ["vslide1up_vredand", "vew64_widen_illegal", *DIRECTED, "axpy", "vlsseg"], workers)]
        if confirmed:
            phases.append(("confirmed-replays", [f"seed{s}" for s in confirmed], workers))
        for phase, names, count in phases:
            path = output / f"{phase}-plan.json"
            save(path, [{"name": n, "cwd": str(ROOT), "command": [PYTHON, str(SCRIPT),
                        "--output", str(output), "--job", n]} for n in names])
            files.add(path)
        record = {"schema_version": 1, "batch": str(batch), "sources": sources,
                  "reference_manifest": manifest, "allowed_changes": changed,
                  "files": {str(p): sha256(p) for p in sorted(files)}, "jobs": jobs,
                  "spike": str(spike), "reference_image": reference_image, "baseline_image": baseline_image,
                  "compile_argv": vcs_argv(REFERENCE), "phases": phases,
                  "image_root": str(image), "prebuilt": prebuilt,
                  "tool_inventory": sorted(str(p) for p in (ROOT / "verification/ara_verify").glob("*.py")),
                  "remaining": [{"name": r["name"], "seed": r.get("seed"),
                                 "original_status": checkpoint["cases"][r["name"]]["status"],
                                 "selected": r in selected or r == segment,
                                 "classification": "OOB_STIMULUS_REFERENCE_RETRY" if r.get("seed") in OOB_SEEDS
                                 else "AWAIT_STRICT_CHECKER" if r.get("seed") in (1401, 1402, 1406, 1420)
                                 else "REPAIR_VALIDATION"} for r in remaining]}
        if prebuilt:
            freeze_candidate(output, record)
            record["files"].update({str(p): sha256(p) for p in
                (image / "sim/vcs_source_manifest.json", image / "sim/simulator.conf",
                 image / "sim/simv.daidir/vcs_rebuild", image / "build/vcs/bender_script_default",
                 output / "candidate.json")})
        save(output / "frozen.json", record)
        save(output / "checkpoint.json", {"status": "PREPARED", "phase": "review",
             "frozen_sha256": sha256(output / "frozen.json"), "coverage_build": False,
             "candidate_sha256": sha256(output / "candidate.json") if prebuilt else None,
             "workers_max": workers, "scope": "selected repair validation, not all remaining failures",
             "remaining": [{**r, "validation_status": "PENDING"} for r in record["remaining"]]})
        check_frozen(output)
        return record
    except Exception as error:
        save(output / "STOP.json", {"phase": "prepare", "reason": str(error)})
        raise


def check_frozen(output):
    require(sha256(output / "frozen.json") == read(output / "checkpoint.json")["frozen_sha256"],
            "frozen manifest changed")
    record = read(output / "frozen.json")
    require(sorted(str(p) for p in (ROOT / "verification/ara_verify").glob("*.py")) ==
            record["tool_inventory"], "checker inventory changed")
    for path, expected in record["files"].items():
        require(sha256(Path(path)) == expected, f"frozen input/checker/ELF drift: {path}")
    require(current_sources(record["reference_manifest"]) == record["sources"], "frozen compile-source drift")
    require(simulation_image(REFERENCE / "sim/simv") == record["reference_image"], "reference image drift")
    for path in record["baseline_image"]:
        require(sha256(Path(path)) == record["baseline_image"][path], "baseline image drift")
    if (output / "candidate.json").exists():
        require(sha256(output / "candidate.json") == read(output / "checkpoint.json")["candidate_sha256"],
                "candidate identity record drift")
        candidate = read(output / "candidate.json")
        image = Path(record["image_root"])
        require(simulation_image(image / "sim/simv") == candidate["image"], "candidate runtime drift")
        require(sha256(image / "sim/vcs_source_manifest.json") == candidate["manifest_sha256"] and
                sha256(image / "sim/simulator.conf") == candidate["config_sha256"], "candidate metadata drift")
        manifest = read(image / "sim/vcs_source_manifest.json")
        require(current_sources(manifest) == manifest["files"], "candidate source drift")
    return record


def freeze_candidate(output, record):
    image = Path(record["image_root"])
    require(vcs_argv(image) == record["compile_argv"], "VCS compile options differ from reference")
    for relative in ("sim/simulator.conf", "build/vcs/bender_script_default"):
        require((image / relative).read_bytes() == (REFERENCE / relative).read_bytes(),
                f"candidate configuration/source list differs: {relative}")
    manifest = read(image / "sim/vcs_source_manifest.json")
    require(current_sources(manifest) == manifest["files"], "compiled source drift")
    external = lambda rows, base: {r["path"]: r["sha256"] for r in rows
                                  if not Path(r["path"]).is_relative_to(base)}
    require(external(manifest["files"], image) == external(record["sources"], REFERENCE),
            "compiled inputs differ from prepared source snapshot")
    require(os.access(image / "sim/simv", os.X_OK) and
            any((image / "sim/simv.daidir").glob("*.so")), "incomplete compiled image")
    save(output / "candidate.json", {"image": simulation_image(image / "sim/simv"),
         "manifest_sha256": sha256(image / "sim/vcs_source_manifest.json"),
         "config_sha256": sha256(image / "sim/simulator.conf")})


def run(command, log, timeout):
    command = [str(x) for x in command]
    log.parent.mkdir(parents=True, exist_ok=True)
    save(log.with_suffix(".command.json"), {"command": command, "cwd": str(ROOT), "timeout_s": timeout})
    with log.open("w") as stream:
        subprocess.run(command, cwd=ROOT, check=True, timeout=timeout,
                       stdout=stream, stderr=subprocess.STDOUT)


def commands(output, name, record):
    spec = record["jobs"][name]
    result, simv = output / "results" / name, Path(record["image_root"]) / "sim/simv"
    verify = [PYTHON, str(ROOT / "verification/verify.py")]
    if spec["kind"] == "axpy":
        return ["bash", str(ROOT / "verification/uvm/run_real_dut_case.sh"), str(simv),
                spec["elf"], "remaining15_axpy", str(result)], None
    common = ["--simv", str(simv), "--jobs", "1", "--timeout", "300", "--output", str(result)]
    audit = verify + ["audit", "--run", str(result), "--require-trace", "--output",
                      str(result / "independent_audit.json")]
    if spec["kind"] == "replay":
        command = verify + ["replay-failed-rvv", "--summary", spec["summary"], "--case", spec["case"],
                            "--spike", record["spike"], "--spike-isa", "rv64gcv_zvfh_zvl1024b",
                            "--spike-timeout", "60", "--watchdog-cycles", "100000"] + common
        audit += ["--require-vector", "--require-full-match"]
    else:
        command = [PYTHON, str(SCRIPT), "--output", str(output), "--run-directed", name]
    return command, audit


def run_directed(output, name):
    record = check_frozen(output)
    spec = record["jobs"][name]
    require(spec["kind"] == "directed", "not a frozen directed ELF")
    options = RunOptions(repo_root=ROOT, output_root=output / "results" / name,
                         config="default", jobs=1, seed=1, dry_run=False, build_only=False,
                         skip_build=True, simv=Path(record["image_root"]) / "sim/simv",
                         commit_trace=True, timeout_s=spec.get("timeout_s", 300))
    case = TestCase(name=spec["test"], kind="rvv", build_target="unused-no-build",
                    binary=Path(spec["elf"]), testcase=name, timeout_s=options.timeout_s)
    results = RegressionRunner(options, [case], [str(SCRIPT), "--run-directed", name]).run()
    require(len(results) == 1 and results[0].status == "PASS", "directed selfcheck did not pass")
    check_frozen(output)


def validate_result(output, name, record):
    result, spec = output / "results" / name, record["jobs"][name]
    image = read(output / "candidate.json")["image"]
    if spec["kind"] == "axpy":
        report = read(result / "uvm_result.json")
        log, elf = result / "work/run.vcs.log", result / "work/input.elf"
        require(report["status"] == "PASS" and report["issues"] == [], "AXPY UVM is not PASS")
        require(report["elf_sha256"] == sha256(elf) == spec["elf_sha256"] and
                report["log_sha256"] == sha256(log) and report["sim_image_sha256"] == image and
                report["vector_trace_sha256"] == sha256(result / "work/vector_trace.csv"),
                "AXPY runtime/ELF/log identity differs")
        measured = cycles(log)
        save(result / "cycle_comparison.json", {"status": "PASS" if measured <= 2810 else "FAIL",
             "baseline_cycles": 2810, "candidate_cycles": measured, "baseline": str(AXPY)})
        require(measured <= 2810, f"AXPY cycle regression: {measured} > 2810")
        return
    rows = read(result / "summary.json")
    require(len(rows) == 1 and rows[0]["status"] == "PASS", "expected exactly one PASS result")
    row = rows[0]
    if spec["kind"] == "directed":
        require(row["name"] == spec["test"], "directed result identity differs")
    artifact = Path(row["artifact_dir"]).resolve()
    require(artifact.is_relative_to(result.resolve()), "result artifact escaped run")
    elf = artifact / "input.elf"
    inputs = read(artifact / "inputs.json")
    require(not check_inputs(inputs, elf) and sha256(elf) == spec["elf_sha256"] and
            inputs["simv"]["image_sha256"] == image, "executed ELF/image differs from frozen input")
    audit = read(result / "independent_audit.json")
    require(audit["status"] == "PASS" and audit["errors"] == [] and audit["case_count"] == 1 and
            len(audit["cases"]) == 1 and audit["cases"][0]["status"] == "PASS" and
            Path(audit["cases"][0]["artifact_dir"]).resolve() == artifact, "independent audit is not PASS")
    flags = ["require_complete", "require_trace"]
    if spec["kind"] == "replay":
        flags += ["require_vector", "require_full_match"]
        scalar = read(artifact / "commit_comparison.json")
        vector = read(artifact / "vector_commit_comparison.json")
        require(row.get("seed") == spec["seed"] and row.get("name") == spec["case"], "replay identity differs")
        require(inputs["spike"]["path"] == record["spike"] and
                inputs["spike"]["sha256"] == record["files"][record["spike"]], "replay Spike differs")
        require(row["comparison"] == scalar and row["vector_commit"] == vector and
                _full_architecture_match(scalar) and _full_vector_match(vector),
                "strict complete scalar/vector match not proven")
    for flag in flags:
        require(audit["policy"].get(flag) is True, f"independent audit lacks {flag}")


def job(output, name):
    record = check_frozen(output)
    require((output / "candidate.json").is_file(), "candidate has not been frozen")
    require(name in record["jobs"], "job is not selected")
    if name != "seed1417":
        require(read(output / "seed1417-scheduler/status.json")["status"] == "PASS",
                "seed1417 gate has not passed")
    if name not in {"seed1417", *(f"seed{s}" for s in CONTROLS)}:
        require(read(output / "control-scheduler/status.json")["status"] == "PASS",
                "control gates have not passed")
    if record["jobs"][name]["kind"] == "replay" and name not in {"seed1417", *(f"seed{s}" for s in CONTROLS)}:
        require(read(output / "regression-scheduler/status.json")["status"] == "PASS",
                "directed/performance gate has not passed")
    require(not (output / "results" / name).exists(), "job output exists; retries forbidden")
    command, audit = commands(output, name, record)
    run(command, output / "logs" / f"{name}.log", max(900, record["jobs"][name].get("timeout_s", 300) + 300)
        if name != "axpy" else 1000)
    if audit:
        run(audit, output / "logs" / f"{name}-audit.log", 300)
    validate_result(output, name, record)
    check_frozen(output)
    save(output / "verdicts" / f"{name}.json", {"status": "PASS", "name": name,
         "elf_sha256": record["jobs"][name]["elf_sha256"]})


def execute(output):
    check_service()
    state = read(output / "checkpoint.json")
    require(state["status"] == "PREPARED", "only PREPARED may execute; no resume")
    try:
        record = check_frozen(output)
        state.update(status="RUNNING", phase="prebuilt-check" if record["prebuilt"] else "compile")
        save(output / "checkpoint.json", state)
        if not record["prebuilt"]:
            run(compile_command(output), output / "compile.log", 1800)
            check_frozen(output)
            freeze_candidate(output, record)
            state["candidate_sha256"] = sha256(output / "candidate.json")
            save(output / "checkpoint.json", state)
        for phase, names, workers in record["phases"]:
            state["phase"] = phase
            save(output / "checkpoint.json", state)
            check_frozen(output)
            run([PYTHON, ROOT / "verification/run_failfast_checkpoint.py", "--plan",
                 output / f"{phase}-plan.json", "--jobs", workers,
                 "--output", output / f"{phase}-scheduler"],
                output / "logs" / f"{phase}-scheduler.log", 3600)
            scheduler = read(output / f"{phase}-scheduler/status.json")
            require(scheduler["status"] == "PASS" and
                    {r["name"] for r in scheduler["results"]} == set(names) and
                    all(r["status"] == "PASS" for r in scheduler["results"]), "scheduler did not pass every job")
            for name in names:
                require(read(output / "verdicts" / f"{name}.json")["status"] == "PASS", "missing job verdict")
                for item in state["remaining"]:
                    if item["name"] == record["jobs"][name].get("original_case"):
                        item["validation_status"] = "PASS"
            save(output / "checkpoint.json", state)
        check_frozen(output)
        state.update(status="SELECTED_PASS", phase="complete",
                     pending_count=sum(r["validation_status"] == "PENDING" for r in state["remaining"]))
        save(output / "checkpoint.json", state)
    except Exception as error:
        state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}")
        save(output / "checkpoint.json", state)
        save(output / "STOP.json", state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch", type=Path, default=BATCH)
    parser.add_argument("--image", type=Path, help="prebuilt image root containing sim/ and build/; prepare only")
    parser.add_argument("--patch-ready", action="store_true")
    parser.add_argument("--allow-dispatcher-change", action="store_true")
    parser.add_argument("--confirmed-seed", action="append", type=int, default=[])
    parser.add_argument("--jobs", type=int, choices=range(1, 6), default=5)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--execute-prepared", action="store_true")
    mode.add_argument("--job", help=argparse.SUPPRESS)
    mode.add_argument("--run-directed", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not (args.job or args.run_directed) and not args.patch_ready:
        parser.error("prepare/execute require --patch-ready after source and checker review")
    if not args.prepare_only and (args.confirmed_seed or args.allow_dispatcher_change or args.image):
        parser.error("seed selection/source permission must be frozen at prepare time")
    os.environ.update(PYTHONPATH=str(ROOT / "verification"), ARA_VCS_TIMEOUT_SECONDS="900",
                      ARA_CONTRACT_TRACE_LIMIT="100000", ARA_UVM_TRACE_LIMIT="100000")
    output = checked_output(args.output)
    if args.prepare_only:
        prepare(output, args.batch, args.confirmed_seed, args.allow_dispatcher_change, args.jobs, args.image)
    elif args.job or args.run_directed:
        require(bool(os.environ.get("INVOCATION_ID")), "worker requires the owning systemd service")
        if args.job:
            job(output, args.job)
        else:
            run_directed(output, args.run_directed)
    else:
        execute(output)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"REMAINING15_STOP: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
