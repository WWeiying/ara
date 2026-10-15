#!/usr/bin/env python3
"""Verify immutable receipts and evidence for three completed M8 prefixes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATHS = (
    "fixed_restart_original/full777_optimized_prepare01/vcs_m8_run01",
    "fp_comparison_original/full682_vcs_m8_plan01/prepared01",
    "arithmetic_restart_original/macc_disjoint482/full482_optimized_prepare01/vcs_m8_plan03/prepared01",
)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    records = []
    pins = {}
    for relative in PATHS:
        directory = ROOT / relative
        complete = json.loads((directory / "complete.json").read_text())
        plan_path = (directory.parent / "vcs_m8_prepared02/plan.json"
                     if relative.startswith("fixed_restart_original/")
                     else directory / "plan.json")
        plan = json.loads(plan_path.read_text())
        require(sha(plan_path) == complete["plan_sha256"], "Plan drift")
        require(complete["status"].startswith("PASS_") and complete["aborted"] is False
                and complete["retries"] == 0 and complete["pins_unchanged"] is True,
                "Terminal not accepted")
        for source in (plan.get("pins", {}), complete["evidence_pins"]):
            for path, digest in source.items():
                require(path not in pins or pins[path] == digest, "Conflicting identity: " + path)
                pins[path] = digest
        require(len(complete["results"]) == 1, "Prefix membership")
        result = complete["results"][0]
        require(result["status"] == "PASS" and type(result["returncode"]) is int
                and result["returncode"] == 0, "DUT result")
        artifact = Path(result["artifact_dir"])
        receipt_name = ("child_exit.json" if relative.startswith("fixed_restart_original/")
                        else "child_outcome.unvalidated.json")
        receipt_path = artifact / receipt_name
        require(str(receipt_path) in complete["evidence_pins"], "Receipt must be sealed")
        child = json.loads(receipt_path.read_text())
        require(type(child["returncode"]) is int and child["returncode"] == 0
                and child["timed_out"] is False and child["failure_seen"] is False,
                "Actual simulator receipt")
        require(not child.get("abort_set", False), "Aborted simulator")
        records.append(dict(name=result["name"], status=complete["status"],
                            elapsed_s=child["elapsed_s"],
                            complete_sha256=sha(directory / "complete.json"),
                            artifact_dir=str(artifact)))
    for path, expected in pins.items():
        require(sha(path) == expected, "Evidence drift: " + path)
    report = dict(status="PASS_SEALED_THREE_PREFIX_EVIDENCE_AUDIT",
                  records=records, checked_unique_pins=len(pins),
                  scope="Receipt and evidence identity audit; existing full CSV checker results retained, no new DUT or CSV semantic replay")
    with (ROOT / "audit_long_prefixes_resume01.json").open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
