#!/usr/bin/env python3
"""Prepare 424 current-image replays plus 21 audited current-image VDBs.

No compilation, historical VDB reuse, exploration export, or automatic retry.
Execute only in the registered control-group systemd service. Functional test
failures continue through the existing eight-worker batch runner; infrastructure
failures stop dispatch. Historical tool hashes are provenance, not current pins.
"""
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

import run_vcs_dve_batch as batch
import run_remaining5_closure as closure
from ara_verify.plan import _full_architecture_match, _full_vector_match

ROOT, HERE, base = batch.ROOT, batch.HERE, batch.base
SCRIPT = Path(__file__).resolve()
OUTPUT = ROOT / "verification/out/vcs-current-coverage-20260927-01"
SERVICE = "ara-vcs-current-coverage-20260927-01.service"
HISTORY = ROOT / "verification/out/vcs-dve-timeout-repair-20260927-05"
CURRENT = ROOT / "verification/out/repair-closure-coverage-20260927-01"
CLOSURE = ROOT / "verification/out/vlsseg-cov-closure-20260927-01"
DVE = HERE / "dve_hierarchy"
OVERLAPS = {"vslide_mask_edges", "vreduction_lmul_edges", "vreduction_overlap_edges"}
read, save, check, pins = batch.read, batch.save, batch.check, batch.pins
sha256, simulation_image = batch.sha256, batch.simulation_image
_batch_frozen = batch.frozen


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_file(files, name):
    found = [Path(p) for p in files if Path(p).name == name]
    require(len(found) == 1, f"expected one archived {name}")
    return found[0]


def contract(case):
    """Labels and no-build paths are not oracle semantics; budgets are retained."""
    kind = case["kind"]
    result = {"mode": "replay" if kind in ("random", "replay") else kind,
              "oracle": case["oracle"], "config": "default", "commit_trace": True,
              "timeout_s": case["timeout_s"], "fault_vstart_probe": bool(case.get("fault_vstart_probe")),
              "require_complete": True, "require_trace": True}
    if kind == "directed":
        test = case["directed_test"]
        result.update(test=test["name"], test_kind=test["kind"], runner_seed=1)
    elif kind in ("random", "replay"):
        result.update(runner_seed=case["seed"], spike_sha256=case["spike_sha256"], spike_isa=base.ISA,
                      spike_timeout_s=case["spike_timeout_s"], watchdog_cycles=case["watchdog_cycles"],
                      require_vector=True, require_full_match=True)
    elif kind == "axpy":
        result.update(test="remaining15_axpy", cycle_limit=2810, independent_uvm_audit=True)
    else:
        raise ValueError(f"unsupported oracle kind: {kind}")
    return result


def case_key(case):
    return case["elf_sha256"], json.dumps(contract(case), sort_keys=True)


def history_selection():
    # Check only the archived plan itself, not plan.files (obsolete tools/RTL).
    check(read(HISTORY / "plan.sha256.json"))
    plan, state = read(HISTORY / "plan.json"), read(HISTORY / "checkpoint.json")
    names = [c["name"] for c in plan["cases"]]
    require(len(names) == len(set(names)) == state["total"] == state["completed"] == 445,
            "historical campaign is incomplete or has duplicate identities")
    require(set(state["cases"]) == set(names) and state["status"] in ("PASS", "COMPLETE_WITH_FAILURES"),
            "historical checkpoint selection differs")
    selected = [c for c in plan["cases"] if state["cases"][c["name"]]["status"] == "PASS"]
    require(len(selected) == state["passed"] == 427, "expected exactly 427 historical PASS stimuli")
    cases, oracles = [], {}
    for original in selected:
        name = original["name"]
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name), "unsafe historical name")
        outcome_path = HISTORY / "outcomes" / (name + ".json")
        outcome = read(outcome_path)
        require(outcome["name"] == name and outcome["status"] == "PASS" and
                outcome["passed_only"] is True and outcome["elf_sha256"] == original["elf_sha256"],
                "historical outcome is not matching PASS")
        summary = unique_file(outcome["files"], "summary.json")
        audit = unique_file(outcome["files"], "independent_audit.json")
        inputs = unique_file(outcome["files"], "inputs.json")
        proof = {str(p): outcome["files"][str(p)] for p in (summary, audit, inputs)}
        check(proof)
        rows, metadata = read(summary), read(inputs)
        require(len(rows) == 1 and rows[0]["status"] == "PASS", "historical summary is not one PASS")
        row = rows[0]
        artifact = Path(row["artifact_dir"]).resolve()
        require(inputs.resolve() == artifact / "inputs.json" and row["name"] == original["source_name"],
                "historical summary/input/case binding differs")
        batch.audit_ok(read(audit), original, artifact)
        require(metadata["binary"]["sha256"] == original["elf_sha256"], "historical ELF metadata differs")
        elf = Path(original["frozen_elf"])
        binaries = {str(elf): original["elf_sha256"], str(artifact / "input.elf"): original["elf_sha256"]}
        check(binaries)
        proof.update(binaries)
        proof.update(pins([outcome_path]))
        case = dict(original, source_files=proof, source_summary=str(summary), source_audit=str(audit),
                    source_artifact=str(artifact), source_elf=str(elf), fault_vstart_probe=False,
                    selection_origin="historical_PASS_stimulus_only")
        if case["kind"] == "directed":
            require(case["directed_test"]["name"] == row["name"] and
                    case["oracle"] == "selfcheck+trace-audit", "historical directed contract differs")
        else:
            require(case["oracle"] == "Spike+scalar+vector+independent-audit" and
                    metadata["spike"]["sha256"] == case["spike_sha256"], "historical replay oracle differs")
            require(case.get("seed", row["seed"]) == row["seed"], "historical replay seed differs")
            case["seed"] = row["seed"]
            oracle, digest = case["spike"], case["spike_sha256"]
            if oracle not in oracles:
                check({oracle: digest})
                oracles[oracle] = digest
            require(oracles[oracle] == digest, "historical cases disagree on Spike identity")
        case["contract"] = contract(case)
        cases.append(case)
    return cases, {"directory": str(HISTORY), "selected": 427, "total": 445,
                   "old_verdict_is_selection_only": True, "old_vdb_reuse": False,
                   "excluded": [n for n in names if state["cases"][n]["status"] != "PASS"]}


def current_reuse():
    collection = read(CLOSURE / "collection.json")
    check(read(CURRENT / "plan.sha256.json"))
    check(read(CURRENT / "runtime.sha256.json"))
    plan, runtime = read(CURRENT / "plan.json"), read(CURRENT / "runtime.json")
    image = simulation_image(CURRENT / "sim/simv")
    require(collection["status"] == "PASS" and collection["coverage_verified"] is True and
            collection["passed"] == 21 and len(collection["cases"]) == 21 and
            collection["image"] == runtime["image"] == image, "current collection/image is not matching PASS")
    require(simulation_image(CURRENT / "inputs/coverage_simv") == runtime["wrapper_image"],
            "current reused wrapper image changed")
    require({r["name"] for r in collection["cases"]} == set(plan["jobs"]) and len(plan["jobs"]) == 21,
            "current collection is not the exact 21-case set")
    require(Counter(s["kind"] for s in plan["jobs"].values()) == {"replay": 14, "directed": 6, "axpy": 1},
            "current collection checking strategies differ")
    require({n for n, s in plan["jobs"].items() if s.get("fault_vstart_probe")} ==
            {"seed1401-original", "seed1402-original"}, "current probe contract differs")
    require({n for n, s in plan["jobs"].items() if s.get("replacement")} ==
            {"seed1409-replacement", "seed1410-replacement", "seed1412-replacement"},
            "current replacement provenance differs")
    cases, outcomes, oracles = [], [], {}
    for item in collection["cases"]:
        spec = plan["jobs"][item["name"]]
        require(item["status"] == "PASS" and item["admitted"] is True and
                item["elf_sha256"] == spec["elf_sha256"], "non-PASS or wrong reused ELF")
        check(item["files"])
        check({spec["elf"]: spec["elf_sha256"]})
        result = CURRENT / "results" / ("vlsseg_retry1800" if item["name"] == "vlsseg" else item["name"])
        case = dict(spec, timeout_s=item.get("wall_timeout_s", spec["timeout_s"]),
                    source_elf=spec["elf"], frozen_elf=spec["elf"],
                    source_files={spec["elf"]: spec["elf_sha256"]}, selection_origin="current_audited_PASS")
        evidence = dict(item["files"])
        if spec["kind"] == "axpy":
            report = read(result / "uvm_result.json")
            require(report == read(result / "independent_uvm_audit.json") and report["status"] == "PASS" and
                    not report["issues"] and report["elf_sha256"] == spec["elf_sha256"] and
                    report["sim_image_sha256"] == runtime["wrapper_image"] and
                    read(result / "cycle_comparison.json")["status"] == "PASS" and
                    closure.prior.cycles(result / "work/run.vcs.log") <= 2810, "reused AXPY proof differs")
            work = result / "work"
            case.update(oracle="UVM+selfcheck+independent-audit+cycle-limit",
                        source_audit=str(result / "independent_uvm_audit.json"), source_name="remaining15_axpy")
        else:
            summary, audit = result / "summary.json", result / "independent_audit.json"
            if item["name"] == "vlsseg":
                audit = CLOSURE / "independent_audit.json"
            rows = read(summary)
            require(len(rows) == 1 and rows[0]["status"] == "PASS", "reused summary is not one PASS")
            row = rows[0]
            artifact = Path(row["artifact_dir"]).resolve()
            require(artifact.is_relative_to(result), "reused artifact escaped its result")
            metadata = read(artifact / "inputs.json")
            require(metadata["binary"]["sha256"] == spec["elf_sha256"] and
                    metadata["simv"]["image_sha256"] == runtime["wrapper_image"], "reused ELF/wrapper differs")
            check({str(artifact / "input.elf"): spec["elf_sha256"]})
            batch.audit_ok(read(audit), dict(spec, source_name=row["name"]), artifact)
            case.update(source_name=row["name"], source_audit=str(audit), source_summary=str(summary),
                        source_artifact=str(artifact))
            if spec["kind"] == "directed":
                require(row["name"] == spec["test"] and row["returncode"] == 0,
                        "reused directed test/completion differs")
                case.update(oracle="selfcheck+trace-audit", directed_test={"name": spec["test"], "kind": "rvv"})
            else:
                require(row["name"] == spec["case"] and row["seed"] == spec["seed"] and
                        row["spike_returncode"] == row["rtl_returncode"] == 0 and
                        row["spike_timed_out"] is False and row["rtl_timed_out"] is False,
                        "reused replay did not complete")
                scalar, vector = read(artifact / "commit_comparison.json"), read(artifact / "vector_commit_comparison.json")
                require(row["comparison"] == scalar and row["vector_commit"] == vector and
                        _full_architecture_match(scalar) and _full_vector_match(vector), "reused strict oracle differs")
                case.update(oracle="Spike+scalar+vector+independent-audit", spike=metadata["spike"]["path"],
                            spike_sha256=metadata["spike"]["sha256"], spike_timeout_s=60, watchdog_cycles=100000)
                oracle, digest = case["spike"], case["spike_sha256"]
                if oracle not in oracles:
                    check({oracle: digest})
                    oracles[oracle] = digest
                require(oracles[oracle] == digest, "current cases disagree on Spike identity")
                enabled = "+ARA_FAULT_VSTART_PROBE" in read(artifact / "rtl.command.json")["command"]
                require(enabled == spec["fault_vstart_probe"], "reused probe opt-in differs")
                if enabled:
                    diagnostic = Path(spec["diagnostic_probe"])
                    require(closure.check_probe(artifact, diagnostic) == read(result / "fault_vstart_capture.json"),
                            "reused fault/vstart capture differs")
                    evidence.update(pins([diagnostic]))
            work = artifact / "work" if spec["kind"] == "directed" else artifact
        vdb = Path(item["vdb"]).resolve()
        require(vdb == work / "code.vdb" and item["coverage_test"] == spec["coverage_test"],
                "reused VDB path/test binding differs")
        require(batch.valid_vdb(vdb, item["coverage_test"], str(CURRENT / "sim/simv")) == item["vdb_files"],
                "reused VDB changed")
        require(read(work / "coverage.command.json")["command"][0] == str(CURRENT / "sim/simv"),
                "reused command used a different real image")
        case["contract"] = contract(case)
        cases.append(case)
        outcomes.append(dict(item, schema_version=1, kind=spec["kind"], reused=True, vdb_valid=True,
                             passed_only=True, returncode=0, files=evidence, vdb_rejection=None,
                             source_audit=case["source_audit"], oracle=case["oracle"], contract=case["contract"],
                             replacement=bool(spec.get("replacement")),
                             fault_vstart_probe=bool(spec.get("fault_vstart_probe")),
                             reuse_collection=str(CLOSURE / "collection.json")))
    return cases, outcomes, runtime


def deduplicate(historical, reused):
    by_key = {case_key(c): c for c in reused}
    require(len(by_key) == len(reused) == 21, "duplicate current ELF/checking contracts")
    cases, aliases, seen = list(reused), [], set(by_key)
    for case in historical:
        key = case_key(case)
        if key in by_key:
            aliases.append({"historical": case["name"], "current": by_key[key]["name"],
                            "elf_sha256": key[0], "contract": contract(case),
                            "source_files": case["source_files"]})
        else:
            require(key not in seen, "unexpected historical duplicate ELF/checking contract")
            seen.add(key)
            cases.append(case)
    require(len(cases) == 445 and len(aliases) == 3 and {a["current"] for a in aliases} == OVERLAPS,
            "expected 424 new + 21 reused, with exactly three approved directed overlaps")
    require(len({c["name"] for c in cases}) == 445, "duplicate case labels")
    return cases, aliases


def tool_paths():
    imported = {Path(m.__file__).resolve() for m in list(sys.modules.values())
                if getattr(m, "__file__", None) and Path(m.__file__).resolve().is_relative_to(ROOT / "verification")
                and not Path(m.__file__).resolve().is_relative_to(ROOT / "verification/tests")}
    paths = imported | set((ROOT / "verification/ara_verify").rglob("*.py")) | {
        SCRIPT, ROOT / "verification/verify.py", ROOT / "verification/uvm/run_real_dut_case.sh",
        DVE / "run_dve_coverage.sh", DVE / "export_dve_coverage.tcl", HERE / "dve_waivers.tcl",
        HERE / "prepare_dve_waivers.py", HERE / "waivers/operand_flush.el", Path(sys.executable).resolve(),
        ROOT / "install/riscv-gcc/bin/riscv64-unknown-elf-readelf",
        ROOT / "install/riscv-llvm/bin/llvm-objdump"}
    for name in ("dve", "xvfb-run", "Xvfb", "xauth", "timeout"):
        path = shutil.which(name)
        require(path is not None, f"missing coverage tool: {name}")
        paths.add(Path(path).resolve())
    return sorted(paths)


def prepare(output):
    require(not output.exists(), "independent unused output required; no overwrite/resume")
    manifest = base.sources(CURRENT / "sim/vcs_source_manifest.json")
    historical, selection = history_selection()
    reused, outcomes, runtime = current_reuse()
    cases, aliases = deduplicate(historical, reused)
    design = CURRENT / "sim/simv.vdb"
    base.pure_design(design)
    require(base.inventory(design) == runtime["design_files"], "compiled coverage design changed")
    output.mkdir(parents=True, exist_ok=False)
    for subdir in ("inputs", "logs", "outcomes"):
        (output / subdir).mkdir()
    files = pins(tool_paths() + [HISTORY / p for p in ("plan.json", "plan.sha256.json", "checkpoint.json")] +
                 [CLOSURE / "collection.json", CURRENT / "plan.json", CURRENT / "plan.sha256.json",
                  CURRENT / "runtime.json", CURRENT / "runtime.sha256.json", CURRENT / "sim/simulator.conf",
                  CURRENT / "sim/vcs_source_manifest.json"])
    files.update({r["path"]: r["sha256"] for r in manifest["files"]})
    files.update(runtime["image"])
    for alias in aliases:
        files.update(alias["source_files"])
    reused_names = [c["name"] for c in reused]
    oracles = {}
    for case in cases:
        if "spike" in case:
            require(case["spike"] not in oracles or oracles[case["spike"]] == case["spike_sha256"],
                    "cases disagree on Spike identity")
            oracles[case["spike"]] = case["spike_sha256"]
        if case["name"] in reused_names:
            continue
        elf = output / "inputs" / (case["name"] + ".elf")
        shutil.copyfile(case["frozen_elf"], elf)
        check({str(elf): case["elf_sha256"]})
        case["frozen_elf"] = str(elf)
        case["source_files"].update(pins([elf]))
        if case["kind"] == "directed":
            case["directed_test"] = dict(case["directed_test"], binary=str(elf))
        else:
            replay = output / "inputs" / (case["name"] + ".json")
            save(replay, [{"name": case["source_name"], "profile": read(case["source_summary"])[0].get("profile", ""),
                           "seed": case["seed"], "status": "PASS", "elf": str(elf)}])
            case["replay_summary"] = str(replay)
            case["source_files"].update(pins([replay]))
    config, wrapper = output / "inputs/coverage-wrapper.json", output / "inputs/coverage_simv"
    save(config, {"simv": str(CURRENT / "sim/simv"), "image": runtime["image"], "results": str(output / "results")})
    wrapper.write_text("#!/bin/sh\nexec " + shlex.join([sys.executable, str(SCRIPT), "--coverage-exec", str(config)]) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + ".daidir").symlink_to(CURRENT / "sim/simv.daidir", target_is_directory=True)
    shutil.copyfile(CURRENT / "sim/simulator.conf", output / "inputs/simulator.conf")
    files.update(pins([config, wrapper, output / "inputs/simulator.conf"]))
    files.update(oracles)
    for item in outcomes:
        path = output / "outcomes" / (item["name"] + ".json")
        save(path, item)
        files.update(pins([path]))
    plan = {"schema_version": 1, "cases": cases, "files": files, "reused": reused_names,
            "checkpoint": str(CURRENT), "source_selection": selection, "aliases": aliases,
            "simv": str(CURRENT / "sim/simv"), "image": runtime["image"], "oracles": oracles,
            "wrapper": str(wrapper), "wrapper_image": simulation_image(wrapper), "workers_max": 8,
            "service": SERVICE, "dve_timeout_s": 1200, "dve_outer_timeout_s": 1320,
            "design_vdb": str(design), "design_files": runtime["design_files"],
            "checker_inventory": sorted(str(p) for p in (ROOT / "verification/ara_verify").rglob("*.py")),
            "policy": "CONTINUE_FUNCTIONAL_FAILURE_STOP_INFRASTRUCTURE", "compile": False,
            "historical_vdb_reuse": False, "historical_tool_hashes_enforced": False,
            "coverage_policy": "CURRENT_IMAGE_PASS_ONLY_FULL_HIERARCHY_WITH_REVIEWED_WAIVERS"}
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pins([output / "plan.json"]))
    frozen(output, all_cases=True)
    save(output / "checkpoint.json", {"status": "PREPARED", "phase": "current RTL coverage recollection",
         "total": 445, "workers": 8, "cases": {}, "source_selection": selection, "simulations_started": False})
    for item in outcomes:
        batch.publish(output, item)


def frozen(output, case=None, all_cases=False):
    plan = _batch_frozen(output, case, all_cases)
    require(plan["schema_version"] == 1 and len(plan["cases"]) == 445 and len(plan["reused"]) == 21,
            "recollection plan schema/count differs")
    require(plan["checker_inventory"] == sorted(str(p) for p in (ROOT / "verification/ara_verify").rglob("*.py")),
            "current checker inventory drift")
    if all_cases:
        base.sources(CURRENT / "sim/vcs_source_manifest.json")
        require(simulation_image(Path(plan["simv"])) == plan["image"] and
                simulation_image(Path(plan["wrapper"])) == plan["wrapper_image"], "current image inventory drift")
        require(base.inventory(Path(plan["design_vdb"])) == plan["design_files"], "design VDB changed")
        for name in plan["reused"]:
            item = read(output / "outcomes" / (name + ".json"))
            check(item["files"])
            require(base.inventory(Path(item["vdb"])) == item["vdb_files"], "reused current VDB changed")
    return plan


def worker(output, name):
    # Verdict classification, audit, trace/image identity and VDB checks stay in
    # the established worker. Its zero exit includes ordinary functional FAILs.
    rc = batch.worker(output, name)
    path = output / "outcomes" / (name + ".json")
    if path.exists():
        item = read(path)
        case = next(c for c in read(output / "plan.json")["cases"] if c["name"] == name)
        item.update(schema_version=1, contract=case["contract"], replacement=bool(case.get("replacement")),
                    fault_vstart_probe=bool(case.get("fault_vstart_probe")))
        save(path, item)
    return rc


def summarize(output, plan):
    outcomes = [read(output / "outcomes" / (c["name"] + ".json")) for c in plan["cases"]]
    selected = []
    for case, item in zip(plan["cases"], outcomes):
        require(item["name"] == case["name"] and item["elf_sha256"] == case["elf_sha256"] and
                item["contract"] == case["contract"], "outcome/plan checking contract differs")
        require(item["coverage_test"] == case["coverage_test"], "outcome coverage label differs")
        if case["name"] in plan["reused"]:
            check({str(output / "outcomes" / (case["name"] + ".json")):
                   plan["files"][str(output / "outcomes" / (case["name"] + ".json"))]})
        else:
            artifact = output / "results" / case["name"] / "tests" / batch._safe_name(case["source_name"])
            work = artifact / "work" if case["kind"] == "directed" else artifact
            require(Path(item["vdb"]).resolve() == work / "code.vdb", "fresh VDB belongs to another case")
        check(item["files"])
        if item["status"] == "PASS":
            require(item["passed_only"] is True and item["vdb_valid"] is True,
                    "PASS lacks admitted VDB")
            require(batch.valid_vdb(Path(item["vdb"]), item["coverage_test"], plan["simv"]) == item["vdb_files"],
                    "PASS VDB differs from validated outcome")
            selected.append(item)
        else:
            require(item["passed_only"] is False, "failed replay marked for verified coverage")
    require(selected, "no PASS coverage to export")
    require(len({i["vdb"] for i in selected}) == len(selected), "duplicate selected VDB")
    design = Path(plan["design_vdb"])
    base.pure_design(design)
    databases = {str(design): plan["design_files"], **{i["vdb"]: i["vdb_files"] for i in selected}}
    require(all(base.inventory(Path(p)) == digest for p, digest in databases.items()), "VDB drift before DVE")
    save(output / "dve-inputs.before.json", databases)
    inputs = output / "dve-inputs.txt"
    inputs.write_text("\n".join(databases) + "\n")
    target = output / "dve"
    command = ["bash", str(DVE / "run_dve_coverage.sh"), str(target), "--inputs-file", str(inputs)]
    require(batch.invoke(command, output / "logs/dve.log", plan["dve_outer_timeout_s"],
                         {"DVE_COVERAGE_TIMEOUT": str(plan["dve_timeout_s"]), "DVE_WAIVERS": "auto"}) == 0,
            "strict PASS-only DVE export failed")
    expected = [str(Path(i["vdb"]).with_suffix("") / i["coverage_test"]) for i in selected]
    require((target / "selected_tests.txt").read_text().splitlines() == expected, "unexpected DVE test selection")
    require((target / "inputs.txt").read_text().splitlines() == list(databases), "unexpected DVE VDB inputs")
    require(read(target / "waiver_status.json")["status"] == "APPLIED", "reviewed waivers not applied")
    after = {p: base.inventory(Path(p)) for p in databases}
    save(output / "dve-inputs.after.json", after)
    require(after == databases, "DVE changed an input VDB")
    with (target / "summary.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    probe = [r for r in rows if "ara_fault_vstart_probe" in r["Name"]]
    require(probe, "full hierarchy report omitted the bound probe")
    reports = [target / name for name in ("summary.csv", "summary_waived.csv", "exclusions.el",
               "waiver_status.json", "selected_tests.txt", "inputs.txt", "points.el")]
    collection = {"status": "PASS" if len(selected) == len(outcomes) else "COMPLETE_WITH_FAILURES",
                  "coverage_verified": True, "total": len(outcomes), "passed": len(selected),
                  "reused_pass": len(plan["reused"]), "replayed": len(outcomes) - len(plan["reused"]),
                  "image": plan["image"], "cases": selected, "metrics_requested": base.METRICS,
                  "scope": "full hierarchy; raw includes TB/UVM/probe; reviewed waivers reported separately",
                  "probe_hierarchy_rows": probe, "probe_enabled_cases": [c["name"] for c in plan["cases"]
                     if c.get("fault_vstart_probe")], "aliases": plan["aliases"],
                  "failed_cases_excluded": [{"name": i["name"], "status": i["status"]}
                                            for i in outcomes if i["status"] != "PASS"],
                  "historical_vdb_reuse": False, "exploration_export": False, "reports": pins(reports),
                  "counts": dict(Counter(i["status"] for i in outcomes))}
    save(output / "collection.json", collection)
    return outcomes


def main():
    # Same dispatch pattern as extend_vcs_dve_batch; no existing file is changed.
    batch.SCRIPT, batch.frozen, batch.summarize = SCRIPT, frozen, summarize
    if len(sys.argv) > 2 and sys.argv[1] == "--coverage-exec":
        argv = batch.adapter_command(read(sys.argv[2]), sys.argv[3:], Path.cwd().resolve())
        with Path("coverage.command.json").open("x") as stream:
            json.dump({"command": argv, "cwd": str(Path.cwd())}, stream, indent=2)
        os.execv(argv[0], argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=8)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--worker", help=argparse.SUPPRESS)
    modes.add_argument("--directed", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = base.checked_output(args.output)
    require(output == OUTPUT, "only the registered recollection output is authorized")
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.worker:
        return worker(output, args.worker)
    if args.directed:
        return batch.directed(output, args.directed)
    if args.execute:
        require(os.environ.get("ARA_CHECKPOINT_UNIT") == SERVICE, "wrong recollection service")
        return batch.execute(output, args.jobs)
    prepare(output)
    print(f"PREPARED, NOT LAUNCHED: {output}; 445 total, 21 reused, 424 new, max 8 workers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
