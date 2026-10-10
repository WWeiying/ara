#!/usr/bin/env python3
"""Bound local-row recalculate/update investigation, never a full-corpus run."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import probe_operand_root_events as prior

runner = prior.runner
HERE = prior.HERE
runner.HOOK = HERE / "probe_operand_root_update.tcl"
PREVIOUS = runner.app.OUT / "operand-root-events-single-20261006-01/diagnostic-result.json"
PREVIOUS_SHA = "ff3321c88b62d90f7d812fb9ebc240a6454861974375d096b67dbb138c94386c"


def verify(output, config):
    scopes = ["ara_tb", "ara_tb.dut.i_ara_soc.i_system", "ara_tb.dut.i_ara_soc.i_system.i_ara"]
    scopes += [list(config["plan"]["scopes"])[i] for i in (0, 4)]
    plan = dict(config["plan"], scopes={s: config["plan"]["scopes"][s] for s in scopes[3:]})
    identities = None
    for stage, mode in (("raw", "before"), ("applied", "selected"), ("after", "selected"), ("final", "final")):
        identities = runner.app.native.states(output / ("subset_" + stage + ".tsv"), plan, mode, identities)
    expected = runner.app.native.parse_native((runner.previous.SOURCE / "applied.el").read_bytes())
    for name in ("event-applied.el", "event-after.el"):
        runner.app.require(runner.app.native.parse_native((output / name).read_bytes()) == expected, "Native targets differ")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    runner.app.require(log.splitlines().count("OPH6_ROOT_UPDATE_PROBE_DONE") == 1, "Probe incomplete")
    roots = prior.read_rows(output / "root-identities.tsv")
    keys = {(r["scope"], r["stage"]) for r in roots}
    runner.app.require(len(roots) == 15 and keys == {(s, t) for s in scopes for t in ("rooted", "recalculate", "update")},
                       "Root binding matrix differs")
    for row in roots:
        runner.app.require(row["path"] == row["name"] == row["scope"].rsplit(".", 1)[-1] and row["handle"],
                           "Root local path contract differs")
    rows = prior.read_rows(output / "observations.tsv")
    observed = {(r["scope"], r["stage"], r["metric"]): r for r in rows}
    metrics = {r["metric"] for r in rows}
    stages = ("raw", "rooted", "recalculate", "update")
    runner.app.require(len(observed) == len(rows) and set(observed) ==
                       {(s, t, m) for s in scopes for t in stages for m in metrics} and {"Branch", "Score"} <= metrics,
                       "Observation matrix incomplete")
    for root in roots:
        for metric in metrics:
            runner.app.require(observed[(root["scope"], root["stage"], metric)]["token"] == root["handle"],
                               "Observation handle not root-bound")
    return dict(status="SINGLE_TEST_ROOT_UPDATE_DIAGNOSTIC_VERIFIED_NOT_APPLICATION_REPORT", tests=1,
                native_records=1144, audited_coordinates=202, reset_verified=True,
                values=[dict(scope=s, metric=m, values={t: observed[(s, t, m)]["value"] for t in stages})
                        for s in scopes for m in ("Branch", "Score")],
                limitation="Not a refreshed690/699 report; this run only compares one historical test.")


def main():
    output = Path(sys.argv[1]).absolute()
    runner.app.require(runner.app.native.hash_file(PREVIOUS) == PREVIOUS_SHA, "Previous diagnostic seal differs")
    saved = json.loads(PREVIOUS.read_text())
    runner.app.require(saved["dependencies_unchanged"] is True, "Previous dependencies not verified")
    for pins in (saved["files"], saved["dependency_pins"]):
        for path, sha in pins.items():
            runner.app.require(runner.app.native.hash_file(path) == sha, "Previous evidence changed")
    paths = [Path(__file__), runner.HOOK, HERE / "test_probe_operand_root_update.py", PREVIOUS,
             HERE / "probe_operand_root_events.tcl", HERE / "probe_operand_root_events.py",
             HERE / "diagnose_operand_hierarchy_v2.py", HERE / "diagnose_operand_hierarchy_v2.tcl",
             HERE / "diagnose_operand_hierarchy_v4.tcl"]
    pins = {str(p): runner.app.native.hash_file(p) for p in paths}
    result = dict(status="FAILED")
    try:
        runner.run("pilot", output)
        source = runner.app.read_config(runner.previous.SOURCE, runner.previous.SEAL)
        result.update(verify(output, source))
    except Exception as error:
        result["reason"] = str(error)
        raise
    finally:
        unchanged = all(runner.app.native.hash_file(p) == sha for p, sha in pins.items())
        result.update(dependencies_unchanged=unchanged, dependency_pins=pins, previous_diagnostic_sha256=PREVIOUS_SHA)
        if output.exists():
            files = [p for p in output.iterdir() if p.is_file() and p.name != "root-update-result.json"]
            log = output / "DVEfiles/dve_gui.log"
            if log.exists():
                files.append(log)
            result["files"] = {str(p): runner.app.native.hash_file(p) for p in files}
            runner.app.native.write(output / "root-update-result.json", result)
        runner.app.require(unchanged, "Diagnostic dependencies changed")


if __name__ == "__main__":
    main()
