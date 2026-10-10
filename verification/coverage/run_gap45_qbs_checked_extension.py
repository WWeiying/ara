#!/usr/bin/env python3
"""Composable checked-extension hooks for qbs_gap45_context only."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import run_checked_extension as checked
import gap45_qbs_context_admission as admission

full = checked.full
SCRIPT = Path(__file__).resolve()
_installed = False


def perf_command(command):
    result = list(command)
    full.require(result.count("+TESTCASE=" + admission.NAME) == 1, "wrong PERF injection case")
    full.require(not any(s.startswith("+QBS_PERF") for s in result), "unexpected existing PERF option")
    return result + ["+QBS_PERF"]


def install_hooks():
    """Preserve the caller's SCRIPT and previously installed case handlers."""
    global _installed
    if _installed:
        return
    _installed = True
    prior_precheck = checked.evidence.precheck
    prior_worker = full.worker
    prior_summary = checked.summarize
    prior_directed = full.batch.directed

    def precheck(item, proof):
        if item.get("name") != "app:" + admission.NAME:
            return prior_precheck(item, proof)
        result = admission.precheck(item, proof)
        proof.pin(SCRIPT)
        proof.pin(Path(checked.__file__))
        return result

    def directed(output, name):
        if name != admission.NAME:
            return prior_directed(output, name)
        # Only this single-case directed subprocess uses the local launch hook.
        # The frozen runner has no extra-plusargs option and never adds QBS_PERF.
        from ara_verify import runner
        original = runner._run_monitored
        def monitored(command, work, console, timeout, cancel):
            full.require(timeout == 600, "QBS runtime budget is not 600 seconds")
            actual = perf_command(command)
            with (work / "gap45-command.json").open("x") as stream:
                json.dump(dict(command=actual, cwd=str(work), timeout_s=timeout), stream, indent=2)
            return original(actual, work, console, timeout, cancel)
        runner._run_monitored = monitored
        try:
            return prior_directed(output, name)
        finally:
            runner._run_monitored = original

    def worker(output, name):
        rc = prior_worker(output, name)
        if rc or name != admission.NAME:
            return rc
        path = output / "outcomes" / (name + ".json")
        row = full.read(path)
        if row["status"] != "PASS":
            return rc
        report = output / "results" / name / "gap45_runtime_audit.json"
        try:
            value = admission.runtime_proof(output, checked.frozen(output), row)
            full.require(json.loads(json.dumps(value)) == value, "unstable runtime JSON")
            full.save(report, value)
            row["files"].update(value["files"])
        except Exception as error:
            full.save(report, dict(status="REJECTED", reason=f"{type(error).__name__}: {error}"))
            row.update(status="INFRASTRUCTURE_ERROR", passed_only=False,
                       reason="gap45 extra admission rejected; retain first evidence")
            rc = 1
        row["files"].update(full.pins([report]))
        full.save(path, row)
        full.batch.publish(output, row)
        return rc

    def summarize(output, plan):
        for case in plan["cases"]:
            if case["name"] != admission.NAME:
                continue
            row = full.read(output / "outcomes" / (admission.NAME + ".json"))
            if row["status"] != "PASS":
                continue
            report = output / "results" / admission.NAME / "gap45_runtime_audit.json"
            full.require(str(report) in row["files"], "missing sealed QBS runtime proof")
            full.check({str(report): row["files"][str(report)]})
            saved = full.read(report)
            full.require(saved.get("status") == "PASS" and saved.get("schema") == admission.SCHEMA,
                         "bad QBS runtime proof")
            full.require(all(row["files"].get(p) == h for p, h in saved["files"].items()), "runtime file binding differs")
            full.check(saved["files"])
            full.require(admission.runtime_proof(output, plan, row) == saved, "QBS runtime replay differs")
        return prior_summary(output, plan)

    checked.evidence.precheck = precheck
    full.worker = worker
    checked.summarize = summarize
    full.batch.directed = directed


def main():
    checked.SCRIPT = SCRIPT
    install_hooks()
    return checked.main()


if __name__ == "__main__":
    raise SystemExit(main())
