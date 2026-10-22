"""Source-qualified, independently parallel budget-retry successor; prepare first."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import akv_historical_budget_source_proof_717 as source
import run_akv_historical_budget_retry_717 as base


def prepare(name, output):
    output, manifest = base.prepare(name, output)
    proof, pins = source.source_proof(manifest["input_elf"])
    manifest["schema"] = "akv-same-elf-old-image-budget-retry-717-v2"
    manifest["source_qualified_translation_counter"] = proof
    manifest["environment_review"]["concurrency"] = "Both independent cases may run in parallel; each has its own wall-clock budget, process, output and launch-once record"
    manifest["tool_issue_record"]["successor"] = "Source-qualified bare translations==0 via existing gap54 PERF parser; gap46 original3237 checks/phase/CSR/traps/trace unchanged"
    manifest["tool_issue_record"]["source_evidence_required"] = True
    manifest["runner_entry"] = str(Path(__file__).resolve())
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_run_akv_historical_budget_retry_717_v2.py")):
        pins[str(path)] = base.sha(path)
    for path, digest in pins.items():
        source.oracle.require(path not in manifest["pins"] or manifest["pins"][path] == digest, "Conflicting source proof pin")
        manifest["pins"][path] = digest
    base.check_pins(manifest["pins"])
    return output, manifest


def run_reviewed(output, reviewed_seal):
    oracle = SimpleNamespace(**dict(base.oracle.__dict__, verify=source.verify))
    namespace = dict(base.__dict__, prepare=prepare, oracle=oracle)
    function = FunctionType(base.run_reviewed.__code__, namespace, "source_qualified_reviewed_run")
    return function(output, reviewed_seal)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run-reviewed"))
    parser.add_argument("--case", choices=sorted(base.CASES))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-seal")
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        source.oracle.require(args.case and not args.prepared_seal, "Prepare needs only --case")
        output, manifest = prepare(args.case, args.output)
        record = output.with_name(output.name + ".prepared.json")
        base.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), plan_sha256=base.sha(record), pins_checked=len(manifest["pins"]),
                              timeout_s=manifest["timeout_s"], expected_checks=manifest["expected_checks"],
                              status="SOURCE_QUALIFIED_PREPARED_PARENT_REVIEW_NO_RUN")))
    else:
        source.oracle.require(args.prepared_seal and not args.case, "Run-reviewed needs only --prepared-seal")
        print(json.dumps(run_reviewed(args.output, args.prepared_seal)))


if __name__ == "__main__":
    main()
