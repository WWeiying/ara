#!/usr/bin/env python3
"""Consolidate a same-image passing retry without rewriting simulation evidence.

The old absolute VDB command path remains a compatibility symlink. Consumers
must validate that recorded path resolves to the canonical VDB, not rewrite
siminfo.xml. Original failed-attempt evidence is kept outside active results.
"""
import argparse
import copy
import shlex
import shutil
from pathlib import Path

import run_full_recollection_20260928 as full


def validate_relocated_vdb(vdb, test, image):
    vdb = Path(vdb)
    info = full.batch.xml_root(vdb / "snps/coverage/db/testdata" / test / "siminfo.xml").find("srctest")
    command = shlex.split(info.get("cmdline", ""))
    full.require(command.count("-cm_dir") == 1, "missing/duplicate recorded VDB path")
    recorded = Path(command[command.index("-cm_dir") + 1])
    full.require(recorded.resolve(strict=True) == vdb.resolve(strict=True), "VDB relocation differs")
    full.batch.valid_vdb(recorded, test, image)
    return full.base.inventory(vdb)


def verify_gate(campaign):
    plan = full.frozen(campaign, all_cases=True)
    gate = full.read(campaign / "gate.json")
    full.require(len(gate["cases"]) == len(set(gate["cases"])) == 60, "invalid gate membership")
    cases = {c["name"]: c for c in plan["cases"]}
    databases = []
    for name in gate["cases"]:
        item = full.read(campaign / "outcomes" / (name + ".json"))
        full.require(item["status"] == "PASS" and item["passed_only"] and item["vdb_valid"], name)
        full.require(item["elf_sha256"] == cases[name]["elf_sha256"]
                     and item["contract"] == cases[name]["contract"], "contract mismatch")
        full.check(item["files"])
        vdb = Path(item["vdb"])
        full.require(vdb.resolve().is_relative_to(campaign / "results" / name), "foreign VDB")
        full.require(validate_relocated_vdb(vdb, item["coverage_test"], plan["simv"])
                     == item["vdb_files"], "VDB hash mismatch")
        databases.append(str(vdb))
    full.require(len(set(databases)) == 60, "duplicate VDB")
    return plan, gate, databases


def consolidate(campaign, retry):
    campaign, retry = campaign.resolve(), retry.resolve()
    plan = full.frozen(campaign, all_cases=True)
    full.check(full.read(retry / "retry.sha256.json"))
    effective = full.read(retry / "effective-plan.json")
    full.require(effective["image"] == plan["image"], "different simulator image")
    case = effective["cases"][0]
    name = case["name"]
    original = next(c for c in plan["cases"] if c["name"] == name)
    expected = copy.deepcopy(original)
    expected["timeout_s"] = 1200
    full.require(effective["cases"] == [expected], "retry changed more than wall budget")
    item = full.read(retry / "outcomes" / (name + ".json"))
    full.require(item["status"] == "PASS" and item["passed_only"], "retry not independently passed")
    full.check(item["files"])
    full.require(full.batch.valid_vdb(Path(item["vdb"]), item["coverage_test"], plan["simv"])
                 == item["vdb_files"], "retry VDB mismatch")
    old_outcome = campaign / "outcomes" / (name + ".json")
    full.require(full.read(old_outcome)["status"] == "RTL_TIMEOUT", "not the expected timeout")
    gate = full.read(campaign / "gate.json")
    full.require(not gate["full_dispatch_started"], "full queue already started")
    for other in gate["cases"]:
        if other != name:
            outcome = full.read(campaign / "outcomes" / (other + ".json"))
            full.require(outcome["status"] == "PASS" and outcome["passed_only"], "another gate failed")
            full.check(outcome["files"])
            full.require(full.batch.valid_vdb(Path(outcome["vdb"]), outcome["coverage_test"], plan["simv"])
                         == outcome["vdb_files"], "existing VDB mismatch")

    archive = campaign / "attempt-history/vfdiv-wall-budget"
    full.require(not archive.exists(), "already consolidated or partial consolidation; inspect first")
    archive.mkdir(parents=True)
    for filename in ("gate.json", "checkpoint.json"):
        shutil.copy2(campaign / filename, archive / filename)
    shutil.copy2(old_outcome, archive / "timeout-outcome.json")
    target = campaign / "results" / name
    old_result = retry / "results" / name
    target.rename(archive / "timeout-result")
    retry.rename(archive / "passing-retry")
    retry.symlink_to(archive / "passing-retry", target_is_directory=True)
    moved = archive / "passing-retry/results" / name
    moved.rename(target)
    moved.symlink_to(target, target_is_directory=True)
    for field in ("files", "vdb_files"):
        item[field] = {str(target / Path(p).relative_to(old_result)): h for p, h in item[field].items()}
    item["vdb"] = str(target / "code.vdb")
    item["relocation"] = {"recorded_result_path": str(old_result), "canonical_result_path": str(target),
                          "original_outcome": str(archive / "passing-retry/outcomes" / (name + ".json")),
                          "validation": "validate_relocated_vdb; recorded path resolves to canonical VDB"}
    item["wall_timeout_override_s"] = 1200
    full.check(item["files"])
    full.require(validate_relocated_vdb(Path(item["vdb"]), item["coverage_test"], plan["simv"])
                 == item["vdb_files"], "relocated VDB mismatch")
    full.save(old_outcome, item)
    full.batch.publish(campaign, item)
    plan, gate, databases = verify_gate(campaign)
    gate.update(status="PASS", failed=[], full_dispatch_started=False,
                outcome_files=full.pins(campaign / "outcomes" / (n + ".json") for n in gate["cases"]))
    gate.pop("reason", None)
    gate["retry_admission"] = str(archive)
    full.save(campaign / "gate.json", gate)
    state = full.read(campaign / "checkpoint.json")
    state.update(status="READY", phase="gate complete; remaining 540 not started", gate_status="PASS",
                 reason="60/60 gate PASS; same-image wall-budget retry consolidated", remaining=540)
    full.save(campaign / "checkpoint.json", state)
    full.save(campaign / "gate-consolidation.json", {
        "status": "PASS", "passed": 60, "total": 600, "remaining": 540,
        "image": plan["image"], "archive": str(archive), "compatibility_link": str(retry),
        "canonical_vdbs": databases, "outcome_files": gate["outcome_files"],
        "original_plan_unchanged": True, "wall_budget_override": {name: 1200},
        "coverage_selection": "one independently passed attempt per case; timeout excluded",
    })
    (campaign / "gate-passed-vdbs.txt").write_text("\n".join([plan["design_vdb"], *databases]) + "\n")
    print("PASS: 60 unique gate outcomes and complete VDBs consolidated; remaining 540 not started")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--retry", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify_gate(args.campaign.resolve())
        print("PASS: all 60 canonical gate results and VDB hashes verified")
    else:
        parser.error("--retry required") if args.retry is None else consolidate(args.campaign, args.retry)
