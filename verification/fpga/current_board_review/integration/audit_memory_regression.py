#!/usr/bin/env python3
"""Read-only audit of the approved candidate02 arithmetic replay."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
PLAN = ROOT / "memory_regression_plan02"
APPROVED = "1410586ddc6e00f7c55239f807497d214c1802c5727dbfb1e0ec1d684841a3bd"


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    plan = read(PLAN / "plan.json")
    launch = read(PLAN / "launch.json")
    complete = read(PLAN / "complete.json")
    summary = read(PLAN / "replay/summary.json")
    run = read(PLAN / "replay/run.json")
    assert sha(PLAN / "plan.json") == APPROVED
    assert launch["plan_sha256"] == complete["plan_sha256"] == APPROVED
    assert complete["status"] == "PASS_38_CANDIDATE02"
    assert run["status"] == "COMPLETE" and run["status_counts"] == {"PASS": 38}
    assert launch["jobs"] == plan["jobs"] == run["jobs"] == 4
    assert plan["stop_first_fail"]
    image_path = Path(plan["image"]) / "image.json"
    image = read(image_path)
    assert sha(image_path) == plan["image_sha256"] == complete["image_sha256"]
    snapshot_path = Path(image["snapshot"]) / "snapshot.json"
    snapshot = read(snapshot_path)
    assert sha(snapshot_path) == plan["snapshot_sha256"] == image["snapshot_sha256"]
    checked = {}
    maps = [plan["pins"], launch["gate_pins"], image["files"],
            {str(Path(snapshot["root"]) / p): h for p, h in snapshot["files"].items()}]
    for pins in maps:
        for path, expected in pins.items():
            if path not in checked:
                checked[path] = sha(path)
            assert checked[path] == expected, path
    gate = read(plan["gates"]["extended8"])
    assert gate["status"] == "CANDIDATE02_EXTENDED8_PASS"
    assert gate["post_hashes"] == "ALL_PRE_RUN_PINS_AND_IMAGE_UNCHANGED"
    assert gate["image_sha256"] == plan["image_sha256"]
    ids = [c["id"] for c in plan["cases"]]
    assert len(ids) == len(set(ids)) == 38
    assert ids == [r["name"] for r in complete["results"]]
    assert set(ids) == {r["name"] for r in summary} and len(summary) == 38
    results = {r["name"]: r for r in summary}
    evidence = []
    for case, terminal in zip(plan["cases"], complete["results"]):
        result = results[case["id"]]
        assert terminal["status"] == result["status"] == "PASS"
        assert result["returncode"] == 0 and not result["reason"]
        assert terminal["elapsed_s"] == result["elapsed_s"] < case["timeout_s"]
        artifact = Path(result["artifact_dir"])
        inputs = read(artifact / "inputs.json")
        assert inputs["binary"]["sha256"] == case["sha256"]
        for path in [case["elf"], case["original_elf"], artifact / "input.elf"]:
            assert sha(path) == case["sha256"], str(path)
        assert inputs["simv"]["image_sha256"] == image["files"]
        assert inputs["simv"]["path"] == image["simv"] == plan["simv"]
        command = read(artifact / "command.json")["command"]
        assert command[0] == image["simv"]
        assert "+TESTCASE=" + case["original_name"] in command
        logs = [artifact / "console.log", artifact / "work/run.vcs.log"]
        for path in logs:
            log = path.read_text()
            assert all(marker in log for marker in case["pass_markers"]), str(path)
            assert "Core Test *** SUCCESS *** (tohost = 0)" in log
            assert not re.search(r"\b(?:FAIL|FAILED|SKIP|FATAL)\b", log)
        row = dict(id=case["id"], status="PASS", elapsed_s=result["elapsed_s"],
                   elf_sha256=case["sha256"], oracle_markers=case["pass_markers"],
                   evidence_sha256={str(p): sha(p) for p in logs + [
                       artifact / "inputs.json", artifact / "command.json"]})
        if case["group"] == "extension-matrix":
            log = logs[0].read_text()
            trials = list(map(int, re.findall(r"^EXTENSION_TRIAL (\d+)$", log, re.M)))
            assert trials == list(range(24))
            trace = artifact / "commit_trace.csv"
            stores = []
            with trace.open() as f:
                for event in csv.DictReader(f):
                    if event["event"] == "retire" and event["insn"].lower().removeprefix("0x") in {
                            "22858c27", "62858c27", "e2858c27"}:
                        stores.append(int(event["cycle"]))
            assert len(stores) == 24, (case["id"], len(stores))
            row.update(trials=trials, whole_store_retire_cycles=stores,
                       commit_trace_sha256=sha(trace))
        evidence.append(row)
    return dict(status="INDEPENDENT_CANDIDATE02_38_PASS", plan_sha256=APPROVED,
                image_sha256=plan["image_sha256"], snapshot_sha256=plan["snapshot_sha256"],
                plan_pin_count=len(plan["pins"]), gate_pin_count=len(launch["gate_pins"]),
                snapshot_file_count=len(snapshot["files"]), unique_pins_checked=len(checked),
                pin_mismatches=0, extension_subcases=144, extension_readback_retires=144,
                groups=dict(collections.Counter(c["group"] for c in plan["cases"])),
                terminal_evidence_sha256={str(PLAN / p): sha(PLAN / p) for p in [
                    "complete.json", "launch.json", "replay/run.json", "replay/summary.json"]},
                scope="Fresh candidate02 SoC runs, not transferred final04 PASS; no Linux or general performance claim",
                results=evidence)


if __name__ == "__main__":
    finding = main()
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as f:
        json.dump(finding, f, indent=2)
        f.write("\n")
    print(json.dumps({k: v for k, v in finding.items() if k not in {"results", "terminal_evidence_sha256"}}, indent=2))
