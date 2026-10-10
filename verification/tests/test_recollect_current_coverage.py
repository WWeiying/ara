"""Pure selection/contract tests; do not prepare, simulate, or invoke DVE."""
import copy
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import recollect_current_coverage as r


@pytest.fixture(autouse=True)
def isolate_shared_batch(monkeypatch):
    # main() intentionally mutates this shared module in a standalone process.
    # Register restoration even when a test exits through argparse/SystemExit.
    for name in ("SCRIPT", "frozen", "summarize"):
        monkeypatch.setattr(r.batch, name, getattr(r.batch, name))
    monkeypatch.setenv("PYTHONPATH", os.environ.get("PYTHONPATH", ""))


def directed(name, elf=None):
    return {"name": name, "kind": "directed", "oracle": "selfcheck+trace-audit",
            "timeout_s": 300, "fault_vstart_probe": False, "elf_sha256": elf or name,
            "source_files": {"fixture": "hash"},
            "directed_test": {"name": "rvv:" + name, "kind": "rvv", "testcase": name,
                              "binary": "/fixture/" + name, "build_target": "unused"}}


def replay(name="random", **changes):
    case = {"name": name, "kind": "random", "oracle": "Spike+scalar+vector+independent-audit",
            "timeout_s": 300, "fault_vstart_probe": False, "elf_sha256": "same-elf",
            "spike_sha256": "spike", "spike_timeout_s": 60, "watchdog_cycles": 100000,
            "seed": 601, "source_files": {}}
    return dict(case, **changes)


def selections():
    current = [directed(name) for name in sorted(r.OVERLAPS)]
    current += [directed(f"current{i}") for i in range(18)]
    historical = []
    for item in current[:3]:
        alias = copy.deepcopy(item)
        alias["name"] = "historical-" + item["name"]
        alias["directed_test"].update(testcase="old-label", binary="/old/input.elf", build_target="old-target")
        historical.append(alias)
    historical += [directed(f"historical{i}") for i in range(424)]
    return historical, current


def test_exact_445_union_and_three_semantic_aliases():
    historical, current = selections()
    before = copy.deepcopy((historical, current))
    cases, aliases = r.deduplicate(historical, current)
    assert len(cases) == 445
    assert cases[:21] == current
    assert len(cases[21:]) == 424
    assert {a["current"] for a in aliases} == r.OVERLAPS
    assert all(a["source_files"] for a in aliases)
    assert (historical, current) == before


def test_labels_and_no_build_paths_do_not_change_directed_contract():
    old, current = selections()
    assert r.case_key(old[0]) == r.case_key(current[0])


@pytest.mark.parametrize("field,value", [("timeout_s", 600), ("fault_vstart_probe", True),
                                         ("oracle", "weaker-checker")])
def test_same_elf_different_directed_semantics_not_deduplicated(field, value):
    historical, current = selections()
    historical[0][field] = value
    assert r.case_key(historical[0]) != r.case_key(current[0])
    with pytest.raises(ValueError, match="three approved"):
        r.deduplicate(historical, current)


@pytest.mark.parametrize("field,value", [("name", "rvv:other"), ("kind", "app")])
def test_catalog_identity_and_oracle_kind_are_semantic(field, value):
    old, current = selections()
    old[0]["directed_test"][field] = value
    assert r.case_key(old[0]) != r.case_key(current[0])
    with pytest.raises(ValueError):
        r.deduplicate(old, current)


@pytest.mark.parametrize("field,value", [("spike_sha256", "other-spike"), ("spike_timeout_s", 120),
                                         ("watchdog_cycles", 200000), ("fault_vstart_probe", True),
                                         ("timeout_s", 1800)])
def test_replay_oracle_and_execution_contract_is_not_elf_only(field, value):
    original = replay()
    assert r.case_key(original) != r.case_key(dict(original, **{field: value}))


def test_replay_rtl_random_seed_is_part_of_contract():
    assert r.case_key(replay(seed=601)) != r.case_key(replay(seed=602))


def test_random_and_replay_labels_share_strict_oracle_mode():
    assert r.case_key(replay(kind="random")) == r.case_key(replay(kind="replay"))
    contract = r.contract(replay())
    assert contract["require_complete"] is True
    assert contract["require_trace"] is True
    assert contract["require_vector"] is True
    assert contract["require_full_match"] is True


def test_axpy_cannot_collapse_into_generic_selfcheck():
    axpy = {"kind": "axpy", "oracle": "UVM+selfcheck+independent-audit+cycle-limit",
            "timeout_s": 900, "elf_sha256": "elf"}
    contract = r.contract(axpy)
    assert contract["cycle_limit"] == 2810
    assert contract["independent_uvm_audit"] is True
    assert r.case_key(axpy) != r.case_key(directed("axpy", "elf"))


def test_unknown_oracle_mode_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        r.contract(replay(kind="unknown"))


@pytest.mark.parametrize("mutation", ("missing_current", "duplicate_current", "missing_history",
                                      "duplicate_history", "duplicate_label", "unexpected_alias"))
def test_union_rejects_wrong_counts_duplicates_and_unapproved_aliases(mutation):
    old, current = selections()
    if mutation == "missing_current":
        current.pop()
    elif mutation == "duplicate_current":
        current[-1] = copy.deepcopy(current[-2])
    elif mutation == "missing_history":
        old.pop()
    elif mutation == "duplicate_history":
        old[-1] = copy.deepcopy(old[-2])
    elif mutation == "duplicate_label":
        old[-1]["name"] = current[-1]["name"]
    else:
        old[0] = copy.deepcopy(current[-1])
        old[0]["name"] = "unexpected-overlap"
    with pytest.raises(ValueError):
        r.deduplicate(old, current)


def test_unique_file_rejects_missing_and_ambiguous_proof():
    assert r.unique_file({"/case/inputs.json": "hash"}, "inputs.json") == Path("/case/inputs.json")
    with pytest.raises(ValueError):
        r.unique_file({}, "inputs.json")
    with pytest.raises(ValueError):
        r.unique_file({"/a/inputs.json": "1", "/b/inputs.json": "2"}, "inputs.json")


@pytest.fixture
def merge_fixture(tmp_path, monkeypatch):
    output = tmp_path / "run"
    output.mkdir()
    cases, outcomes = [], []
    for name, status in (("passed", "PASS"), ("failed", "TIMEOUT")):
        case = dict(directed(name), source_name="rvv:" + name, coverage_test=name)
        case["contract"] = r.contract(case)
        item = {"name": name, "status": status, "elf_sha256": case["elf_sha256"],
                "contract": case["contract"], "coverage_test": name, "files": {},
                "vdb": str(output / "results" / name / "tests" / ("rvv_" + name) / "work/code.vdb"),
                "vdb_files": {}, "passed_only": status == "PASS", "vdb_valid": status == "PASS"}
        r.save(output / "outcomes" / (name + ".json"), item)
        cases.append(case)
        outcomes.append(item)
    plan = {"cases": cases, "reused": [], "files": {}, "simv": "/current/sim/simv", "image": {"image": "hash"},
            "design_vdb": str(tmp_path / "design.vdb"), "design_files": {}, "aliases": [],
            "dve_outer_timeout_s": 1320, "dve_timeout_s": 1200}
    validated, invoked = [], []
    def valid(vdb, test, image):
        validated.append((str(vdb), test, image))
        return {}
    def invoke(command, log, timeout, env):
        invoked.append(command)
        target = Path(command[2])
        assert target == output / "dve"
        assert command[1] == str(r.HERE / "dve_hierarchy/run_dve_coverage.sh")
        target.mkdir()
        databases = Path(command[-1]).read_text()
        (target / "inputs.txt").write_text(databases)
        selected = str(Path(outcomes[0]["vdb"]).with_suffix("") / "passed")
        (target / "selected_tests.txt").write_text(selected + "\n")
        text = "Name,Depth,Line,Condition,FSM,Toggle,Branch\nara_fault_vstart_probe,0,1,1,NA,1,1\n"
        for name in ("summary.csv", "summary_waived.csv"):
            (target / name).write_text(text)
        for name in ("exclusions.el", "points.el"):
            (target / name).write_text("mock native exclusions\n")
        r.save(target / "waiver_status.json", {"status": "APPLIED"})
        return 0
    monkeypatch.setattr(r.batch, "valid_vdb", valid)
    monkeypatch.setattr(r.batch, "invoke", invoke)
    monkeypatch.setattr(r.base, "pure_design", lambda path: None)
    monkeypatch.setattr(r.base, "inventory", lambda path: {})
    return output, plan, outcomes, validated, invoked


def test_merge_pass_only_current_image_and_dve_directory(merge_fixture):
    output, plan, outcomes, validated, invoked = merge_fixture
    r.summarize(output, plan)
    assert len(invoked) == 1
    assert validated == [(outcomes[0]["vdb"], "passed", plan["simv"])]
    assert (output / "dve-inputs.txt").read_text().splitlines() == [plan["design_vdb"], outcomes[0]["vdb"]]
    collection = r.read(output / "collection.json")
    assert collection["status"] == "COMPLETE_WITH_FAILURES"
    assert collection["passed"] == 1
    assert collection["failed_cases_excluded"] == [{"name": "failed", "status": "TIMEOUT"}]
    assert collection["historical_vdb_reuse"] is False
    assert collection["exploration_export"] is False
    assert not (output / "exploration").exists()


@pytest.mark.parametrize("mutation", ("old_image_path", "other_case_path", "coverage_label", "oracle_contract",
                                      "elf", "failed_admitted", "pass_without_vdb"))
def test_merge_refuses_cross_case_and_unproven_outcomes(merge_fixture, mutation):
    output, plan, outcomes, _, invoked = merge_fixture
    item = copy.deepcopy(outcomes[0])
    if mutation == "old_image_path":
        item["vdb"] = "/old-image/results/passed/code.vdb"
    elif mutation == "other_case_path":
        item["vdb"] = outcomes[1]["vdb"]
    elif mutation == "coverage_label":
        item["coverage_test"] = "wrong"
    elif mutation == "oracle_contract":
        item["contract"]["require_trace"] = False
    elif mutation == "elf":
        item["elf_sha256"] = "wrong"
    elif mutation == "failed_admitted":
        item["status"] = "TIMEOUT"
    else:
        item["vdb_valid"] = False
    r.save(output / "outcomes/passed.json", item)
    with pytest.raises(ValueError):
        r.summarize(output, plan)
    assert invoked == []


def test_reused_outcome_requires_frozen_record_hash(merge_fixture):
    output, plan, outcomes, _, invoked = merge_fixture
    path = output / "outcomes/passed.json"
    plan["reused"] = ["passed"]
    plan["files"] = r.pins([path])
    modified = dict(outcomes[0], vdb="/other-current-case/code.vdb")
    r.save(path, modified)
    with pytest.raises(RuntimeError, match="frozen input changed"):
        r.summarize(output, plan)
    assert invoked == []


def test_main_eight_workers_dispatch_and_hooks_are_isolated(monkeypatch):
    called = []
    monkeypatch.setattr(sys, "argv", [str(r.SCRIPT), "--execute", "--jobs", "8"])
    monkeypatch.setenv("ARA_CHECKPOINT_UNIT", r.SERVICE)
    monkeypatch.setattr(r.batch, "execute", lambda output, jobs: called.append((output, jobs)) or 0)
    assert r.main() == 0
    assert called == [(r.OUTPUT, 8)]
    assert r.batch.SCRIPT == r.SCRIPT
    assert r.batch.frozen is r.frozen
    assert r.batch.summarize is r.summarize


def test_main_rejects_more_than_eight_workers(monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(r.SCRIPT), "--execute", "--jobs", "9"])
    with pytest.raises(SystemExit) as error:
        r.main()
    assert error.value.code == 2


def test_main_rejects_unregistered_service_before_dispatch(monkeypatch):
    called = []
    monkeypatch.setattr(sys, "argv", [str(r.SCRIPT), "--execute"])
    monkeypatch.setenv("ARA_CHECKPOINT_UNIT", "other.service")
    monkeypatch.setattr(r.batch, "execute", lambda *args: called.append(args))
    with pytest.raises(ValueError, match="wrong recollection service"):
        r.main()
    assert called == []
