#!/usr/bin/env python3
"""Replay the accepted 38 unchanged programs on the frozen candidate04 image."""
import argparse
from collections import Counter
import copy
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import replay_memory_regression as base

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent
PREVIOUS = HERE / "memory_regression_plan02"
IMAGE = Path("/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image")
AUDIT = REVIEW / "comparison_alias_original/candidate04_audit02/finding.json"
FP = REVIEW / "comparison_source_controls/vcs_candidate04_01/complete.json"
IMAGE_SHA = "e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673"
LANE_SHA = "dfda48c8f3c9c1a1f0f41499a48b890cfaa112eb822f702ed8738fe3ae3705fa"
JOBS = 4


def gates(previous, terminal, audit, floating):
    base.require(terminal.get("status") == "PASS_38_CANDIDATE02", "Previous38 not accepted")
    cases = previous["cases"]
    names = {c["id"] for c in cases}
    results = terminal["results"]
    base.require(len(cases) == len(names) == len(results) == 38, "Wrong38 membership")
    base.require({x["name"] for x in results} == names and
                 all(x["status"] == "PASS" for x in results), "Previous38 incomplete")
    base.require(dict(Counter(c["group"] for c in cases)) == base.GROUPS, "Wrong38 groups")
    base.require(audit.get("status") == "INDEPENDENT_PASS_19_PLUS_16" and
                 audit.get("counts") == dict(first=1, remaining18=18, smokes=10, singles=6),
                 "Current35 not independently accepted")
    base.require(len(audit["tests"]) == 35 and
                 all(x["status"] == "PASS" and x["returncode"] == 0 for x in audit["tests"]),
                 "Current35 incomplete")
    base.require(floating.get("status") == "PASS_3_SAME_ELF_CANDIDATE04",
                 "Current FP source controls not accepted")


def identity():
    base.require(base.sha(IMAGE / "image.json") == IMAGE_SHA, "Wrong frozen candidate04")
    base.IMAGE = IMAGE
    ledger, repo, framework = base.image_context()
    snapshot = Path(ledger["snapshot"])
    base.require(base.read(snapshot / "snapshot.json")["files"]
                 ["hardware/src/lane/lane_sequencer.sv"] == LANE_SHA, "Wrong source-origin repair")
    return ledger, repo, framework


def resources(out):
    result = subprocess.run(["/usr/bin/pgrep", "-a", "-x", "simv"],
                            capture_output=True, text=True, check=False)
    base.require(result.returncode in (0, 1), "Cannot inventory simulators")
    lines = result.stdout.splitlines()
    external = [x for x in lines if str(out) not in x]
    reserve = max(0, 2 - sum("indexed_review" in x for x in external))
    memory = dict(x.split(":", 1) for x in Path("/proc/meminfo").read_text().splitlines())
    available = int(memory["MemAvailable"].split()[0]) * 1024
    base.require(len(external) + reserve + JOBS <= 24, "No capacity; refused without retry")
    base.require(available >= 32 * 1024**3, "Memory floor not satisfied")
    return dict(time=time.time(), processes=lines, external=len(external),
                reserved_nf7=reserve, own_jobs=JOBS, available_bytes=available)


def prepare(out):
    previous = base.read(PREVIOUS / "plan.json")
    terminal = base.read(PREVIOUS / "complete.json")
    gates(previous, terminal, base.read(AUDIT), base.read(FP))
    base.verify_pins(previous["pins"])
    ledger, repo, _ = identity()
    pins = dict(previous["pins"])
    pins.update(ledger["files"])
    snapshot = Path(ledger["snapshot"])
    pins.update({str(repo / name): digest for name, digest in
                 base.read(snapshot / "snapshot.json")["files"].items()})
    for path in (Path(__file__).resolve(), PREVIOUS / "plan.json", PREVIOUS / "complete.json",
                 AUDIT, FP, IMAGE / "image.json", snapshot / "snapshot.json",
                 Path(ledger["simv"]).parent / "simulator.conf",
                 Path(ledger["simv"]).parent / "vcs_source_manifest.json"):
        pins[str(path)] = base.sha(path)
    for case in previous["cases"]:
        base.require(base.sha(Path(case["elf"])) == case["sha256"], "Original ELF drift")
        base.require(case["pass_markers"] and case["timeout_s"] > 0, "Missing oracle/budget")
    out.mkdir(parents=True, exist_ok=False)
    data = dict(schema_version=1, image=str(IMAGE), image_sha256=IMAGE_SHA,
                snapshot_sha256=ledger["snapshot_sha256"], jobs=JOBS, stop_first_fail=True,
                cases=copy.deepcopy(previous["cases"]), pins=pins,
                gates=dict(previous38=str(PREVIOUS / "complete.json"),
                           current35=str(AUDIT), fp3=str(FP)),
                scope="Current candidate04 replay of the unchanged accepted38, not all historical/Linux records",
                changes="Image/output only; same38 ELF, oracle, individual budgets and four jobs",
                status="PREPARED_NOT_LAUNCHED")
    base.save(out / "plan.json", data)
    dry = base.execute(data, out / "dryrun", True)
    base.require(len(dry) == 38 and all(x.status == "DRY_RUN" for x in dry), "Dry-run unexpected")
    base.verify_pins(pins)
    base.save(out / "preflight.json", dict(status="PASS_PREPARE_ONLY", cases=38,
              jobs=JOBS, VCS_started=False, plan_sha256=base.sha(out / "plan.json"),
              timeout_sum_s=sum(x["timeout_s"] for x in data["cases"]),
              max_case_timeout_s=max(x["timeout_s"] for x in data["cases"])))
    print("READY_NOT_LAUNCHED " + base.sha(out / "plan.json"), flush=True)


def work(out, approved, authorized):
    base.require(authorized and approved == base.sha(out / "plan.json"), "Unapproved launch")
    data = base.read(out / "plan.json")
    base.require(data["image_sha256"] == IMAGE_SHA and data["jobs"] == JOBS and
                 data["stop_first_fail"], "Launch contract changed")
    base.verify_pins(data["pins"])
    previous = base.read(PREVIOUS / "plan.json")
    gates(previous, base.read(PREVIOUS / "complete.json"), base.read(AUDIT), base.read(FP))
    base.require(data["cases"] == previous["cases"], "Case/oracle/budget changed")
    identity()
    with (out / "launch.json").open("x") as stream:
        import json
        json.dump(dict(pid=os.getpid(), time=time.time(), plan_sha256=approved,
                       admission=resources(out)), stream, indent=2)
    original_runner = base.runner_class

    def admitted_runner(parent, entries):
        checked = original_runner(parent, entries)

        class Runner(checked):
            def _run_test(self, test, image):
                if not self.cancel_event.is_set():
                    try:
                        base.save(out / "admission" / (test.name + ".json"), resources(out))
                    except BaseException:
                        self.cancel_event.set()
                        raise
                return super()._run_test(test, image)
        return Runner

    base.runner_class = admitted_runner
    try:
        results = base.execute(data, out / "replay", False)
        base.verify_pins(data["pins"])
        identity()
        passed = len(results) == 38 and all(x.status == "PASS" and x.returncode == 0 for x in results)
        base.save(out / "complete.json", dict(status="PASS_38_CANDIDATE04" if passed else "NOT_PASS",
            plan_sha256=approved, image_sha256=IMAGE_SHA, pins_unchanged=True,
            results=[dict(name=x.name, status=x.status, returncode=x.returncode,
                          elapsed_s=x.elapsed_s, reason=x.reason) for x in results],
            finished=time.time(), scope=data["scope"]))
        return int(not passed)
    except BaseException as error:
        base.save(out / "complete.json", dict(status="ERROR_NOT_PASS", error=str(error),
                                              finished=time.time()))
        raise


def self_test():
    import unittest

    class Tests(unittest.TestCase):
        def test_acceptance_and_scope(self):
            previous = base.read(PREVIOUS / "plan.json")
            terminal = base.read(PREVIOUS / "complete.json")
            audit, floating = base.read(AUDIT), base.read(FP)
            gates(previous, terminal, audit, floating)
            for field, source in (("terminal", terminal), ("audit", audit), ("floating", floating)):
                changed = copy.deepcopy(source)
                changed["status"] = "RUNNING"
                args = [previous, terminal, audit, floating]
                args[{"terminal": 1, "audit": 2, "floating": 3}[field]] = changed
                with self.assertRaises(ValueError):
                    gates(*args)
            changed = copy.deepcopy(previous)
            changed["cases"].pop()
            with self.assertRaises(ValueError):
                gates(changed, terminal, audit, floating)

        def test_no_unapproved_simulation(self):
            with self.assertRaises(ValueError):
                work(Path("/not-a-run"), None, False)

    base.self_test()
    base.require(unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
                 .wasSuccessful(), "Candidate04 host tests failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "work", "self-test"])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--approved-plan-sha256")
    parser.add_argument("--authorize-run", action="store_true")
    args = parser.parse_args()
    if args.mode == "self-test":
        self_test()
        return 0
    base.require(args.out is not None, "--out required")
    environment = base.shared.environment()
    os.environ.clear()
    os.environ.update(environment)
    out = base.owned(args.out)
    if args.mode == "prepare":
        prepare(out)
        return 0
    return work(out, args.approved_plan_sha256, args.authorize_run)


if __name__ == "__main__":
    raise SystemExit(main())
