#!/usr/bin/env python3
"""Composable gap54 gates; only standalone main assigns checked.SCRIPT."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import gap54_akv_admission as admission
import run_checked_extension as checked

SCRIPT = Path(__file__).resolve()
full = checked.full
_HOOKS = None


def perf_command(command):
    require = admission.require
    command = list(command)
    require([x for x in command if x.startswith("+TESTCASE=")] == ["+TESTCASE="+admission.NAME],
            "PERF injection is gap54-only")
    require(not any(x.startswith("+AKV_PERF") for x in command), "unexpected existing AKV_PERF option")
    require(command.count("+NO_FSDB") == 1, "bounded no-FSDB profile required")
    return command + ["+AKV_PERF"]


def install_hooks():
    """Call after parent defaults; delegate all other cases and preserve SCRIPT."""
    global _HOOKS
    if _HOOKS is not None:
        return _HOOKS
    old_precheck,old_worker = checked.evidence.precheck,full.worker
    old_summary,old_directed = checked.summarize,full.batch.directed

    def precheck(item, proof):
        if item.get("name") != admission.TEST:
            return old_precheck(item,proof)
        return admission.precheck(item,proof)

    def directed(output, name):
        if name != admission.NAME:
            return old_directed(output,name)
        from ara_verify import runner
        original = runner._run_monitored
        def monitored(command, work, console, timeout, cancel):
            admission.require(timeout == 600, "exact 600-second simulator limit required")
            actual = perf_command(command)
            with (work / "gap54-command.json").open("x") as stream:
                json.dump(dict(command=actual,cwd=str(work),timeout_s=timeout),stream,indent=2)
            return original(actual,work,console,timeout,cancel)
        runner._run_monitored = monitored
        try:
            return old_directed(output,name)
        finally:
            runner._run_monitored = original

    def worker(output, name):
        rc = old_worker(output,name)
        if rc or name != admission.NAME:
            return rc
        path = output / "outcomes" / (name+".json")
        row = full.read(path)
        if row["status"] != "PASS":
            return rc
        report = output / "results" / name / "gap54_runtime_audit.json"
        try:
            value = admission.runtime_proof(output,checked.frozen(output),row)
            admission.require(json.loads(json.dumps(value)) == value, "runtime JSON must round-trip exactly")
            full.save(report,value)
            row["files"].update(value["files"])
        except Exception as error:
            full.save(report,dict(status="REJECTED",reason=f"{type(error).__name__}: {error}"))
            row.update(status="INFRASTRUCTURE_ERROR",passed_only=False,
                reason="gap54 independent audit rejected; retain first evidence, no automatic retry")
            rc = 1
        row["files"].update(full.pins([report]))
        full.save(path,row)
        full.batch.publish(output,row)
        return rc

    def summarize(output, plan):
        for case in plan["cases"]:
            if case["name"] != admission.NAME:
                continue
            row = full.read(output / "outcomes" / (admission.NAME+".json"))
            if row["status"] != "PASS":
                continue
            report = output / "results" / admission.NAME / "gap54_runtime_audit.json"
            admission.require(str(report) in row["files"], "unbound gap54 runtime audit")
            full.check({str(report):row["files"][str(report)]})
            saved = full.read(report)
            admission.require(saved.get("schema") == admission.oracle.RUNTIME_FORMAT and saved.get("status") == "PASS",
                              "wrong runtime audit schema/status")
            admission.require(all(row["files"].get(p) == h for p,h in saved["files"].items()), "runtime file binding differs")
            full.check(saved["files"])
            admission.require(admission.runtime_proof(output,plan,row) == saved, "runtime replay differs")
        return old_summary(output,plan)

    for wrapped,delegate in ((precheck,old_precheck),(directed,old_directed),
                             (worker,old_worker),(summarize,old_summary)):
        wrapped.delegate = delegate
    checked.evidence.precheck = precheck
    full.worker,checked.summarize,full.batch.directed = worker,summarize,directed
    _HOOKS = dict(name=admission.NAME,precheck=precheck,worker=worker,summarize=summarize,
                  directed=directed,runtime_proof=admission.runtime_proof)
    return _HOOKS


def main():
    checked.SCRIPT = SCRIPT
    install_hooks()
    return checked.main()


if __name__ == "__main__":
    raise SystemExit(main())
