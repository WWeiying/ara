#!/usr/bin/env python3
"""Seal partial UI observations without promoting a failed probe to a report."""
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import diagnose_operand_hierarchy as original

app = original.app


def summarize(output):
    config = app.read_config(original.SOURCE, original.SEAL)
    app.require(app.native.hash_file(original.SOURCE / "application-result.json") == original.RESULT_SEAL,
                "Original application result differs")
    result = json.loads((original.SOURCE / "application-result.json").read_text())
    for path, sha in result["files"].items():
        app.require(app.native.hash_file(path) == sha, "Original artifact differs")
    status = json.loads((output / "status.json").read_text())
    app.require(status["status"] == "FAILED", "This summarizer only handles the retained failed probe")
    probe = json.loads((output / "config.json").read_text())
    app.require(probe["mode"] == "full" and probe["source_config_sha256"] == original.SEAL, "Wrong corpus")
    dependency = json.loads((output / "dependency-verification.json").read_text())
    app.require(dependency["unchanged"] is True, "Dependency integrity not confirmed")
    for pins in (probe["pins"], dependency["pins"]):
        for path, sha in pins.items():
            app.require(app.native.hash_file(path) == sha, "Probe dependency differs")
    app.require((output / "selected_tests.txt").read_text().splitlines() == config["selected_tests"], "Not exact690")
    identities = None
    for stage, expected in (("raw", "before"), ("applied", "selected"), ("final", "final")):
        identities = app.native.states(output / ("states_" + stage + ".tsv"), config["plan"], expected, identities)
    app.require(app.native.parse_native((output / "applied-before.el").read_bytes()) ==
                app.native.parse_native((original.SOURCE / "applied.el").read_bytes()), "Native set differs")
    for name in ("initial-empty.el", "final-empty.el"):
        app.require((output / name).read_bytes() == b"", "Empty exclusion verification differs")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    app.require("OPH2_FAILED Scope not found: ara_tb.dut.i_ara_soc.i_system" in log and
                "OPH2_CLEANUP_ERROR" not in log and "OP1144_AUDIT final 3636" in log,
                "Failure/cleanup evidence differs")
    with (output / "observations.tsv").open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    observed = {}
    for row in rows:
        key = (row["stage"], row["scope"], row["metric"])
        app.require(key not in observed, "Duplicate observation")
        observed[key] = row
    raw = app.summaries(original.SOURCE / "summary_raw.csv")
    applied = app.summaries(original.SOURCE / "summary_applied.csv")
    scopes = ["ara_tb", "ara_tb.dut.i_ara_soc.i_system", "ara_tb.dut.i_ara_soc.i_system.i_ara"]
    scopes += [list(config["plan"]["scopes"])[i] for i in (0, 4)]
    changes = []
    for scope in scopes:
        for metric in ("Branch", "Score"):
            records = [observed[(stage, scope, metric)] for stage in
                       ("raw_percent", "raw_ratio", "applied_percent", "applied_ratio")]
            app.require(len({r["token"] for r in records}) == 1, "Not the same actual table handle")
            app.require(records[0]["value"] == records[1]["value"] == raw[scope][metric] and
                        records[2]["value"] == applied[scope][metric], "Independent690 reference differs")
            app.require(all(r["value"].endswith("%") for r in records), "Unexpected display semantics")
            if records[2]["value"] != records[3]["value"]:
                changes.append(dict(scope=scope, metric=metric, handle=records[2]["token"],
                                    first_applied_read=records[2]["value"],
                                    after_display_switch_and_events=records[3]["value"]))
    app.require(bool(changes), "No delayed observation change")
    files = [Path(__file__), output / "config.json", output / "status.json", output / "dependency-verification.json",
             output / "observations.tsv", output / "selected_tests.txt", output / "applied-before.el",
             output / "initial-empty.el", output / "final-empty.el", output / "DVEfiles/dve_gui.log"]
    files += [output / ("states_" + stage + ".tsv") for stage in ("raw", "applied", "final")]
    evidence = dict(status="PARTIAL_UI_REFRESH_OBSERVATION_NOT_APPLICATION_REPORT", original_probe_status="FAILED",
                    source_config_sha256=original.SEAL, source_result_sha256=original.RESULT_SEAL,
                    tests=690, targets_verified_before_probe=1144, protected_verified_before_probe=2492,
                    final_reset_and_all_states_verified=True, post_probe_applied_audit_available=False,
                    changes=changes, actual_ratio_counts_available=False,
                    limitation="Ratio-labelled stages still returned percent; display toggle versus event processing not isolated. Root comparison incomplete.",
                    files={str(path): app.native.hash_file(path) for path in files})
    destination = output / "partial-observation-evidence.json"
    app.require(not destination.exists(), "Never overwrite earlier evidence")
    app.native.write(destination, evidence)
    print(json.dumps(evidence, indent=2))
    print("EVIDENCE_SHA256 " + app.native.hash_file(destination))


if __name__ == "__main__":
    summarize(Path(sys.argv[1]).absolute())
