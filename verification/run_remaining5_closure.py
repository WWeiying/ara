#!/usr/bin/env python3
"""Freeze five closure inputs, then run strict VCS/Spike replay under systemd.

No build/generator path. Prepare only after checker and replacement review:
  python3 verification/run_remaining5_closure.py --prepare-only --checker-ready \
    --replacements /absolute/replacements.json

Replacement manifest schema (paths relative to the manifest are accepted):
  {"schema_version": 1, "replacements": [{"seed": 1409,
    "original_elf_sha256": "...", "elf": "fixed.elf", "elf_sha256": "...",
    "reason": "Repair defined-scalar injection corrupting index rotation", "evidence": [{"path": "repair.json",
    "sha256": "..."}]}]}
Exactly seeds 1409, 1410, 1412 are required. They are replacements, never a
retroactive PASS of the old invalid stimuli. Original 1401/1402 ELFs are reused.

After reviewing the prepared output, execute in ONE systemd --user service:
  systemd-run --user --unit=ara-remaining5-UNIQUE --service-type=exec \
    -p KillMode=control-group -p Restart=no -p TimeoutStopSec=5s \
    --setenv=ARA_CHECKPOINT_UNIT=ara-remaining5-UNIQUE.service \
    --working-directory=/absolute/worktree /usr/bin/python3 \
    /absolute/worktree/verification/run_remaining5_closure.py --execute-prepared
"""

import argparse
import os
from pathlib import Path
import re
import sys

from ara_verify.artifacts import sha256, simulation_image
from ara_verify.spike_probe import probe_paths
from run_coverage_checkpoint import check_service, save
import run_remaining15_validation as prior


ROOT, OUT = prior.ROOT, prior.OUT
SCRIPT = Path(__file__).resolve()
DEFAULT_OUTPUT = OUT / "remaining5-closure-20260927-01"
IMAGE = OUT / "fault-vstart-20260927-01"
BATCH = OUT / "batch-exploration-20260926-04"
SEEDS = (1401, 1402, 1409, 1410, 1412)
REPLACEMENTS = {1409, 1410, 1412}
PROBE = ROOT / "verification/probes/ara_fault_vstart_probe.sv"
read, require = prior.read, prior.require


def replacement_inputs(path):
    payload = read(path)
    require(payload.get("schema_version") == 1, "unsupported replacement schema")
    rows = payload["replacements"]
    require(len(rows) == 3 and {r["seed"] for r in rows} == REPLACEMENTS,
            "replacement manifest must contain exactly 1409/1410/1412")
    result, files = {}, {path}
    for row in rows:
        require(type(row["seed"]) is int and bool(row["reason"].strip()), "invalid replacement seed/reason")
        elf = (path.parent / row["elf"]).resolve()
        require(elf.is_relative_to(ROOT), "replacement ELF must be in this worktree")
        require(sha256(elf) == row["elf_sha256"], "replacement ELF hash differs")
        require(row["elf_sha256"] != row["original_elf_sha256"], "replacement must not silently reuse old OOB ELF")
        require(isinstance(row["evidence"], list) and bool(row["evidence"]), "replacement evidence is required")
        evidence = {}
        for entry in row["evidence"]:
            source = (path.parent / entry["path"]).resolve()
            require(source.is_relative_to(ROOT) and sha256(source) == entry["sha256"],
                    "replacement evidence path/hash differs")
            evidence[str(source)] = entry["sha256"]
            files.add(source)
        files.add(elf)
        result[row["seed"]] = {**row, "elf": str(elf), "evidence": evidence}
    return result, files


def prepare(output, replacements, workers=5):
    output = prior.checked_output(output)
    require(1 <= workers <= 5, "workers must be 1..5")
    require(not output.exists(), "output exists; overwrite/resume forbidden")
    replacement, files = replacement_inputs(replacements.resolve())
    plan, checkpoint, identity = [read(BATCH / f) for f in ("plan.json", "checkpoint.json", "identity.json")]
    require(checkpoint["status"] == "STOPPED" and checkpoint["completed"] == checkpoint["total"],
            "batch04 must be a completed, stopped historical checkpoint")
    manifest_path = IMAGE / "sim/vcs_source_manifest.json"
    manifest = read(manifest_path)
    require(prior.current_sources(manifest) == manifest["files"], "probe image source drift")
    require(str(PROBE) in {r["path"] for r in manifest["files"]}, "image did not compile fault-vstart probe")
    image = simulation_image(IMAGE / "sim/simv")
    captured = read(IMAGE / "frozen.json")
    require(len(image) > 1 and all(captured.get(p) == value for p, value in image.items()),
            "probe runtime differs from diagnostic image snapshot")
    files.update({SCRIPT, PROBE, manifest_path, IMAGE / "frozen.json", IMAGE / "sim/simulator.conf",
                  IMAGE / "sim/simv.daidir/vcs_rebuild", ROOT / "verification/verify.py",
                  ROOT / "verification/run_remaining15_validation.py",
                  ROOT / "verification/run_seed509_validation.py",
                  ROOT / "verification/run_coverage_checkpoint.py",
                  ROOT / "verification/run_failfast_checkpoint.py",
                  ROOT / "install/riscv-gcc/bin/riscv64-unknown-elf-readelf",
                  ROOT / "install/riscv-llvm/bin/llvm-objdump", *probe_paths(ROOT),
                  *(BATCH / f for f in ("plan.json", "checkpoint.json", "identity.json"))})
    files.update((ROOT / "verification/ara_verify").glob("*.py"))
    output.mkdir(parents=True)
    try:
        jobs, spike = {}, None
        for seed in SEEDS:
            matches = [r for r in plan["cases"] if r.get("seed") == seed and r["kind"] == "random"]
            require(len(matches) == 1, f"ambiguous/missing historical seed {seed}")
            row = matches[0]
            outcome = checkpoint["cases"][row["name"]]
            require(outcome["status"] != "PASS", "historical result is not one of the remaining failures")
            elf, reference_spike, case, evidence = prior.old_replay(
                row, outcome, BATCH, identity, identity["images"][str(prior.REFERENCE / "sim/simv")])
            require(spike is None or spike == reference_spike, "inconsistent reference Spike")
            spike = reference_spike
            files.update(evidence)
            original = prior.snapshot_elf(elf, output / "original-inputs" / f"seed{seed}.elf", files)
            name = f"seed{seed}" + ("-replacement" if seed in REPLACEMENTS else "-original")
            provenance = {"original_case": row["name"], "original_outcome": outcome,
                          "original_elf": original, "replacement": seed in REPLACEMENTS}
            if seed in REPLACEMENTS:
                item = replacement[seed]
                require(item["original_elf_sha256"] == original["elf_sha256"], "replacement points at wrong original ELF")
                source = Path(item["elf"])
                provenance["replacement_record"] = item
            else:
                source = elf
                probe = IMAGE / f"seed{seed}/probe.json"
                observed = read(probe)
                require(observed["status"] == "TRAP_VSTART_CONFIRMED" and
                        observed["elf_sha256"] == original["elf_sha256"], "diagnostic probe ELF differs")
                files.add(probe)
                provenance["diagnostic_probe"] = str(probe)
            frozen = prior.snapshot_elf(source, output / "inputs" / f"{name}.elf", files)
            replay_case = case if seed not in REPLACEMENTS else f"{case}_replacement_{seed}"
            summary = output / "inputs" / f"{name}.json"
            save(summary, [{"name": replay_case, "seed": seed, "profile": row["test"],
                            "status": "REPLACEMENT_PENDING" if seed in REPLACEMENTS else outcome["status"],
                            "elf": frozen["elf"]}])
            files.add(summary)
            jobs[name] = {**frozen, **provenance, "kind": "replay", "seed": seed,
                          "case": replay_case, "summary": str(summary), "fault_vstart_probe": seed not in REPLACEMENTS}
        schedule = output / "plan.json"
        save(schedule, [{"name": name, "cwd": str(ROOT), "command": [sys.executable, str(SCRIPT),
             "--output", str(output), "--job", name]} for name in jobs])
        save(output / "candidate.json", {"image": image})
        files.update({schedule, output / "candidate.json"})
        record = {"schema_version": 1, "image_root": str(IMAGE), "image": image, "manifest": manifest,
                  "jobs": jobs, "spike": str(spike), "workers": workers,
                  "files": {str(p): sha256(p) for p in sorted(files)},
                  "tool_inventory": sorted(str(p) for p in (ROOT / "verification/ara_verify").glob("*.py")),
                  "scope": "2 original-ELF validations + 3 explicit stimulus replacements; old results unchanged"}
        save(output / "frozen.json", record)
        save(output / "checkpoint.json", {"status": "PREPARED", "phase": "review",
             "frozen_sha256": sha256(output / "frozen.json"), "workers_max": workers,
             "cases": {name: {"status": "PENDING", "replacement": spec["replacement"],
                               "original_status": spec["original_outcome"]["status"]} for name, spec in jobs.items()}})
        check_frozen(output)
    except Exception as error:
        save(output / "STOP.json", {"phase": "prepare", "reason": str(error)})
        raise


def check_frozen(output):
    require(sha256(output / "frozen.json") == read(output / "checkpoint.json")["frozen_sha256"], "frozen manifest drift")
    record = read(output / "frozen.json")
    require(sorted(str(p) for p in (ROOT / "verification/ara_verify").glob("*.py")) ==
            record["tool_inventory"], "checker inventory drift")
    for path, expected in record["files"].items():
        require(sha256(Path(path)) == expected, f"frozen source/tool/ELF/evidence drift: {path}")
    require(prior.current_sources(record["manifest"]) == record["manifest"]["files"], "compiled source drift")
    require(simulation_image(Path(record["image_root"]) / "sim/simv") == record["image"], "runtime image drift")
    return record


def commands(output, name, record):
    command, audit = prior.commands(output, name, record)
    if record["jobs"][name]["fault_vstart_probe"]:
        command.append("--fault-vstart-probe")
    return command, audit


def check_probe(artifact, diagnostic):
    """Verify fresh probe capture; scalar/vector correctness still requires audit."""
    expected = read(diagnostic)["response"]
    log = artifact / "run.vcs.log"
    events = [dict(re.findall(r"(\w+)=([^\s]+)", line)) for line in log.read_text().splitlines()
              if line.startswith("[ARA_FAULT_VSTART]")]
    responses = [r for r in events if r.get("phase") == "RESP" and r.get("fire") == "1" and
                 r.get("current_insn") == expected["current_insn"]]
    require(len(responses) == 1, "missing/ambiguous fresh fault-vstart response")
    response = responses[0]
    for key in ("cause", "tval", "exception_vstart", "csr_vstart_d"):
        require(int(response[key], 16) == int(expected[key], 16), f"probe differs: {key}")
    require(response["backend_valid"] == response["backend_exception"] == "1", "probe lacks backend exception")
    following = [r for r in events if r.get("phase") == "NEXT" and
                 (r.get("inst"), r.get("event")) == (response.get("inst"), response["event"])]
    require(len(following) == 1 and following[0]["rst_n"] == "1" and
            int(following[0]["cycle"]) == int(response["cycle"]) + 1 and
            int(following[0]["actual_q"], 16) == int(response["csr_vstart_d"], 16),
            "fresh next-cycle vstart not proven")
    return {"status": "CAPTURE_CONFIRMED", "not_case_pass": True,
            "log_sha256": sha256(log), "response": response, "next": following[0]}


def job(output, name):
    record = check_frozen(output)
    require(name in record["jobs"], "unselected job")
    result = output / "results" / name
    require(not result.exists(), "existing result; no retry/overwrite")
    command, audit = commands(output, name, record)
    prior.run(command, output / "logs" / f"{name}.log", 900)
    prior.run(audit, output / "logs" / f"{name}-audit.log", 300)
    prior.validate_result(output, name, record)
    spec = record["jobs"][name]
    rows = read(result / "summary.json")
    artifact = Path(rows[0]["artifact_dir"])
    require(rows[0]["spike_returncode"] == 0 and rows[0]["spike_timed_out"] is False and
            rows[0]["rtl_returncode"] == 0 and rows[0]["rtl_timed_out"] is False,
            "reference/RTL completion not proven")
    if spec["fault_vstart_probe"]:
        require("+ARA_FAULT_VSTART_PROBE" in read(artifact / "rtl.command.json")["command"], "probe not enabled")
        save(result / "fault_vstart_capture.json", check_probe(artifact, Path(spec["diagnostic_probe"])))
    check_frozen(output)
    save(output / "verdicts" / f"{name}.json", {"status": "PASS", "seed": spec["seed"],
         "replacement": spec["replacement"], "elf_sha256": spec["elf_sha256"],
         "original_status_unchanged": spec["original_outcome"]["status"]})


def execute(output):
    check_service()
    state = read(output / "checkpoint.json")
    require(state["status"] == "PREPARED", "only PREPARED may execute; no resume")
    try:
        record = check_frozen(output)
        state.update(status="RUNNING", phase="strict-replay")
        save(output / "checkpoint.json", state)
        prior.run([sys.executable, ROOT / "verification/run_failfast_checkpoint.py", "--plan",
                   output / "plan.json", "--jobs", record["workers"], "--output", output / "scheduler"],
                  output / "logs/scheduler.log", 6600)
        scheduler = read(output / "scheduler/status.json")
        require(scheduler["status"] == "PASS" and len(scheduler["results"]) == 5 and
                {r["name"] for r in scheduler["results"]} == set(record["jobs"]) and
                all(r["status"] == "PASS" for r in scheduler["results"]), "not all five strict jobs passed")
        for name in record["jobs"]:
            verdict = read(output / "verdicts" / f"{name}.json")
            require(verdict["status"] == "PASS" and verdict["elf_sha256"] == record["jobs"][name]["elf_sha256"],
                    "missing/mismatched strict verdict")
            state["cases"][name].update(verdict)
        check_frozen(output)
        state.update(status="SELECTED_PASS", phase="complete", original_elf_passes=2,
                     replacement_passes=3, historical_failures_relabelled=0)
        save(output / "checkpoint.json", state)
    except Exception as error:
        state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}")
        save(output / "checkpoint.json", state)
        save(output / "STOP.json", state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replacements", type=Path)
    parser.add_argument("--checker-ready", action="store_true")
    parser.add_argument("--jobs", type=int, choices=range(1, 6), default=5)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--execute-prepared", action="store_true")
    modes.add_argument("--job", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.prepare_only and not (args.replacements and args.checker_ready):
        parser.error("prepare requires --checker-ready and --replacements; wait for reviewed inputs")
    if not args.prepare_only and (args.replacements or args.checker_ready):
        parser.error("inputs are chosen only during prepare")
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    output = prior.checked_output(args.output)
    if args.prepare_only:
        prepare(output, args.replacements, args.jobs)
    elif args.job:
        require(bool(os.environ.get("INVOCATION_ID")), "worker must belong to the owning systemd service")
        job(output, args.job)
    else:
        execute(output)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"REMAINING5_STOP: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
