#!/usr/bin/env python3
"""Root/recalculate comparison with explicit non-success update diagnostics."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import probe_operand_root_update as base

runner = base.runner
HERE = base.HERE
runner.HOOK = HERE / "probe_operand_root_update_v2.tcl"
FAILED = runner.app.OUT / "operand-root-update-single-20261006-01"


def main():
    output = Path(sys.argv[1]).absolute()
    runner.app.require(json.loads((FAILED / "root-update-result.json").read_text())["status"] == "FAILED",
                       "Original API failure must remain")
    paths = [Path(__file__), runner.HOOK, HERE / "test_probe_operand_root_update_v2.py",
             HERE / "probe_operand_root_update.py", HERE / "probe_operand_root_update.tcl",
             HERE / "probe_operand_root_events.py", HERE / "probe_operand_root_events.tcl",
             HERE / "diagnose_operand_hierarchy_v2.py", HERE / "diagnose_operand_hierarchy_v2.tcl",
             HERE / "diagnose_operand_hierarchy_v4.tcl"]
    paths += [FAILED / name for name in ("config.json", "status.json", "root-update-result.json", "DVEfiles/dve_gui.log")]
    pins = {str(p): runner.app.native.hash_file(p) for p in paths}
    runner.app.require(runner.app.native.hash_file(base.PREVIOUS) == base.PREVIOUS_SHA, "Prior contract seal differs")
    previous = json.loads(base.PREVIOUS.read_text())
    for hashes in (previous["files"], previous["dependency_pins"]):
        for path, sha in hashes.items():
            runner.app.require(runner.app.native.hash_file(path) == sha, "Prior contract artifact differs")
    result = dict(status="FAILED")
    try:
        runner.run("pilot", output)
        config = runner.app.read_config(runner.previous.SOURCE, runner.previous.SEAL)
        result.update(base.verify(output, config))
        updates = base.prior.read_rows(output / "update-attempts.tsv")
        scopes = {r["scope"] for r in result["values"]}
        runner.app.require(len(updates) == 5 and {r["scope"] for r in updates} == scopes and
                           all(r["catch_code"] in ("0", "1") for r in updates), "Update diagnostic incomplete")
        failed = [r for r in updates if r["catch_code"] != "0"]
        result.update(status="SINGLE_TEST_ROOT_RECALCULATE_DIAGNOSTIC_VERIFIED_NOT_REPORT",
                      update_attempts=updates, update_api_success_for_all_scopes=not failed,
                      limitation="Update-stage values are reads after attempted update, not proof update succeeded. No690/699 report qualification.")
    except Exception as error:
        result.update(status="FAILED", reason=str(error))
        raise
    finally:
        unchanged = all(runner.app.native.hash_file(path) == sha for path, sha in pins.items())
        result.update(dependencies_unchanged=unchanged, dependency_pins=pins, previous_diagnostic_sha256=base.PREVIOUS_SHA)
        if output.exists():
            files = [p for p in output.iterdir() if p.is_file() and p.name != "root-update-result.json"]
            gui = output / "DVEfiles/dve_gui.log"
            if gui.exists():
                files.append(gui)
            result["files"] = {str(p): runner.app.native.hash_file(p) for p in files}
            runner.app.native.write(output / "root-update-result.json", result)
        runner.app.require(unchanged, "Probe dependency changed")


if __name__ == "__main__":
    main()
