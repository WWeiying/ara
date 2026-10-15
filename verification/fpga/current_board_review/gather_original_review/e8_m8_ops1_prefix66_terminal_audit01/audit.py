#!/usr/bin/env python3
"""Offline e8/m8 prefix66 case audit; one raw CSV recompute, no DUT/poll/writeback."""
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
SEALED = OWNER / "e8_m8_ops1_prefix66_vcs_m6_plan01"
OUT = SEALED / "prepared01"
PLAN_SHA = "3d487be3a65775b2fa99cceec10bf9a09d9e2564e09efed66e7485a7abfa8006"
IMAGE_SHA = "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0"


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    sys.path.insert(0, str(SEALED))
    spec = importlib.util.spec_from_file_location("e8_m8_frozen_replay", SEALED / "replay.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    require, read = worker.require, worker.read
    sha = lambda path: worker.sha(Path(path))
    root = OUT / "replay/tests" / worker.NAME
    # Real source failure markers take priority over expensive evidence processing.
    for log in (root / "console.log", root / "work/run.vcs.log"):
        text = log.read_text()
        failure = worker.checker.VETO.search(text)
        if failure:
            line = text.count("\n", 0, failure.start()) + 1
            save("FIRST_FAILURE.json", dict(status="NOT_ACCEPTED_RAW_FAILURE", source=str(log),
                line=line, raw_line=text.splitlines()[line - 1], no_DUT_rerun=True))
            raise ValueError("Original raw failure at %s:%d" % (log, line))
        worker.checker.console_gate(text)
    require(sha(OUT / "plan.json") == PLAN_SHA, "Exact sealed e8 plan")
    plan = read(OUT / "plan.json")
    image = Path(plan["image"])
    worker.validate(plan, image)
    require(len(plan["pins"]) == 785 and plan["image_sha256"] == IMAGE_SHA, "785/M6 scope identity")
    ledger, _, _ = worker.common.image_context(image)
    require(Path(ledger["snapshot"]).parent.name == "current_board_memory_candidate06" and
            ledger["snapshot_sha256"] == plan["snapshot_sha256"] and ledger["configuration_sha256"] ==
            "6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785", "M6 snapshot/config")
    from ara_verify.trace import validate_trace
    import audit_accepted8
    terminal = read(OUT / "complete.json")
    require(terminal["status"] == worker.PASS and terminal["aborted"] is False and
            terminal["pins_unchanged"] is True and terminal["plan_sha256"] == PLAN_SHA and
            terminal["retries"] == 0 and terminal["full_child_acceptance"] is False and
            terminal["exact_historical_stopped_tuple"] is None, "Incomplete/failed/foreign terminal")
    require(len(terminal["results"]) == 1 and read(OUT / "replay/summary.json") == terminal["results"],
            "Exact actual case result/summary")
    result_data = terminal["results"][0]
    require(result_data["artifact_dir"] == str(root) and result_data["returncode"] == 0 and
            0 <= result_data["elapsed_s"] <= 9000, "Case numeric rc/budget/private output")
    result = SimpleNamespace(**dict(result_data, artifact_dir=root))
    worker.terminal_gate([result], read(OUT / "replay/run.json"), threading.Event(), ledger)
    expected = {str(OUT / f) for f in ("launch.json", "replay/run.json", "replay/summary.json")}
    expected.update(str(root / f) for f in ("input.elf", "inputs.json", "command.json", "console.log",
        "work/run.vcs.log", "commit_trace.csv", "trace_summary.json", "strict_prefix.json"))
    require(len(expected) == 11 and set(terminal["evidence_pins"]) == expected, "Exact11 raw evidence pins")
    worker.common.base.verify_pins(terminal["evidence_pins"])
    before = dict(terminal["evidence_pins"])
    before[str(OUT / "complete.json")] = sha(OUT / "complete.json")
    launch = read(OUT / "launch.json")
    require(launch["plan_sha256"] == PLAN_SHA, "Launch plan drift")
    worker.common.base.verify_pins(launch["approval_pins"])
    case, routine = worker.scope()
    reference = worker.REF
    require(sha(reference / "READY.json") == worker.READY_SHA, "Accepted raw reference identity")
    ready = read(reference / "READY.json")
    require(ready["status"] == "READY_HOST_SPIKE_AUTHENTIC66_NOT_DUT" and
            (ready["calls"], ready["predecessors"], ready["capacity"], ready["fullcap_results"], ready["guards"]) ==
            (66, 65, 1024, 67584, 132), "Full original source reference scope")
    worker.common.base.verify_pins(ready["evidence_pins"])
    proof = read(reference / "source_elf_proof.json")
    original = reference / "prepared" / worker.NAME / "original"
    require(sha(original / "scenario.c") == proof["original_c_sha256"] and
            sha(original / "original_linux.elf") == proof["original_linux_elf_sha256"], "Authentic source/ELF identity")
    archived = audit_accepted8.archived_window(original / "original_linux.elf", routine["routine"])
    require(archived == proof["original_routine"], "Actual archive13 instruction window differs")
    spike_routine = worker.checker.source.instructions(Path(proof["spike_elf"]["path"]), worker.NAME + "_op_1")
    require(spike_routine == proof["spike_routine"] and
            [r["insn"] for r in archived] == [r["insn"] for r in spike_routine], "Actual reference13 differs")
    model = worker.checker.source.model()
    require(model["capacity"] == 1024 and len(model["rows"]) == 66, "No reduced-capacity or isolated-tuple model")
    started = time.monotonic()
    report = worker.checker.artifacts(result, case, ledger, routine, validate_trace)
    elapsed = time.monotonic() - started
    save("recomputed_strict_prefix.json", report)
    require(report == read(root / "strict_prefix.json"), "Raw recompute differs from original stored strict report")
    strict = report["strict"]
    require(strict["target_hits"] == strict["returned_vstart_zero"] == 66 and
            strict["routine_retire_counts"] == [66] * 13 and strict["fullcap_checks"] == 67584 and
            strict["guards"] == 132 and strict["actual_output_scalar_loads"] == 67716 and strict["soc_ctrl_exit"] == 0,
            "Incomplete original calls/asm/full1024 oracle/exit")
    require([c["ordinal"] for c in strict["calls"]] == list(range(1, 67)) and
            [c["original_tuple"] for c in strict["calls"]] == [r["tuple"] for r in model["rows"]] and
            all(c["setup_values_checked"] == 4226 for c in strict["calls"]), "Missing/changed natural65 predecessors")
    require(strict["calls"][-1]["original_tuple"] == [0, 1, 0, 4, 0, 1] and
            strict["calls"][-1]["target"]["vl"] == 512 and strict["calls"][-1]["target"]["vstart"] == 256,
            "Exact original endpoint")
    require(all(sha(path) == digest for path, digest in before.items()), "Original terminal/raw evidence changed")
    worker.common.base.verify_pins(plan["pins"])
    pins = dict(plan["pins"])
    pins.update(before)
    pins.update(launch["approval_pins"])
    pins[str(OUT / "plan.json")] = PLAN_SHA
    pins[str(HERE / "audit.py")] = sha(HERE / "audit.py")
    pins[str(HERE / "recomputed_strict_prefix.json")] = sha(HERE / "recomputed_strict_prefix.json")
    audit = dict(status="E8M8VX66_DUT_CASE_INDEPENDENTLY_ACCEPTED_NOT_FULL2688", name=worker.NAME,
        plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, snapshot_sha256=ledger["snapshot_sha256"],
        configuration_sha256=ledger["configuration_sha256"], plan_pins_verified=785, raw_evidence_pins_verified=11,
        actual_numeric_simulator_returncode=result.returncode, elapsed_s=result.elapsed_s, terminal_aborted=False,
        runner_status="COMPLETE", runner_status_counts={"PASS": 1}, raw_csv_strict_recomputed_once=True,
        raw_recompute_equals_stored=True, recompute_seconds=elapsed, capacity=1024,
        calls=66, predecessors=65, all_predecessor_tuples_match_original_model=True,
        helper_instruction_retire_counts=[66] * 13, setup_values_per_call=4226,
        fullcap_results=67584, guards=132, actual_oracle_scalar_loads=67716,
        returned_vstart_zero=66, endpoint=strict["calls"][-1],
        csv_rows=strict["csv_rows"], retired=strict["retired_rows"], last_cycle=strict["csv_last_cycle"],
        post_exit_park_retired=strict["post_exit_park_retired"],
        soc_elf_sha256=case["sha256"], original_linux_elf_sha256=proof["original_linux_elf_sha256"],
        original_c_sha256=proof["original_c_sha256"], archived_target_pc=hex(archived[8]["pc"]),
        original_artifacts_unchanged=True, outer_worker_exit0_verified=False,
        outer_service_actual_exit="UNAVAILABLE_AFTER_PARENT_REPORTED_GC", GC_used_as_exit0_evidence=False,
        exact_historical_stopped_tuple=None, full2688_child_accepted=False, original_linux_replay_accepted=False,
        entire_original_linux_binary_rebuild_proven=False, active_ei16_queried=False,
        process_or_service_queries=False, no_DUT_or_Host_rerun=True, no_original_or_sealed_writes=True, pins=pins)
    save("audit.json", audit)
    print(json.dumps({key: value for key, value in audit.items() if key != "pins"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        save("AUDIT_NOT_ACCEPTED.json", dict(status="NOT_ACCEPTED", error=repr(error), no_DUT_rerun=True))
        raise
