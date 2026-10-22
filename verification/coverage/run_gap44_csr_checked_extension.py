#!/usr/bin/env python3
"""Thin gap44 gate composed with the existing checked runner; no new scheduler."""
import json
from pathlib import Path

import gap44_csr_admission as csr
import run_checked_extension as checked

full = checked.full
SCRIPT = Path(__file__).resolve()
_HOOKS = None


def worker(output, name, delegate):
    rc = delegate(output, name)
    if rc or name != csr.NAME:
        return rc
    path = output / "outcomes" / (name + ".json")
    row = full.read(path)
    if row["status"] != "PASS":
        return rc
    report = output / "results" / name / "csr_gap44_runtime_audit.json"
    try:
        proof = csr.runtime_proof(output, checked.frozen(output), row)
        csr.require(json.loads(json.dumps(proof)) == proof, "runtime proof is not JSON stable")
        full.save(report, proof)
        row["files"].update(proof["files"])
    except Exception as error:
        full.save(report, dict(status="REJECTED", reason=f"{type(error).__name__}: {error}"))
        row.update(status="INFRASTRUCTURE_ERROR", passed_only=False,
                   reason="gap44 extra audit failed; retain first evidence, no automatic retry")
        rc = 1
    row["files"].update(full.pins([report]))
    full.save(path, row)
    full.batch.publish(output, row)
    return rc


def summarize(output, plan, delegate):
    full.require(checked.frozen(output, all_cases=True) == plan, "summarize plan differs")
    for case in plan["cases"]:
        if case["name"] != csr.NAME:
            continue
        row = full.read(output / "outcomes" / (csr.NAME + ".json"))
        if row["status"] != "PASS":
            continue
        report = output / "results" / csr.NAME / "csr_gap44_runtime_audit.json"
        full.require(str(report) in row["files"], "unbound gap44 runtime proof")
        full.check({str(report): row["files"][str(report)]})
        saved = full.read(report)
        full.require(saved.get("schema") == csr.oracle.RUNTIME_FORMAT and saved.get("files"), "strict gap44 proof required")
        full.require(all(row["files"].get(p) == h for p, h in saved["files"].items()), "runtime proof differs from original outcome")
        full.check(saved["files"])
        full.require(csr.runtime_proof(output, plan, row) == saved, "full gap44 runtime replay differs")
    return delegate(output, plan)


def install_hooks():
    """Call once per process after parent defaults, before checked.main().

    Later helpers may wrap these gates. No assignment to checked.SCRIPT and no
    scheduler replacement; all non-gap44 cases retain the captured delegates.
    """
    global _HOOKS
    if _HOOKS is not None:
        return _HOOKS
    prior_precheck = checked.evidence.precheck
    prior_worker = full.worker
    prior_summarize = checked.summarize

    def wrapped_precheck(item, proof):
        if not csr.handles(item):
            return prior_precheck(item, proof)
        result = csr.precheck(item, proof)
        proof.pin(SCRIPT)
        proof.pin(Path(checked.__file__))
        return result

    def wrapped_worker(output, name):
        return worker(output, name, prior_worker)

    def wrapped_summarize(output, plan):
        return summarize(output, plan, prior_summarize)

    for wrapper, delegate in ((wrapped_precheck, prior_precheck), (wrapped_worker, prior_worker),
                              (wrapped_summarize, prior_summarize)):
        wrapper.delegate = delegate
    checked.evidence.precheck = wrapped_precheck
    full.worker = wrapped_worker
    checked.summarize = wrapped_summarize
    _HOOKS = dict(name=csr.NAME, precheck=wrapped_precheck, runtime_proof=csr.runtime_proof,
                  worker=wrapped_worker, summarize=wrapped_summarize)
    return _HOOKS


def main():
    # Standalone entry only. A combined parent owns this assignment itself.
    checked.SCRIPT = SCRIPT
    install_hooks()
    return checked.main()


if __name__ == "__main__":
    raise SystemExit(main())
