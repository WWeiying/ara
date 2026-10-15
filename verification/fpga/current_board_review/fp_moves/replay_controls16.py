#!/usr/bin/env python3
"""Replay exactly ten M2 smokes and six M2 singles on the existing M3 image."""
import argparse
import csv
import filecmp
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent / "integration"
sys.path.insert(0, str(INTEGRATION))
import run as shared
from prepare import save, sha

M2 = Path("/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign")
M3 = Path("/home/wangwy/fpga_runs/current_board_memory_candidate03/campaign/image")
SINGLES = INTEGRATION / "memory_regression_plan02"
SMOKES = Path("/tmp/current-board-integration-smoke02/programs.json")
SUCCESS = "Core Test *** SUCCESS *** (tohost = 0)"


def read(path):
    return json.loads(path.read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def resources(out):
    process = subprocess.run(["/usr/bin/pgrep", "-a", "-x", "simv"],
                             capture_output=True, text=True)
    require(process.returncode in (0, 1), "Cannot inspect process capacity")
    lines = process.stdout.splitlines()
    external = [line for line in lines if str(out / "replay") not in line]
    reserve = max(0, 2 - sum("indexed_review" in x for x in external))
    reserve += max(0, 1 - sum("mask_alias_original" in x for x in external))
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(mem["MemAvailable"].split()[0]) * 1024
    # Reserve both own worker slots, including the interval before Popen.
    require(len(external) + reserve + 2 <= 24, "Global simv cap; refuse without polling")
    require(available >= 32 * 1024**3, "Memory floor; refuse without polling")
    return dict(time=time.time(), processes=lines, external_simv=len(external),
                reserved_unoccupied=reserve, own_slots=2, available_bytes=available)


def context():
    ledger = read(M3 / "image.json")
    require(sha(M3 / "image.json") ==
            "e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6", "Wrong M3 ledger")
    snapshot = Path(ledger["snapshot"])
    require(sha(snapshot / "snapshot.json") == ledger["snapshot_sha256"], "Snapshot drift")
    repo = shared.sealed(snapshot)
    framework = shared.framework(repo)
    simv = Path(ledger["simv"])
    require(framework[3](simv) == ledger["files"], "Image drift")
    require(sha(simv.parent / "simulator.conf") == ledger["configuration_sha256"], "Config drift")
    manifest = simv.parent / "vcs_source_manifest.json"
    require(sha(manifest) == ledger["manifest_sha256"], "Manifest drift")
    from ara_verify.vcs_source_manifest import collect
    captured = read(manifest)
    require(collect(Path(captured["filelist"]), repo,
                    [Path(p) for p in captured["extra_sources"]]) == captured["files"], "Source drift")
    import ara_verify.runner
    require(Path(ara_verify.runner.__file__).is_relative_to(repo), "Wrong runner")
    return ledger, repo, framework


def verify(pins):
    for path, digest in pins.items():
        require(sha(Path(path)) == digest, "Pin drift: " + path)


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    ledger, repo, _ = context()
    pins = dict(ledger["files"])

    def pin(path):
        pins[str(path)] = sha(path)
        return pins[str(path)]

    for path in (Path(__file__), INTEGRATION / "run.py", INTEGRATION / "prepare.py",
                 M2 / "plan.json", M2 / "image/image.json", M2 / "smokes/summary.json",
                 SINGLES / "plan.json", SINGLES / "complete.json", SINGLES / "replay/summary.json",
                 SMOKES, M3 / "image.json", Path(ledger["snapshot"]) / "snapshot.json",
                 Path(ledger["simv"]).parent / "simulator.conf",
                 Path(ledger["simv"]).parent / "vcs_source_manifest.json"):
        pin(path)
    pins.update({str(repo / name): digest for name, digest in
                 read(Path(ledger["snapshot"]) / "snapshot.json")["files"].items()})
    old_image = read(M2 / "image/image.json")
    pins.update(old_image["files"])
    old_snapshot = Path(old_image["snapshot"])
    pin(old_snapshot / "snapshot.json")
    pins.update({str(old_snapshot / "sources" / name): digest for name, digest in
                 read(old_snapshot / "snapshot.json")["files"].items()})
    stage = next(s for s in read(M2 / "plan.json")["stages"] if s["name"] == "smokes")
    programs = read(SMOKES)["programs"]
    specs = [("smokes", name, programs[name], M2 / "smokes", name) for name in stage["cases"]]
    singles = [c for c in read(SINGLES / "plan.json")["cases"] if c["group"] == "singles"]
    require(len(specs) == 10 and len(singles) == 6, "Wrong scope")
    require([c["original_name"] for c in singles] ==
            ["maskslide", "restart_compare", "reduction_fflags", "m8widen", "wholemove", "slide1up_prestart"],
            "Wrong singles")
    specs += [("singles", c["original_name"], c, SINGLES / "replay", c["id"]) for c in singles]
    cases = []
    (out / "inputs").mkdir()
    for group, name, entry, run, old_name in specs:
        old = run / "tests" / old_name
        observation = next(r for r in read(run / "summary.json") if r["name"] == old_name)
        require(observation["status"] == "PASS" and observation["returncode"] == 0, "M2 not PASS")
        for file in ("inputs.json", "console.log", "commit_trace.csv", "input.elf"):
            pin(old / file)
        require(read(old / "inputs.json")["simv"]["image_sha256"] == old_image["files"], "Wrong baseline image")
        require(sha(old / "input.elf") == entry["sha256"] ==
                read(old / "inputs.json")["binary"]["sha256"], "ELF mismatch")
        require(shared.oracle_complete(entry, (old / "console.log").read_text()), "Baseline oracle incomplete")
        identity = group + "__" + name
        elf = out / "inputs" / (identity + ".elf")
        shutil.copyfile(old / "input.elf", elf)
        elf.chmod(0o444)
        require(pin(elf) == entry["sha256"], "Copy mismatch")
        cases.append(dict(id=identity, original_name=name, group=group, elf=str(elf),
            sha256=entry["sha256"], pass_markers=entry["pass_markers"],
            baseline=str(old), observed_m2_s=observation["elapsed_s"], timeout_s=180))
    require(max(c["observed_m2_s"] for c in cases) * 2 < 180, "Budget basis changed")
    verify(pins)
    save(out / "plan.json", dict(cases=cases, pins=pins, image=str(M3), jobs=2,
        stop_first_fail=True, scope="M3 representative16; not M3 arithmetic38 or Linux closure",
        budget_basis="180s each exceeds twice all M2 observed times; outer1800s exceeds 16*180/2 plus validation",
        comparison="Entire cycle-bearing commit_trace.csv, byte-for-byte against actual M2 run"))


def run(out):
    plan = read(out / "plan.json")
    verify(plan["pins"])
    ledger, repo, (base, options_type, testcase, _) = context()
    entries = {c["id"]: c for c in plan["cases"]}
    save(out / "resources.json", resources(out))
    (out / "admission").mkdir()

    class ControlsRunner(base):
        def _run_test(self, test, image):
            try:
                save(out / "admission" / (test.name + ".json"), resources(out))
                result = super()._run_test(test, image)
                if result.status == "PASS":
                    console = (result.artifact_dir / "console.log").read_text()
                    if not shared.oracle_complete(entries[test.name], console) or SUCCESS not in console:
                        result.status, result.reason = "FAIL", "Original oracle incomplete"
                if result.status != "PASS":
                    self.cancel_event.set()
                return result
            except BaseException:
                self.cancel_event.set()
                raise

    tests = [testcase(c["id"], "app", "", Path(c["elf"]), c["original_name"], c["timeout_s"])
             for c in plan["cases"]]
    options = options_type(repo, out / "replay", "default", 2, 1, False,
                           False, True, Path(ledger["simv"]), True, None)
    started = time.time()
    results = ControlsRunner(options, tests, sys.argv).run()
    comparisons = []
    for result in results:
        entry = entries[result.name]
        old, new = Path(entry["baseline"]), result.artifact_dir
        inputs = read(new / "inputs.json")
        require(sha(new / "input.elf") == entry["sha256"] == inputs["binary"]["sha256"], "Runtime ELF mismatch")
        require(inputs["simv"]["image_sha256"] == ledger["files"], "Runtime image mismatch")
        trace = new / "commit_trace.csv"
        same = trace.is_file() and filecmp.cmp(old / "commit_trace.csv", trace, shallow=False)
        with trace.open() as stream:
            rows = sum(1 for _ in csv.DictReader(stream))
        console = (new / "console.log").read_text()
        comparisons.append(dict(name=result.name, status=result.status, returncode=result.returncode,
            elapsed_s=result.elapsed_s, complete_trace_equal=same, trace_rows=rows,
            old_trace_sha256=sha(old / "commit_trace.csv"), trace_sha256=sha(trace),
            oracle_complete=shared.oracle_complete(entry, console) and SUCCESS in console,
            console_sha256=sha(new / "console.log"), inputs_sha256=sha(new / "inputs.json")))
    verify(plan["pins"])
    context()
    passed = len(results) == 16 and all(c["status"] == "PASS" and c["returncode"] == 0 and
              c["oracle_complete"] and c["complete_trace_equal"] for c in comparisons)
    save(out / "complete.json", dict(status="PASS_16_M3_TRACE_IDENTICAL_M2" if passed else "NOT_PASS",
        started=started, finished=time.time(), elapsed_s=time.time()-started, jobs=2,
        plan_sha256=sha(out / "plan.json"), pins_unchanged=True, pin_count=len(plan["pins"]),
        comparisons=comparisons, no_build=True, no_rtl_edits=True, scope=plan["scope"]))
    print("PASS_16_M3_TRACE_IDENTICAL_M2" if passed else "NOT_PASS", flush=True)
    return int(not passed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.is_relative_to(HERE) and out != HERE, "Output must be a fresh owned directory")
    env = shared.environment()
    os.environ.clear()
    os.environ.update(env)
    if args.mode == "prepare":
        prepare(out)
    else:
        try:
            sys.exit(run(out))
        except Exception as error:
            save(out / "error.json", dict(error=str(error), finished=time.time()))
            raise
