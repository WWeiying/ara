#!/usr/bin/env python3
"""Inventory (default), prepare, or explicitly execute a fresh-image full replay.

No build, retry, old verdict admission, or old VDB merge. --inventory only reads
stimulus provenance; --prepare requires --freeze JSON supplied after repair:
{"status":"READY_FOR_FULL_RECOLLECTION", "simv":"/absolute/.../sim/simv",
 "image":{...simulation_image hashes...}, "files":{...build/repair evidence pins...},
 "repair_evidence":["/absolute/.../focused-result.json"]}.
Parent owns the build (build_memory_vl0_repair.py compiler/source contract).
Preparation pins current sources, checkers, image and inputs. Six FP16 tests,
four adjacent smoke tests, three conversion tests, AXPY, the full 40-case memory
matrix and six Gap28 store timeouts must PASS before the remaining eight-worker
queue. Unit evidence alone makes no performance claim.
--systemd-command prints a launch command without running it; execution requires
that exact unit. Functional failures continue only after the gate has passed.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "verification"))
import run_vcs_dve_batch as batch
import run_remaining5_closure as closure
from run_seed509_validation import cycles

SCRIPT = Path(__file__).resolve()
DEFAULT_PLAN = HERE / "full_recollection_20260928.plan.json"
DVE = HERE / "dve_hierarchy"
UVM = ROOT / "verification/uvm/run_real_dut_case.sh"
read, save, pins, check = batch.read, batch.save, batch.pins, batch.check
base = batch.base
original_frozen, original_commands = batch.frozen, batch.commands
original_schedule = batch.schedule


def require(ok, message):
    if not ok:
        raise ValueError(message)


def absolute(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def contract(case):
    kind = case["kind"]
    result = {"mode": "replay" if kind in ("random", "replay") else kind,
              "oracle": case["oracle"], "reset": case.get("reset", {}),
              "fault_vstart_probe": bool(case.get("fault_vstart_probe"))}
    if kind in ("random", "replay"):
        result.update(spike_sha256=case["spike_sha256"], isa=base.ISA,
                      seed=case["seed"], watchdog_cycles=case["watchdog_cycles"])
    if kind == "directed":
        result["test_kind"] = case["directed_test"]["kind"]
    if kind in ("uvm", "axpy"):
        result.update(trace_limits=case.get("trace_limits", [100000, 100000]),
                      trace_axi_write=case.get("trace_axi_write", False),
                      cycle_limit=case.get("cycle_limit"), require_axi=case.get("require_axi", True),
                      required_markers=case.get("required_markers", []))
    return result


def case_key(case):
    return case["elf_sha256"], json.dumps(contract(case), sort_keys=True)


def normalize(original, origin):
    case = copy.deepcopy(original)
    elf = case.get("frozen_elf", case.get("elf"))
    require(elf is not None, f"missing frozen ELF: {origin}")
    check({elf: case["elf_sha256"]})
    case.update(source_elf=elf, source_files={elf: case["elf_sha256"]},
                origins=[origin], source_audit=case.get("source_audit", "fresh audit required"))
    kind = case["kind"]
    require(kind in ("random", "replay", "directed", "axpy", "uvm"), f"unsupported kind {kind}")
    if kind == "directed":
        test = case.get("directed_test", {"name": case["test"], "kind": "rvv"} if "test" in case else {})
        require(test.get("name") and test.get("kind"), f"missing directed contract: {origin}")
        case["source_name"] = test["name"]
        case["directed_test"] = dict(test, build_target="unused-no-build",
                                     testcase=test.get("testcase", case["coverage_test"]))
        case["oracle"] = "selfcheck+trace-audit"
    elif kind == "axpy":
        case.update(oracle="UVM+selfcheck+independent-audit+cycle-limit", cycle_limit=2810,
                    reset={}, trace_limits=[100000, 100000])
    elif kind in ("replay", "random"):
        require(all(k in case for k in ("spike", "spike_sha256", "spike_timeout_s", "watchdog_cycles")),
                f"missing replay oracle: {origin}")
        if "seed" not in case:
            rows = read(case["source_summary"])
            require(len(rows) == 1, "ambiguous historical replay seed")
            case["seed"] = rows[0]["seed"]
            case["source_files"].update(pins([Path(case["source_summary"])]))
        case["oracle"] = "Spike+scalar+vector+independent-audit"
        if case.get("fault_vstart_probe"):
            case["source_files"].update(pins([Path(case["diagnostic_probe"])]))
    require(case.get("timeout_s", 0) > 0, "missing bounded timeout")
    return case


def deduplicate(cases):
    unique = {}
    for case in cases:
        key = case_key(case)
        if key in unique:
            kept = unique[key]
            kept["origins"].extend(case["origins"])
            kept["source_files"].update(case["source_files"])
            # Wall-clock budgets are not oracle semantics. Retain the largest
            # existing budget; never retune a workload or its cycle watchdog.
            for field in ("timeout_s", "spike_timeout_s"):
                if field in case:
                    kept[field] = max(kept.get(field, 0), case[field])
        else:
            unique[key] = copy.deepcopy(case)
    for index, case in enumerate(unique.values()):
        digest = hashlib.sha256(json.dumps(case_key(case)).encode()).hexdigest()[:12]
        label = re.sub(r"[^A-Za-z0-9_.-]", "_", case["name"])[:80]
        case["name"] = f"c{index:04d}-{label}-{digest}"
        case["contract"] = contract(case)
    return list(unique.values())


def gate_selection(cases, policy, memory_tests, gap28_tests):
    names = []
    for test in policy["fp16_tests"]:
        found = [c for c in cases if c.get("source_name") == test and c["kind"] == "directed"]
        require(len(found) == 1, f"missing or ambiguous FP16 gate: {test}")
        names.append(found[0]["name"])
    for test in policy["adjacent_smoke"]:
        found = [c for c in cases if c["kind"] == "uvm" and c["coverage_test"] == test
                 and c.get("required_markers") and not c.get("require_axi", True)]
        require(len(found) == 1, f"missing or ambiguous adjacent gate: {test}")
        names.append(found[0]["name"])
    for test in policy["conversion_tests"]:
        found = [c for c in cases if c.get("source_name") == test and c["kind"] == "directed"]
        require(len(found) == 1, f"missing or ambiguous conversion gate: {test}")
        names.append(found[0]["name"])
    require(policy["axpy"] is True, "AXPY gate required")
    axpy = [c for c in cases if c["kind"] == "axpy"]
    require(len(axpy) == 1, "missing or ambiguous AXPY gate")
    names.append(axpy[0]["name"])
    require(len(names) == len(set(names)) == 14 and len(policy["fp16_tests"]) == 6,
            "expected six FP16, four adjacent, three conversion and one AXPY gate cases")
    require(policy["all_memory_matrix"] is True and policy["all_gap28_store_timeouts"] is True,
            "known memory/store failures must gate full dispatch")
    required_indexed = {f"rvv:vmemory_gap_nf{nf}_e{eew}_indexed"
                        for nf in (5, 6, 7) for eew in (8, 16, 32, 64)}
    require(len(memory_tests) == len(set(memory_tests)) == 40 and required_indexed <= set(memory_tests),
            "memory gate must include all 40 tests and all 12 indexed timeouts")
    require(set(gap28_tests) == {f"vqueue_gap28_store_e{eew}_m{lmul}" for eew in (32, 64) for lmul in (1, 2, 4)},
            "store gate must include all six old timeouts")
    early_stores, memory = [], []
    for tests, group in ((["rvv:" + n for n in gap28_tests], early_stores), (memory_tests, memory)):
        for test in tests:
            # Include every distinct ELF/oracle variant. Label-only aliases have
            # already collapsed, but a repaired ELF must not replace its original.
            found = [c for c in cases if c.get("source_name") == test and c["kind"] == "directed"]
            require(found, f"missing known-failure gate: {test}")
            group.extend(c["name"] for c in found)
    # Dispatch long stores immediately after FP16 so other bounded gate cases
    # can occupy free workers while stores finish. This is not a phase barrier.
    fp16_count = len(policy["fp16_tests"])
    names = list(dict.fromkeys(names[:fp16_count] + early_stores + names[fp16_count:] + memory))
    require(len(names) == policy["expected_count"] and len(names) >= 60,
            "gate membership changed; review all variants and expected count")
    return names


def wall_budgets(cases, review):
    require(review["status"] == "STATIC_TRACE_REVIEWED_NOT_A_PASS_CLAIM", "unreviewed wall budgets")
    ready, body = absolute(review["source_ready"]), absolute(review["source_body"])
    evidence = {str(body): read(ready)["files"][str(body)]}
    check(evidence)
    evidence.update(pins([ready]))
    for test, seconds in review["seconds_by_test"].items():
        require(type(seconds) is int and seconds > 0, "invalid wall budget")
        matched = [c for c in cases if c.get("source_name") == test]
        require(matched, f"wall budget test missing: {test}")
        outcome = absolute(review["outcomes"]) / ("extra-" + test.replace(":", "-") + ".json")
        old = read(outcome)
        require(old["status"] == "TIMEOUT" and old["elf_sha256"] in {c["elf_sha256"] for c in matched},
                "wall budget evidence is not the matching historical timeout")
        evidence.update(pins([outcome]))
        # Keep archived trace hashes, not just the derived diagnosis. Full
        # prepare/execute boundary checks enforce these potentially large files.
        for basename in ("summary.json", "commit_trace.csv", "input.elf", "coverage.command.json"):
            matches = {p: h for p, h in old["files"].items() if Path(p).name == basename}
            require(len(matches) == 1, f"missing/ambiguous budget evidence: {basename}")
            evidence.update(matches)
        for case in matched:
            require(case["kind"] == "directed", "review applies only to directed store tests")
            case["wall_timeout_adjustment"] = {"previous_seconds": case["timeout_s"],
                "reviewed_seconds": seconds, "evidence": str(outcome), "not_a_pass_claim": True}
            case["timeout_s"] = max(case["timeout_s"], seconds)
    return evidence


def validate_bounds(cases, gates):
    names = [c["name"] for c in cases]
    require(len(names) == len(set(names)) == 600, "full collection must contain 600 unique cases")
    require(len(gates) == len(set(gates)) == 60 and set(gates) <= set(names), "gate mapping must be exactly once")
    remaining = [name for name in names if name not in gates]
    require(len(remaining) == 540 and set(gates).isdisjoint(remaining), "gate/full dispatch overlap")
    bounds = {}
    for case in cases:
        timeout = case["timeout_s"]
        require(type(timeout) is int and 0 < timeout <= 1800, "unreviewed or unbounded RTL wall timeout")
        row = {"rtl_wall_s": timeout, "runner_outer_s": timeout + 600, "independent_audit_s": 300}
        if case["kind"] in ("random", "replay"):
            spike, watchdog = case["spike_timeout_s"], case["watchdog_cycles"]
            require(type(spike) is int and 0 < spike <= 120 and type(watchdog) is int and
                    watchdog in (100000, 250000), "unreviewed replay oracle/watchdog bound")
            require(timeout + spike < row["runner_outer_s"], "runner budget cannot contain RTL and Spike")
            row.update(spike_wall_s=spike, rtl_watchdog_cycles=watchdog)
        bounds[case["name"]] = row
    return bounds


def siminfo(vdb):
    paths = list((vdb / "snps/coverage/db/testdata").glob("*/siminfo.xml"))
    require(len(paths) == 1, f"ambiguous stimulus command: {vdb}")
    info = batch.xml_root(paths[0]).find("srctest")
    require(info is not None, "missing stimulus command")
    return shlex.split(info.attrib["cmdline"]), paths[0]


def uvm_source(vdb, result, origin):
    argv, command_file = siminfo(vdb)
    plus = {}
    allowed = {"PRELOAD", "TESTCASE", "NO_FSDB", "ARA_CONTRACT_TRACE_LIMIT", "ARA_UVM_TRACE_LIMIT",
               "VECTOR_TRACE", "ARA_UVM_TRACE_AXI_WRITE", "ARA_UVM_RESET_ON_AXI",
               "ARA_UVM_RESET_READ_INDEX", "ARA_UVM_RESET_STATE_TARGET", "ntb_random_seed"}
    for arg in argv:
        if arg.startswith("+"):
            key, _, value = arg[1:].partition("=")
            require(key in allowed and key not in plus, f"unsupported/duplicate historical plusarg: {arg}")
            plus[key] = value
    require(plus.get("ntb_random_seed", "1") == "1", "unsupported UVM random seed")
    audit = result / "uvm_result.json"
    report = read(audit)
    elf = result / "work/input.elf"
    reset = {}
    kind = plus.get("ARA_UVM_RESET_ON_AXI")
    require(report.get("reset_kind") == kind, "historical reset command/audit disagree")
    if kind:
        require(kind in ("read", "write", "state"), "unknown reset mode")
        reset["kind"] = kind
        if kind == "read":
            reset["read_index"] = int(plus.get("ARA_UVM_RESET_READ_INDEX", "1"))
        if kind == "state":
            reset["target"] = plus["ARA_UVM_RESET_STATE_TARGET"]
    case = normalize({"name": plus["TESTCASE"], "kind": "uvm", "elf": str(elf),
        "elf_sha256": report["elf_sha256"], "coverage_test": plus["TESTCASE"], "timeout_s": 900,
        "oracle": "UVM+selfcheck+independent-audit", "reset": reset,
        "trace_limits": [int(plus.get(k, "100000")) for k in ("ARA_CONTRACT_TRACE_LIMIT", "ARA_UVM_TRACE_LIMIT")],
        "trace_axi_write": "ARA_UVM_TRACE_AXI_WRITE" in plus}, origin)
    case["source_files"].update(pins([audit, command_file]))
    return case


def inventory(spec_path):
    spec = read(spec_path)
    require(spec["schema_version"] == 1 and spec["workers"] == 8, "unsupported selection plan")
    cases, sources, counts = [], pins([spec_path]), {}
    for entry in spec["plans"]:
        path = absolute(entry["path"])
        plan = read(path)
        check(read(path.with_name("plan.sha256.json")))
        rows = plan.get("cases", list(plan.get("jobs", {}).values()))
        require(len(rows) == entry["count"], f"source membership changed: {path}")
        require(len({c["name"] for c in rows}) == len(rows), "duplicate source labels")
        sources.update(pins([path, path.with_name("plan.sha256.json")]))
        counts[entry["path"]] = len(rows)
        # Deliberately no checkpoint/PASS filtering, including obsolete failures.
        cases.extend(normalize(c, {"source": str(path), "name": c["name"]}) for c in rows)
    chain = absolute(spec["historical_chain"]["path"])
    require(read(chain)["passed"] == spec["historical_chain"]["passed"], "historical endpoint differs")
    visited = set()
    while "added" in read(chain):
        require(chain not in visited, "cyclic historical collection chain")
        visited.add(chain)
        item = read(chain)
        result, vdb = Path(item["functional_run"]), Path(item["new_vdb"])
        origin = {"source": str(chain), "name": item["added"]}
        if Path(item["functional_audit"]).name == "uvm_result.json":
            case = uvm_source(vdb, result, origin)
        else:
            rows = read(result / "summary.json")
            require(len(rows) == 1, "ambiguous historical fault case")
            row = rows[0]
            artifact = Path(row["artifact_dir"])
            metadata = read(artifact / "inputs.json")
            case = normalize({"name": item["added"], "kind": "directed",
                "elf": str(artifact / "input.elf"), "elf_sha256": metadata["binary"]["sha256"],
                "test": row["name"], "directed_test": {"name": row["name"], "kind": row["kind"]},
                "coverage_test": item["added"], "timeout_s": 900}, origin)
            case["source_files"].update(pins([result / "summary.json", artifact / "inputs.json"]))
        sources.update(pins([chain]))
        cases.append(case)
        chain = Path(item["baseline"]) / "collection.json"
    require(len(visited) == spec["historical_chain"]["added_count"], "historical additions missing")
    listing = absolute(spec["latest"]["path"])
    vdbs = [Path(p) for p in listing.read_text().splitlines() if p.strip()]
    require(len(vdbs) == spec["latest"]["count"] + 1 and len(set(vdbs)) == len(vdbs), "latest 48 membership differs")
    sources.update(pins([listing]))
    for vdb in vdbs[1:]:
        cases.append(uvm_source(vdb, vdb.parent, {"source": str(listing), "name": str(vdb.parent)}))
    for key, count in (("memory_selection", 40), ("gap29_selection", 7)):
        path = absolute(spec[key])
        names = read(path)["tests"]
        require(len(names) == len(set(names)) == count, f"{key} changed")
        actual = {c.get("source_name") for c in cases}
        require(set(names) <= actual, f"missing {key}: {set(names) - actual}")
        sources.update(pins([path]))
    smoke = absolute(spec["repair_smoke"]["path"])
    hashes = read(smoke / "input_sha256.json")
    rows = read(smoke / "summary.json")
    require(set(spec["repair_smoke"]["cases"]) <= {r["name"] for r in rows}, "repair regression missing")
    sources.update(pins([smoke / "input_sha256.json", smoke / "summary.json",
                         ROOT / "verification/uvm/run_store_fp16_merge_smoke.py"]))
    for label, test in spec["repair_smoke"]["cases"].items():
        markers = ["PASSED"]
        if label == "csr":
            markers.append("vec_fp_csr_order: 21 cases, 762 checks, traps=2")
        if label == "div_mask":
            markers.append("vfdiv_mask_flags: 52 cases, 1612 checks")
        case = normalize({"name": test, "kind": "uvm", "elf": str(smoke / label / "input.elf"),
            "elf_sha256": hashes[label], "coverage_test": test, "timeout_s": 600,
            "oracle": "selfcheck-markers+UVM-events-backend+independent-audit", "require_axi": False,
            "required_markers": markers, "reset": {}}, {"source": str(smoke), "name": label})
        case["source_files"].update(pins([smoke / label / "uvm_result.json"]))
        cases.append(case)
    required = {"rvv:" + n for n in spec["required_gap28_timeouts"]}
    require(required <= {c.get("source_name") for c in cases}, "old gap28 timeouts missing")
    excluded = []
    for exclusion in spec["excluded_static_seeds"]:
        require(any(c.get("seed") == exclusion["replacement_seed"] for c in cases), "static failure replacement missing")
        removed = [c for c in cases if c.get("seed") == exclusion["seed"]]
        excluded.append(dict(exclusion, origins=[o for c in removed for o in c["origins"]]))
        cases = [c for c in cases if c.get("seed") != exclusion["seed"]]
    selected = deduplicate(cases)
    require(len(selected) == spec["expected_unique_cases"], "deduplicated membership changed; review selection plan")
    sources.update(wall_budgets(selected, spec["wall_budget_review"]))
    gates = gate_selection(selected, spec["gate"], read(absolute(spec["memory_selection"]))["tests"],
                           spec["required_gap28_timeouts"])
    return {"cases": selected, "files": sources, "source_counts": counts,
            "source_entries": len(cases), "unique_cases": len(selected),
            "aliases": sum(len(c["origins"]) - 1 for c in selected),
            "latest_entries": len(vdbs) - 1, "historical_additions": len(visited),
            "repair_smoke_entries": len(spec["repair_smoke"]["cases"]), "excluded_static": excluded,
            "gate_cases": gates, "case_bounds": validate_bounds(selected, gates),
            "gate_expected_count": spec["gate"]["expected_count"], "gate_policy": spec["gate"]["policy"]}


def tool_paths():
    paths = {SCRIPT, UVM, ROOT / "verification/verify.py", HERE / "prepare_dve_waivers.py",
             HERE / "dve_waivers.tcl", DVE / "run_dve_coverage.sh", DVE / "export_dve_coverage.tcl",
             Path(sys.executable).resolve(), * (HERE / "waivers").glob("*.el")}
    paths.update((ROOT / "verification/ara_verify").glob("*.py"))
    paths.update(Path(m.__file__).resolve() for m in list(sys.modules.values())
                 if getattr(m, "__file__", None) and Path(m.__file__).resolve().is_relative_to(ROOT / "verification"))
    for name in ("dve", "xvfb-run", "Xvfb", "xauth", "timeout", "bash"):
        require(shutil.which(name), f"missing tool: {name}")
        paths.add(Path(shutil.which(name)).resolve())
    return paths


def prepare(output, selection, freeze_path):
    require(not output.exists(), "unused independent output required; no resume/overwrite")
    freeze = read(freeze_path)
    require(freeze.get("status") == "READY_FOR_FULL_RECOLLECTION" and freeze.get("repair_evidence"),
            "post-repair image approval and focused evidence required")
    check(freeze["files"])
    require(all(str(absolute(p)) in freeze["files"] for p in freeze["repair_evidence"]), "unpinned repair evidence")
    simv = Path(freeze["simv"]).resolve(strict=True)
    require(simv.parent.name == "sim" and os.access(simv, os.X_OK), "expected completed sim/simv build")
    image = batch.simulation_image(simv)
    require(image == freeze["image"] and len(image) > 1, "approved image drift/incomplete image")
    manifest = base.sources(simv.parent / "vcs_source_manifest.json")
    design = Path(str(simv) + ".vdb")
    base.pure_design(design)
    selected = inventory(selection)
    output.mkdir(parents=True, exist_ok=False)
    for sub in ("inputs", "logs", "outcomes"):
        (output / sub).mkdir()
    files = dict(selected["files"], **freeze["files"], **image)
    files.update(pins([freeze_path, simv.parent / "vcs_source_manifest.json", simv.parent / "simulator.conf", *tool_paths()]))
    files.update({r["path"]: r["sha256"] for r in manifest["files"]})
    oracles = {}
    for case in selected["cases"]:
        elf = output / "inputs" / (case["name"] + ".elf")
        shutil.copyfile(case["source_elf"], elf)
        check({str(elf): case["elf_sha256"]})
        case["frozen_elf"] = str(elf)
        case["source_files"].update(pins([elf]))
        if case["kind"] == "directed":
            case["directed_test"].update(binary=str(elf), timeout_s=case["timeout_s"])
        elif case["kind"] in ("random", "replay"):
            check({case["spike"]: case["spike_sha256"]})
            require(case["spike"] not in oracles or oracles[case["spike"]] == case["spike_sha256"], "oracle conflict")
            oracles[case["spike"]] = case["spike_sha256"]
            replay = output / "inputs" / (case["name"] + ".json")
            # FAIL is a replay selector, never a fabricated historical PASS.
            save(replay, [{"name": case["source_name"], "seed": case["seed"], "status": "FAIL", "elf": str(elf)}])
            case["replay_summary"] = str(replay)
            case["source_files"].update(pins([replay]))
    config, wrapper = output / "inputs/coverage-wrapper.json", output / "inputs/coverage_simv"
    save(config, {"simv": str(simv), "image": image, "results": str(output / "results")})
    wrapper.write_text("#!/bin/sh\nexec " + shlex.join([sys.executable, str(SCRIPT), "--coverage-exec", str(config)]) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + ".daidir").symlink_to(Path(str(simv) + ".daidir"), target_is_directory=True)
    shutil.copyfile(simv.parent / "simulator.conf", output / "inputs/simulator.conf")
    files.update(pins([config, wrapper, output / "inputs/simulator.conf"]))
    files.update(oracles)
    plan = dict(selected, files=files, reused=[], checkpoint=str(simv.parent.parent), simv=str(simv),
        image=image, oracles=oracles, wrapper=str(wrapper), wrapper_image=batch.simulation_image(wrapper),
        workers_max=8, service="ara-full-recollection-" + output.name + ".service",
        design_vdb=str(design), design_files=base.inventory(design),
        checker_inventory=sorted(str(p) for p in (ROOT / "verification/ara_verify").glob("*.py")),
        policy="CONTINUE_FUNCTIONAL_FAILURE_STOP_INFRASTRUCTURE", historical_vdb_reuse=False,
        compile=False, dve_timeout_s=1800, dve_outer_timeout_s=1920)
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pins([output / "plan.json"]))
    frozen(output, all_cases=True)
    save(output / "checkpoint.json", {"status": "PREPARED", "total": len(plan["cases"]),
        "workers": 8, "completed": 0, "cases": {}, "simulations_started": False})


def frozen(output, case=None, all_cases=False):
    plan = original_frozen(output, case, all_cases)
    require(not plan["reused"] and plan["historical_vdb_reuse"] is False, "old coverage reuse forbidden")
    require(plan["checker_inventory"] == sorted(str(p) for p in (ROOT / "verification/ara_verify").glob("*.py")), "checker inventory drift")
    if all_cases:
        require(batch.simulation_image(Path(plan["simv"])) == plan["image"], "image inventory drift")
        require(batch.simulation_image(Path(plan["wrapper"])) == plan["wrapper_image"], "wrapper inventory drift")
        require(base.inventory(Path(plan["design_vdb"])) == plan["design_files"], "design drift")
        base.sources(Path(plan["simv"]).parent / "vcs_source_manifest.json")
    return plan


def commands(output, case, plan):
    command, audit = original_commands(output, case, plan)
    if case.get("fault_vstart_probe"):
        command.append("--fault-vstart-probe")
    return command, audit


def uvm_commands(output, case, plan):
    target = output / "results" / case["name"]
    reset = case.get("reset", {})
    command = ["bash", str(UVM), plan["simv"], case["frozen_elf"], case["coverage_test"], str(target)]
    if reset:
        command.append(reset["kind"])
    audit = [sys.executable, "-m", "ara_verify.uvm_dut", "--require-events", "--require-backend",
             "--require-axi", "--require-axi-write", "--vector-trace", str(target / "work/vector_trace.csv"),
             "--log", str(target / "work/run.vcs.log"), "--simv", plan["simv"],
             "--elf", str(target / "work/input.elf"), "--output", str(target / "independent_uvm_audit.json")]
    if reset:
        audit += ["--expect-reset-abort", reset["kind"]]
    limits = case.get("trace_limits", [100000, 100000])
    env = {"ARA_VCS_CODE_COVERAGE": "1", "ARA_VCS_TIMEOUT_SECONDS": str(case["timeout_s"]),
           "ARA_CONTRACT_TRACE_LIMIT": str(limits[0]), "ARA_UVM_TRACE_LIMIT": str(limits[1]),
           "ARA_UVM_TRACE_AXI_WRITE": "1" if case.get("trace_axi_write") else "0",
           "ARA_UVM_RESET_STATE_TARGET": reset.get("target", ""),
           "ARA_UVM_RESET_READ_INDEX": str(reset.get("read_index", 1))}
    if not case.get("require_axi", True):
        audit.remove("--require-axi")
        audit.remove("--require-axi-write")
        work = target / "work"
        command = ["timeout", "--foreground", str(case["timeout_s"]), plan["simv"], "-no_save",
            "-l", str(work / "run.vcs.log"), "+PRELOAD=" + str(work / "input.elf"),
            "+TESTCASE=" + case["coverage_test"], "+NO_FSDB", "+VECTOR_TRACE=" + str(work / "vector_trace.csv"),
            "+ARA_CONTRACT_TRACE_LIMIT=" + str(limits[0]), "+ARA_UVM_TRACE_LIMIT=" + str(limits[1]),
            "-cm", base.METRICS, "-cm_dir", str(target / "code.vdb"), "-cm_name", case["coverage_test"]]
    return command, audit, env


def uvm_verdict(rc, report):
    if rc == 124:
        return "RTL_TIMEOUT"
    require(rc in (0, 1) and report is not None and report.get("status") in ("PASS", "FAIL"),
            f"unclassified UVM runner failure: rc={rc}")
    require((rc == 0) == (report["status"] == "PASS"), "UVM audit/runner disagreement")
    require(not any(re.search(r"cannot read|cannot hash|malformed|is missing:|libraries are missing", issue, re.I)
                    for issue in report.get("issues", [])), "UVM checker/input integrity failure")
    return report["status"]


def recover_uvm_report(output, case, target, audit, env):
    """Audit a bounded nonzero simulator exit skipped by the shell's set -e."""
    for name in ("run.vcs.log", "vector_trace.csv"):
        path = target / "work" / name
        require(path.is_file() and path.stat().st_size > 0,
                f"unclassified runner exit without simulation evidence: {path}")
    primary = list(audit)
    primary[primary.index("--output") + 1] = str(target / "uvm_result.json")
    rc = batch.invoke(primary, output / "logs" / (case["name"] + "-recovered-audit.log"), 300, env)
    require(rc in (0, 1) and (target / "uvm_result.json").is_file(), "post-exit UVM checker failed")
    report = read(target / "uvm_result.json")
    require((rc == 0) == (report.get("status") == "PASS"), "post-exit UVM checker disagreement")
    return report


def probe_capture(artifact, diagnostic):
    try:
        return closure.check_probe(artifact, diagnostic)
    except RuntimeError as error:
        # Existing parser's explicit value comparisons are functional verdicts;
        # missing responses, incomplete captures and malformed fields still stop.
        if str(error).startswith("probe differs:") or str(error) == "probe lacks backend exception":
            return {"status": "FAIL", "reason": str(error)}
        raise


def reset_target_matches(log, expected):
    targets = re.findall(r"^\[ARA_UVM_RESET_TEST\] kind=state observed=1 target=(\S+) actual=(\S+)",
                         log, re.M)
    require(len(targets) == 1, "missing/ambiguous reset state marker")
    return targets[0][0] == expected


def worker(output, name):
    path = output / "outcomes" / (name + ".json")
    require(not path.exists(), "existing outcome; no retries")
    target = output / "results" / name
    try:
        plan = frozen(output)
        case = next(c for c in plan["cases"] if c["name"] == name)
        frozen(output, case)
        require(not target.exists(), "existing result; no retries")
        if case["kind"] not in ("uvm", "axpy"):
            rc = batch.worker(output, name)
            item = read(path)
            if rc:
                return rc
            if item["status"] == "PASS" and case.get("fault_vstart_probe"):
                artifact = Path(read(target / "summary.json")[0]["artifact_dir"])
                capture = probe_capture(artifact, Path(case["diagnostic_probe"]))
                save(target / "fault_vstart_capture.json", capture)
                if capture["status"] == "FAIL":
                    item.update(status="FAIL", passed_only=False, reason=capture["reason"])
                item["files"].update(pins([target / "fault_vstart_capture.json"]))
        else:
            command, audit, env = uvm_commands(output, case, plan)
            direct_uvm = not case.get("require_axi", True)
            simulator_rc = None
            if direct_uvm:
                (target / "work").mkdir(parents=True)
                shutil.copyfile(case["frozen_elf"], target / "work/input.elf")
                # Isolate simulator scratch files just like the established shell runner.
                import subprocess
                save(output / "logs" / (name + ".command.json"), {"command": command, "cwd": str(target / "work")})
                with (target / "work/console.log").open("w") as stream:
                    rc = subprocess.run(command, cwd=target / "work", env=dict(os.environ, **env),
                        stdout=stream, stderr=subprocess.STDOUT, timeout=case["timeout_s"] + 600, check=False).returncode
                simulator_rc = rc
                require(rc in (0, 1, 124), f"unclassified simulator exit {rc}")
                if rc != 124:
                    primary = audit[:-1] + [str(target / "uvm_result.json")]
                    audit_rc = batch.invoke(primary, output / "logs" / (name + "-primary-audit.log"), 300, env)
                    require(audit_rc in (0, 1), "UVM checker crashed")
                    rc = audit_rc
            else:
                rc = batch.invoke(command, output / "logs" / (name + ".log"), case["timeout_s"] + 600, env)
            batch.check_environment_logs(target)
            check({str(target / "work/input.elf"): case["elf_sha256"]})
            report_path = target / "uvm_result.json"
            report = read(report_path) if report_path.exists() else None
            if not direct_uvm and rc == 1 and report is None:
                report = recover_uvm_report(output, case, target, audit, env)
            status = uvm_verdict(rc, report)
            if report is not None:
                require(report.get("elf_sha256") == case["elf_sha256"] and report.get("sim_image_sha256") == plan["image"], "UVM identity drift")
            if status == "PASS":
                require(batch.invoke(audit, output / "logs" / (name + "-audit.log"), 300, env) == 0, "independent UVM audit failed")
                require(read(target / "independent_uvm_audit.json") == report, "independent UVM audit differs")
                reset = case.get("reset", {})
                if reset.get("kind") == "state":
                    log = (target / "work/run.vcs.log").read_text(errors="replace")
                    if not reset_target_matches(log, reset["target"]):
                        status = "FAIL"
                        save(target / "reset_target_comparison.json", {"status": status, "expected": reset["target"]})
                if case.get("cycle_limit") is not None:
                    measured = cycles(target / "work/run.vcs.log")
                    if measured > case["cycle_limit"]:
                        status = "FAIL"
                    save(target / "cycle_comparison.json", {"status": status, "cycles": measured, "limit": case["cycle_limit"]})
                if case.get("required_markers"):
                    log = (target / "work/run.vcs.log").read_text(errors="replace")
                    if any(marker not in log for marker in case["required_markers"]) or re.search(r"^FAIL(?:[ :]|$)|FAILED|Fatal:|Error:", log, re.M):
                        status = "FAIL"
                if simulator_rc not in (None, 0):
                    status = "FAIL"
            vdb = target / "code.vdb"
            rejection, vdb_files = None, {}
            try:
                vdb_files = batch.valid_vdb(vdb, case["coverage_test"], plan["simv"])
            except (OSError, ValueError, batch.ET.ParseError, EOFError, IndexError) as error:
                rejection = str(error)
                require(status != "PASS", f"PASS without complete VDB: {error}")
            evidence = [p for p in target.rglob("*") if p.is_file() and not p.is_relative_to(vdb)]
            item = {"name": name, "kind": case["kind"], "status": status, "reused": False,
                "elf_sha256": case["elf_sha256"], "returncode": rc, "files": pins(evidence),
                "simulator_returncode": simulator_rc,
                "vdb": str(vdb), "coverage_test": case["coverage_test"], "vdb_files": vdb_files,
                "vdb_valid": bool(vdb_files), "passed_only": status == "PASS" and bool(vdb_files),
                "vdb_rejection": rejection, "issues": report.get("issues", []) if report else ["bounded RTL timeout"]}
        frozen(output, case)
        item.update(contract=case["contract"], origins=case["origins"])
        save(path, item)
        batch.publish(output, item)
        return 0
    except Exception as error:
        previous = read(path) if path.exists() else None
        item = {"name": name, "status": "INFRASTRUCTURE_ERROR", "reason": f"{type(error).__name__}: {error}",
                "previous_outcome": previous, "result_dir": str(target), "passed_only": False}
        save(path, item)
        batch.publish(output, item)
        return 1


def summarize(output, plan):
    outcomes, selected = [], []
    for case in plan["cases"]:
        item = read(output / "outcomes" / (case["name"] + ".json"))
        require(item["name"] == case["name"] and item["elf_sha256"] == case["elf_sha256"] and item["contract"] == case["contract"], "outcome contract drift")
        check(item["files"])
        vdb = Path(item["vdb"]).resolve()
        require(vdb.is_relative_to(output / "results" / case["name"]), "old/foreign VDB rejected")
        if item["status"] == "PASS":
            require(item["passed_only"] and item["vdb_valid"] and not item["reused"], "unadmitted PASS")
            require(batch.valid_vdb(vdb, case["coverage_test"], plan["simv"]) == item["vdb_files"], "PASS VDB drift")
            selected.append(item)
        else:
            require(not item["passed_only"], "failed case admitted")
        outcomes.append(item)
    save(output / "all-outcomes.json", outcomes)
    databases = {plan["design_vdb"]: plan["design_files"], **{i["vdb"]: i["vdb_files"] for i in selected}}
    require(len(databases) == len(selected) + 1, "duplicate VDB")
    base.pure_design(Path(plan["design_vdb"]))
    require(all(base.inventory(Path(p)) == h for p, h in databases.items()), "VDB drift before DVE")
    save(output / "dve-inputs.before.json", databases)
    inputs = output / "dve-inputs.txt"
    inputs.write_text("\n".join(databases) + "\n")
    target = output / "dve"
    require(batch.invoke(["bash", str(DVE / "run_dve_coverage.sh"), str(target), "--inputs-file", str(inputs)],
            output / "logs/dve.log", plan["dve_outer_timeout_s"],
            {"DVE_COVERAGE_TIMEOUT": str(plan["dve_timeout_s"]), "DVE_WAIVERS": "auto"}) == 0, "DVE export failed")
    expected = [str(Path(i["vdb"]).with_suffix("") / i["coverage_test"]) for i in selected]
    require((target / "selected_tests.txt").read_text().splitlines() == expected, "DVE test selection differs")
    require((target / "inputs.txt").read_text().splitlines() == list(databases), "DVE database selection differs")
    after = {p: base.inventory(Path(p)) for p in databases}
    save(output / "dve-inputs.after.json", after)
    require(after == databases, "DVE modified input databases")
    waiver = read(target / "waiver_status.json")
    require(waiver["status"] in ("APPLIED", "NOT_APPLICABLE_UNREVIEWED_DESIGN"), "unexpected waiver state")
    reports = [target / "summary.csv", target / "waiver_status.json", target / "selected_tests.txt", target / "inputs.txt"]
    if waiver["status"] == "APPLIED":
        reports += [target / "summary_waived.csv", target / "exclusions.el"]
    save(output / "collection.json", {"status": "PASS" if len(selected) == len(outcomes) else "COMPLETE_WITH_FAILURES",
        "total": len(outcomes), "passed": len(selected), "image": plan["image"], "historical_vdb_reuse": False,
        "counts": dict(Counter(i["status"] for i in outcomes)), "waiver": waiver,
        "scope": "fresh-image independently audited PASS-only; raw full hierarchy; waiver applicability explicit",
        "failed_cases_excluded": [i for i in outcomes if i["status"] != "PASS"], "reports": pins(reports)})
    return outcomes


def schedule(output, names, jobs):
    """The gate is part of the fresh collection, not a separate-image PASS reuse."""
    plan = read(output / "plan.json")
    gate = plan["gate_cases"]
    require(jobs == 8 and len(gate) == len(set(gate)) == plan["gate_expected_count"] and len(gate) >= 60
            and set(gate) <= set(names),
            "invalid full-recollection gate/worker count")
    require(not (output / "gate.json").exists(), "gate already attempted; no automatic retry")
    save(output / "gate.json", {"status": "RUNNING", "cases": gate, "full_dispatch_started": False})
    try:
        original_schedule(output, gate, jobs)
        outcomes = [read(output / "outcomes" / (name + ".json")) for name in gate]
        failed = [{"name": item["name"], "status": item["status"]} for item in outcomes
                  if item["status"] != "PASS" or not item.get("passed_only")]
        save(output / "gate.json", {"status": "FAIL" if failed else "PASS", "cases": gate,
            "failed": failed, "full_dispatch_started": False,
            "outcome_files": pins(output / "outcomes" / (name + ".json") for name in gate)})
        require(not failed, "known-failure/adjacent gate failed; remaining full queue NOT dispatched")
        frozen(output, all_cases=True)
    except Exception as error:
        record = read(output / "gate.json")
        record.update(status="FAIL" if record.get("status") == "FAIL" else "INFRASTRUCTURE_ERROR",
                      reason=str(error), full_dispatch_started=False)
        save(output / "gate.json", record)
        raise
    # Keep both scheduler histories. Gate workers already published their fresh
    # outcomes; they are included once in final DVE and are never run twice.
    (output / "scheduler").rename(output / "gate-scheduler")
    remaining = [name for name in names if name not in gate]
    record = read(output / "gate.json")
    record.update(full_dispatch_started=True, remaining=len(remaining))
    save(output / "gate.json", record)
    if remaining:
        original_schedule(output, remaining, jobs)


def systemd_command(output, plan):
    return ["systemd-run", "--user", "--unit=" + plan["service"], "--property=KillMode=control-group",
            "--property=Restart=no", "--property=RemainAfterExit=no", "--property=TimeoutStopSec=60",
            "--working-directory=" + str(ROOT), "--setenv=ARA_CHECKPOINT_UNIT=" + plan["service"],
            "--setenv=PATH=" + os.environ["PATH"], "--setenv=PYTHONPATH=" + str(ROOT / "verification"),
            *["--setenv=" + k + "=" + os.environ[k] for k in ("SNPSLMD_LICENSE_FILE", "LM_LICENSE_FILE", "VCS_HOME", "LD_LIBRARY_PATH") if k in os.environ],
            sys.executable, str(SCRIPT), "--output", str(output), "--execute"]


def execute(output):
    rc = batch.execute(output, 8)
    if rc:
        return rc
    # A worker's zero means "safe to continue dispatch". The service's zero
    # must mean the entire campaign passed, not merely that DVE finished.
    return 0 if read(output / "checkpoint.json")["status"] == "PASS" else 1


def main():
    batch.SCRIPT, batch.frozen, batch.commands, batch.summarize = SCRIPT, frozen, commands, summarize
    batch.schedule = schedule
    if len(sys.argv) > 2 and sys.argv[1] == "--coverage-exec":
        argv = batch.adapter_command(read(sys.argv[2]), sys.argv[3:], Path.cwd().resolve())
        with Path("coverage.command.json").open("x") as stream:
            json.dump({"command": argv, "cwd": str(Path.cwd())}, stream)
        os.execv(argv[0], argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--freeze", type=Path)
    modes = parser.add_mutually_exclusive_group()
    for name in ("inventory", "prepare", "execute", "systemd-command"):
        modes.add_argument("--" + name, action="store_true")
    modes.add_argument("--worker")
    modes.add_argument("--directed")
    parser.add_argument("--list-cases", action="store_true", help="include complete provenance/aliases in read-only inventory JSON")
    args = parser.parse_args()
    if args.inventory or not any((args.prepare, args.execute, args.systemd_command, args.worker, args.directed)):
        data = inventory(args.selection.resolve())
        print(json.dumps(data if args.list_cases else {k: v for k, v in data.items() if k not in ("cases", "files", "case_bounds")}, indent=2))
        return 0
    require(args.output is not None, "--output required")
    output = base.checked_output(args.output)
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    # Prevent caller reset/coverage knobs from leaking into ordinary replay.
    for key in list(os.environ):
        if key.startswith(("ARA_UVM_", "ARA_CONTRACT_", "ARA_VCS_")):
            del os.environ[key]
    if args.prepare:
        require(args.freeze is not None, "--freeze required after repair/build completion")
        prepare(output, args.selection.resolve(), args.freeze.resolve())
        print(f"PREPARED, NOT LAUNCHED: {output}")
        return 0
    plan = frozen(output)
    if args.systemd_command:
        print(shlex.join(systemd_command(output, plan)))
        return 0
    require(os.environ.get("ARA_CHECKPOINT_UNIT") == plan["service"] and os.environ.get("INVOCATION_ID"), "registered systemd service required")
    if args.worker:
        return worker(output, args.worker)
    if args.directed:
        return batch.directed(output, args.directed)
    return execute(output)


if __name__ == "__main__":
    raise SystemExit(main())
