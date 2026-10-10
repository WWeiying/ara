#!/usr/bin/env python3
"""Add bounded memory tests to current coverage, retaining the audited Q5_K retry."""
from pathlib import Path

import extend_gap_coverage as gap
import recollect_current_coverage as current

extension = gap.extension
b = gap.batch
SCRIPT = Path(__file__).resolve()
original_prepare = gap.prepare
original_schedule = b.schedule


def prepare(output, previous, selection):
    current.require(previous == current.OUTPUT, "expected current frozen campaign")
    original_prepare(output, previous, selection)
    retry = b.ROOT / "verification/out/vcs-current-q5k-retry600-20260927-02"
    status = b.read(retry / "status.json")
    plan = b.read(output / "plan.json")
    name = "extra-app-llama_qwen25_q5k_decode_attn_q_qbs"
    case = next(c for c in plan["cases"] if c["name"] == name)
    current.require(status["status"] == "PASS" and status["coverage_valid"] and
                    status["elf_sha256"] == case["elf_sha256"], "unverified retry")
    target = retry / "result"
    artifact = target / "tests" / b._safe_name(case["source_name"])
    current.require(Path(status["vdb"]).resolve() == artifact / "work/code.vdb",
                    "retry VDB is not the audited artifact")
    provenance = b.read(retry / "provenance.json")
    current.require(provenance["image"] == plan["image"] and provenance["timeout_s"] == 600 and
                    provenance["case"]["elf_sha256"] == case["elf_sha256"], "retry provenance mismatch")
    b.audit_ok(b.read(status["audit"]), case, artifact)
    b.check({str(artifact / "input.elf"): case["elf_sha256"]})
    current.require(b.valid_vdb(Path(status["vdb"]), case["coverage_test"], plan["simv"]) == status["vdb_files"], "retry VDB drift")
    case["timeout_s"] = 600
    case["contract"] = dict(case["contract"], timeout_s=600)
    item = b.read(output / "outcomes" / (name + ".json"))
    evidence = [target / "summary.json", Path(status["audit"]), retry / "status.json", retry / "provenance.json"]
    evidence.extend(p for p in artifact.rglob("*") if p.is_file() and p.suffix in (".json", ".csv", ".log", ".elf"))
    item.update(status="PASS", reused=True, returncode=0, files=b.pins(evidence),
                vdb=status["vdb"], vdb_valid=True, vdb_files=status["vdb_files"],
                vdb_rejection=None, passed_only=True, contract=case["contract"],
                retry_origin=str(retry), original_timeout_preserved=True)
    b.save(output / "outcomes" / (name + ".json"), item)
    b.publish(output, item)
    plan["files"].update(b.pins([SCRIPT, Path(gap.__file__), Path(current.__file__),
                                 retry / "status.json", target / "independent_audit.json"]))
    plan["files"].update(b.pins([b.ROOT / "apps/riscv-tests/isa/rv64uv/vmemory_gap_body.h",
        b.ROOT / "verification/tests/generate_rvv_memory_gaps.py",
        b.ROOT / "verification/tests/build_rvv_memory_gaps.py"]))
    plan["files"].update(b.pins(output / "outcomes" / (n + ".json") for n in plan["reused"]))
    b.save(output / "plan.json", plan)
    b.save(output / "plan.sha256.json", b.pins([output / "plan.json"]))
    b.frozen(output, all_cases=True)


def summarize(output, plan):
    outcomes = [b.read(output / "outcomes" / (c["name"] + ".json")) for c in plan["cases"]]
    selected = []
    for case, item in zip(plan["cases"], outcomes):
        current.require(item["name"] == case["name"] and item["elf_sha256"] == case["elf_sha256"], "case identity mismatch")
        current.require(item["coverage_test"] == case["coverage_test"], "coverage label mismatch")
        if case["name"] in plan["reused"]:
            path = output / "outcomes" / (case["name"] + ".json")
            b.check({str(path): plan["files"][str(path)]})
        else:
            expected_vdb = output / "results" / case["name"] / "tests" / b._safe_name(case["source_name"]) / "work/code.vdb"
            current.require(Path(item["vdb"]).resolve() == expected_vdb, "VDB does not belong to test")
        b.check(item["files"])
        if item["status"] == "PASS":
            current.require(item["passed_only"] and item["vdb_valid"], "PASS without coverage")
            current.require(b.valid_vdb(Path(item["vdb"]), item["coverage_test"], plan["simv"]) == item["vdb_files"], "VDB drift")
            selected.append(item)
    databases = {plan["design_vdb"]: plan["design_files"], **{x["vdb"]: x["vdb_files"] for x in selected}}
    current.require(len(databases) == len(selected) + 1, "duplicate VDB")
    for path, digest in databases.items():
        current.require(b.base.inventory(Path(path)) == digest, "input drift")
    b.save(output / "dve-inputs.before.json", databases)
    inputs = output / "dve-inputs.txt"
    inputs.write_text("\n".join(databases) + "\n")
    report = output / "dve"
    command = ["bash", str(current.DVE / "run_dve_coverage.sh"), str(report), "--inputs-file", str(inputs)]
    current.require(b.invoke(command, output / "logs/dve.log", 720,
        {"DVE_COVERAGE_TIMEOUT": "600", "DVE_WAIVERS": "auto"}) == 0, "DVE export failed")
    expected = [str(Path(x["vdb"]).with_suffix("") / x["coverage_test"]) for x in selected]
    current.require((report / "selected_tests.txt").read_text().splitlines() == expected, "DVE selection mismatch")
    current.require(b.read(report / "waiver_status.json")["status"] == "APPLIED", "waivers missing")
    for path, digest in databases.items():
        current.require(b.base.inventory(Path(path)) == digest, "DVE input changed")
    b.save(output / "collection.json", {"status": "PASS" if len(selected) == len(outcomes) else "COMPLETE_WITH_FAILURES",
        "coverage_verified": True, "passed": len(selected), "total": len(outcomes),
        "cases": selected, "image": plan["image"], "excluded": [x["name"] for x in outcomes if x["status"] != "PASS"],
        "reports": b.pins([report / "summary.csv", report / "summary_waived.csv"])})
    return outcomes


def schedule(output, names, jobs):
    # Validate representatives before expanding the same generator's cases.
    first = names[:2]
    original_schedule(output, first, 1)
    (output / "scheduler").rename(output / "preflight-scheduler")
    for name in first:
        current.require(b.read(output / "outcomes" / (name + ".json"))["status"] == "PASS",
                        "representative failed; stop before expanding stimuli")
    if names[2:]:
        original_schedule(output, names[2:], jobs)


extension.SCRIPT = SCRIPT
b.SCRIPT = SCRIPT
extension.prepare = prepare
b.summarize = summarize
b.schedule = schedule

if __name__ == "__main__":
    raise SystemExit(extension.main())
