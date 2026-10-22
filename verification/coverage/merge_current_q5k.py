#!/usr/bin/env python3
"""Export the 444 admitted tests plus the audited Q5_K replay, without overwrite."""
from pathlib import Path
import run_vcs_dve_batch as b
import recollect_current_coverage as current


def main():
    parent = current.OUTPUT
    retry = b.ROOT / "verification/out/vcs-current-q5k-retry600-20260927-02"
    output = b.ROOT / "verification/out/vcs-current-coverage-445-20260928-01"
    output.mkdir(parents=True, exist_ok=False)
    plan = current.frozen(parent, all_cases=True)
    collection = b.read(parent / "collection.json")
    status = b.read(retry / "status.json")
    case = next(c for c in plan["cases"] if c["name"] == "extra-app-llama_qwen25_q5k_decode_attn_q_qbs")
    current.require(collection["passed"] == 444 and collection["coverage_verified"], "wrong parent collection")
    current.require(status["status"] == "PASS" and status["coverage_valid"] and
                    status["elf_sha256"] == case["elf_sha256"], "retry not matching PASS")
    artifact = retry / "result/tests" / b._safe_name(case["source_name"])
    b.audit_ok(b.read(status["audit"]), case, artifact)
    b.check({str(artifact / "input.elf"): case["elf_sha256"]})
    databases = {plan["design_vdb"]: plan["design_files"]}
    expected = []
    for item in collection["cases"]:
        current.require(item["status"] == "PASS" and item["passed_only"], "unadmitted parent test")
        b.check(item["files"])
        current.require(b.valid_vdb(Path(item["vdb"]), item["coverage_test"], plan["simv"]) == item["vdb_files"], "parent VDB changed")
        databases[item["vdb"]] = item["vdb_files"]
        expected.append(str(Path(item["vdb"]).with_suffix("") / item["coverage_test"]))
    current.require(status["vdb"] not in databases, "duplicate retry VDB")
    current.require(b.valid_vdb(Path(status["vdb"]), case["coverage_test"], plan["simv"]) == status["vdb_files"], "retry VDB changed")
    databases[status["vdb"]] = status["vdb_files"]
    expected.append(str(Path(status["vdb"]).with_suffix("") / case["coverage_test"]))
    current.require(len(databases) == 446, "expected one design plus 445 tests")
    for database, inventory in databases.items():
        current.require(b.base.inventory(Path(database)) == inventory, "input changed")
    b.save(output / "inputs.before.json", databases)
    inputs = output / "inputs.txt"
    inputs.write_text("\n".join(databases) + "\n")
    command = ["bash", str(current.DVE / "run_dve_coverage.sh"), str(output / "dve"), "--inputs-file", str(inputs)]
    current.require(b.invoke(command, output / "export.log", 660,
        {"DVE_COVERAGE_TIMEOUT": "600", "DVE_WAIVERS": "auto"}) == 0, "DVE export failed")
    current.require((output / "dve/selected_tests.txt").read_text().splitlines() == expected, "test selection differs")
    current.require(b.read(output / "dve/waiver_status.json")["status"] == "APPLIED", "waivers not applied")
    for database, inventory in databases.items():
        current.require(b.base.inventory(Path(database)) == inventory, "DVE changed input")
    b.save(output / "collection.json", {"status": "PASS", "passed": 445,
        "coverage_verified": True, "parent": str(parent), "retry": str(retry),
        "original_timeout_preserved": True, "image": plan["image"],
        "reports": b.pins([output / "dve/summary.csv", output / "dve/summary_waived.csv"]),
        "test_vdbs": list(databases)[1:]})
    print("PASS: 445-test coverage export complete", flush=True)


if __name__ == "__main__":
    main()
