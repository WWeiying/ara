#!/usr/bin/env python3
"""Independent offline DUT-case acceptance, never service-exit inference from GC."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OWNER = HERE.parent
SEALED = OWNER / "e16_m8_ops1_prefix98_vcs_m6_plan02"
OUT = SEALED / "prepared01"
PLAN_SHA = "e4476bec15fadab91251915d44bc156e24c9191abd0aea0359a32d372336f5c2"
IMAGE_SHA = "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0"
CONFIG_SHA = "6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785"


def save(name, data):
    with (HERE / name).open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def main():
    sys.path.insert(0, str(SEALED))
    spec = importlib.util.spec_from_file_location("e16_m8_terminal_sealed", SEALED / "replay.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    require, read = worker.require, worker.read
    sha = lambda path: worker.sha(Path(path))
    require(sha(OUT / "plan.json") == PLAN_SHA, "Exact sealed plan02")
    plan = read(OUT / "plan.json")
    image = Path(plan["image"])
    worker.validate(plan, image)
    require(plan["image_sha256"] == IMAGE_SHA and len(plan["pins"]) == 708, "M6 plan identity/count")
    ledger, repo, _ = worker.common.image_context(image)
    require(Path(ledger["snapshot"]).parent.name == "current_board_memory_candidate06" and
            ledger["snapshot_sha256"] == plan["snapshot_sha256"] and
            ledger["configuration_sha256"] == CONFIG_SHA, "Frozen M6 snapshot/config")
    import audit_accepted8
    from ara_verify.trace import validate_trace
    case, routine = worker.scope()
    root = OUT / "replay/tests" / worker.NAME
    terminal = read(OUT / "complete.json")
    require(terminal["status"] == worker.PASS and terminal["aborted"] is False and
            terminal["pins_unchanged"] is True and terminal["plan_sha256"] == PLAN_SHA and
            terminal["retries"] == 0 and terminal["full_child_acceptance"] is False and
            terminal["exact_historical_stopped_tuple"] is None, "False/incomplete terminal")
    require(len(terminal["results"]) == 1 and read(OUT / "replay/summary.json") == terminal["results"],
            "Terminal/summary exact membership")
    result_data = terminal["results"][0]
    require(result_data["artifact_dir"] == str(root), "Foreign artifact root")
    result = SimpleNamespace(**dict(result_data, artifact_dir=root))
    worker.terminal_gate([result], read(OUT / "replay/run.json"), threading.Event(), ledger)
    require(result.returncode == 0 and 0 <= result.elapsed_s <= 9000, "Actual simulator exit/budget")
    expected_evidence = {str(OUT / path) for path in ("launch.json", "replay/run.json", "replay/summary.json")}
    expected_evidence.update(str(root / name) for name in ("input.elf", "inputs.json", "command.json",
        "console.log", "work/run.vcs.log", "commit_trace.csv", "trace_summary.json", "strict_prefix.json"))
    require(set(terminal["evidence_pins"]) == expected_evidence, "Exact eleven evidence pins required")
    worker.common.base.verify_pins(terminal["evidence_pins"])
    before = dict(terminal["evidence_pins"])
    before[str(OUT / "complete.json")] = sha(OUT / "complete.json")
    reference = worker.REF
    proof = read(reference / "source_elf_proof.json")
    original = reference / "prepared" / worker.NAME / "original"
    require(sha(original / "scenario.c") == proof["original_c_sha256"] and
            sha(original / "original_linux.elf") == proof["original_linux_elf_sha256"], "Authentic original source/ELF")
    archived = audit_accepted8.archived_window(original / "original_linux.elf", routine["routine"])
    require(archived == proof["original_routine"] and archived[8]["pc"] == 0x105EE,
            "Actual archived13 disassembly differs")
    require(worker.checker.source.instructions(Path(proof["spike_elf"]["path"]), worker.NAME + "_op_1") ==
            proof["spike_routine"] and [r["insn"] for r in archived] ==
            [r["insn"] for r in proof["spike_routine"]], "Reference13 encoding drift")
    reference_gate = read(SEALED / "reference_audit02.json")
    require(reference_gate["status"] == "PASS_REFERENCE_RAW98_NOT_DUT" and
            reference_gate["calls"] == 98 and reference_gate["fullcap"] == 50176 and
            reference_gate["guards"] == 196 and reference_gate["asm_counts"] == [98] * 13 and
            reference_gate["returned_vstart_zero"] == 98, "Full raw reference scope")
    worker.common.base.verify_pins(reference_gate["reference_pins"])
    model = worker.checker.source.model()
    finalize_existing = sys.argv[1:] == ["--finalize-existing"]
    require(not sys.argv[1:] or finalize_existing, "Only explicit retained-result finalization supported")
    if finalize_existing:
        retained = HERE / "recomputed_strict_prefix.json"
        require(sha(retained) == "9e276ae7bda91801fd2f201bb3739e35f78f02da54491bcf4be2f7d6d3b59066",
                "Retained independent recompute changed")
        report, elapsed = read(retained), None
        require(report["csv_sha256"] == sha(root / "commit_trace.csv"), "Retained recompute CSV identity")
    else:
        started = time.monotonic()
        report = worker.checker.artifacts(result, case, ledger, routine, validate_trace)
        elapsed = time.monotonic() - started
        save("recomputed_strict_prefix.json", report)
    require(report == read(root / "strict_prefix.json"), "Actual CSV recompute differs from stored strict analysis")
    strict = report["strict"]
    require(strict["target_hits"] == strict["returned_vstart_zero"] == 98 and
            strict["routine_retire_counts"] == [98] * 13 and strict["fullcap_checks"] == 50176 and
            strict["guards"] == 196 and strict["actual_output_scalar_loads"] == 50372 and
            strict["soc_ctrl_exit"] == 0, "Full98/cap/guards/exit")
    require([c["original_tuple"] for c in strict["calls"]] == [r["tuple"] for r in model["rows"]] and
            model["rows"][-1]["tuple"] == [0, 1, 0, 6, 0, 1], "Natural first98 exact identity")
    require(all(sha(path) == value for path, value in before.items()), "Terminal/evidence changed during audit")
    worker.common.base.verify_pins(plan["pins"])
    combined = dict(plan["pins"])
    combined.update(before)
    combined[str(OUT / "plan.json")] = PLAN_SHA
    combined[str(HERE / "audit.py")] = sha(HERE / "audit.py")
    combined[str(HERE / "recomputed_strict_prefix.json")] = sha(HERE / "recomputed_strict_prefix.json")
    combined[str(repo / "verification/ara_verify/trace.py")] = sha(repo / "verification/ara_verify/trace.py")
    audit = dict(status="DUT_CASE_PREFIX98_INDEPENDENTLY_ACCEPTED_NOT_FULL2688", name=worker.NAME,
        plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, configuration_sha256=CONFIG_SHA,
        snapshot_sha256=ledger["snapshot_sha256"], plan_pins_verified=708, terminal_evidence_pins_verified=11,
        simulator_returncode=result.returncode, elapsed_s=result.elapsed_s, terminal_aborted=False,
        raw_csv_equals_stored_strict=True, original_artifacts_unchanged=True, recompute_seconds=elapsed,
        finalized_from_retained_independent_recompute=finalize_existing,
        soc_elf_sha256=case["sha256"], original_linux_elf_sha256=proof["original_linux_elf_sha256"],
        original_c_sha256=proof["original_c_sha256"], source_child="rvv_permute_restart_e16_m8_ops1",
        archived_target_pc="0x105ee", dut_target_pc=hex(routine["routine"][8]["pc"]), target_encoding="308e4c57",
        calls=98, helper_instruction_retire_counts=strict["routine_retire_counts"], setup_values_per_call=2178,
        fullcap_output_checks=50176, guards=196, returned_vstart_zero=98,
        endpoint_tuple=[0, 1, 0, 6, 0, 1], endpoint_vl=512, endpoint_vstart=256,
        csv_rows=strict["csv_rows"], retired=strict["retired_rows"], last_cycle=strict["csv_last_cycle"],
        post_exit_park_retired=strict["post_exit_park_retired"],
        case_rc0_provenance="Actual frozen runner COMPLETE/PASS1 summary and terminal rc0, raw CTRL0/fulloracle and strict recompute",
        worker_exit0_verified=False, actual_service_exit_status="UNAVAILABLE_AFTER_GC",
        service_not_found_used_as_positive_evidence=False, processes_or_services_queried=False,
        historical_stopped_tuple=None, full2688_child_accepted=False, original_linux_execution_accepted=False,
        entire_original_linux_binary_rebuild_proven=False, indexed_fault_queried=False,
        no_DUT_started=True, no_original_or_sealed_writes=True, pins=combined)
    save("audit.json", audit)
    print(json.dumps({key: value for key, value in audit.items() if key != "pins"}))


if __name__ == "__main__":
    main()
