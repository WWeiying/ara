#!/usr/bin/env python3
"""One-test diagnostic only, bound to the retained690 partial observations."""
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import diagnose_operand_hierarchy_v2 as runner

HERE = Path(__file__).resolve().parent
runner.HOOK = HERE / "probe_operand_root_events.tcl"
PARTIAL = runner.app.OUT / "operand-hierarchy-compare-690-20261006-02/partial-observation-evidence.json"
PARTIAL_SEAL = "eb02f388d9bda0b64c4dca84aa96156a9ea021d210983ca1c39d53dfaf05f07c"


def read_rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def verify(output, source):
    plan = source["plan"]
    targets = list(plan["scopes"])
    scopes = ["ara_tb", "ara_tb.dut.i_ara_soc.i_system", "ara_tb.dut.i_ara_soc.i_system.i_ara", targets[0], targets[4]]
    contract = read_rows(output / "root-contract.tsv")
    runner.app.require({r["request"] for r in contract} == set(scopes) and all(r["handle"] for r in contract), "Root dump incomplete")
    subset = dict(plan, scopes={s: plan["scopes"][s] for s in scopes[3:]})
    identities = None
    for stage, expected in (("raw", "before"), ("applied", "selected"), ("final", "final")):
        identities = runner.app.native.states(output / ("subset_" + stage + ".tsv"), subset, expected, identities)
    expected = runner.app.native.parse_native((runner.previous.SOURCE / "applied.el").read_bytes())
    for name in ("event-applied.el", "event-after.el"):
        runner.app.require(runner.app.native.parse_native((output / name).read_bytes()) == expected, "Exact native set differs")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    runner.app.require(log.splitlines().count("OPH5_ROOT_EVENT_PROBE_DONE") == 1, "Incomplete event probe")
    observations = read_rows(output / "observations.tsv")
    stages = ("raw", "immediate_a", "immediate_b", "events_100", "events_200")
    got = {}
    for row in observations:
        key = row["scope"], row["stage"], row["metric"]
        runner.app.require(key not in got, "Duplicate observation")
        got[key] = row
    metrics = {r["metric"] for r in observations}
    runner.app.require(set(got) == {(s, t, m) for s in scopes for t in stages for m in metrics} and
                       {"Branch", "Score"} <= metrics, "Observation matrix incomplete")
    summary = []
    for scope in scopes:
        for metric in ("Branch", "Score"):
            rows = [got[(scope, stage, metric)] for stage in stages]
            runner.app.require(len({r["token"] for r in rows}) == 1, "Handle differs")
            summary.append(dict(scope=scope, metric=metric, values={stage: row["value"] for stage, row in zip(stages, rows)}))
    return dict(status="SINGLE_TEST_ROOT_EVENT_DIAGNOSTIC_VERIFIED_NOT_APPLICATION_REPORT", tests=1,
                root_contract_rows=len(contract), native_records=1144, audited_coordinates=202,
                final_reset=True, observations=summary,
                root_top_rows=[r for r in contract if r["depth"] == "0"],
                limitation="Only one historical test; not a refreshed690/692 hierarchy report. Events versus elapsed time not fully isolated.")


def main():
    output = Path(sys.argv[1]).absolute()
    runner.app.require(runner.app.native.hash_file(PARTIAL) == PARTIAL_SEAL, "Partial evidence seal differs")
    evidence = json.loads(PARTIAL.read_text())
    for path, sha in evidence["files"].items():
        runner.app.require(runner.app.native.hash_file(path) == sha, "Partial evidence input differs")
    paths = [Path(__file__), runner.HOOK, HERE / "test_probe_operand_root_events.py", PARTIAL,
             HERE / "diagnose_operand_hierarchy_v2.py", HERE / "diagnose_operand_hierarchy_v2.tcl",
             HERE / "diagnose_operand_hierarchy_v4.tcl"]
    pins = {str(p): runner.app.native.hash_file(p) for p in paths}
    diagnostic = dict(status="FAILED")
    try:
        runner.run("pilot", output)
        source = runner.app.read_config(runner.previous.SOURCE, runner.previous.SEAL)
        diagnostic.update(verify(output, source))
    except Exception as error:
        diagnostic["reason"] = str(error)
        raise
    finally:
        unchanged = all(runner.app.native.hash_file(p) == sha for p, sha in pins.items())
        diagnostic.update(dependencies_unchanged=unchanged, dependency_pins=pins, partial_evidence_sha256=PARTIAL_SEAL)
        if output.exists():
            diagnostic["files"] = {str(p): runner.app.native.hash_file(p) for p in output.iterdir()
                                   if p.is_file() and p.name != "diagnostic-result.json"}
            gui = output / "DVEfiles/dve_gui.log"
            if gui.exists():
                diagnostic["files"][str(gui)] = runner.app.native.hash_file(gui)
            runner.app.native.write(output / "diagnostic-result.json", diagnostic)
        runner.app.require(unchanged, "Diagnostic dependency differs")


if __name__ == "__main__":
    main()
