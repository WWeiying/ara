#!/usr/bin/env python3
"""Read-only VI31 terminal audit; exactly one strict CSV reconstruction."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SEALED = HERE.parent / "e16_m8_ops3_prefix98_vcs_m6_plan01"
OUT = SEALED / "prepared01"
PLAN_SHA = "d35fd8ce0a1a74854ad6d230c2c9f467f7c633fa5d9f4f3d1ca52619fb23d0a5"
IMAGE_SHA = "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0"
CFG_SHA = "6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785"
SNAP_SHA = "3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438"


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def observe(rows, spec, model, evidence):
    # Observe actual rows without altering the frozen checker's inputs or oracle.
    regs, ordinal = {0: 0}, 0
    addresses, routine = spec["addresses"], spec["routine"]
    for line, row in enumerate(rows, 2):
        if row["event"] == "retire":
            pc, insn = int(row["pc"], 16), int(row["insn"], 16)
            rd, value = int(row["rd"]), int(row["rd_wdata"], 16)
            if pc == routine[0]["pc"]:
                ordinal += 1
                if regs.get(11) != addresses["indices"] or regs.get(11) == addresses["indices16"] or regs.get(16) != 0:
                    raise ValueError("Actual ordinary indices/a6 mismatch")
                evidence["entries"].append(dict(call=ordinal, cycle=int(row["cycle"]), csv_line=line,
                    a1=hex(regs[11]), a6=regs[16]))
            if pc == routine[8]["pc"]:
                if regs.get(28) != 0 or regs.get(16) != 0 or insn != 0x308fbc57 or (insn >> 15) & 31 != 31:
                    raise ValueError("Actual vi31/t3/a6 mismatch")
                evidence["targets"].append(dict(call=ordinal, cycle=int(row["cycle"]), csv_line=line,
                    t3=regs[28], a6=regs[16], immediate_unsigned=31, pc=hex(pc), insn=hex(insn)))
            address = int(row["mem_addr"], 16)
            if ordinal and int(row["mem_rmask"], 16) and addresses["output"] <= address < addresses["output"] + 1028:
                element = (address - addresses["output"]) // 2 - 1
                if 0 <= element < 512:
                    gold = model["rows"][ordinal - 1]
                    picked = (gold["predicate"][element // 8] >> (element % 8)) & 1
                    active = gold["vstart"] <= element < gold["vl"] and picked
                    category = "active" if active else "prestart" if element < gold["vstart"] else "tail" if element >= gold["vl"] else "inactive"
                    counts = evidence["all_categories"]
                    counts[category] = counts.get(category, 0) + 1
                    if ordinal == 98:
                        counts = evidence["call98_categories"]
                        counts[category] = counts.get(category, 0) + 1
                    if active and value != 32689:
                        raise ValueError("Actual vi31 active result differs from source31")
                    if (ordinal, element) in ((18, 0), (18, 1), (98, 255), (98, 256), (98, 511)):
                        evidence["selected_loads"]["call%d_element%d" % (ordinal, element)] = dict(call=ordinal,
                            element=element, vl=gold["vl"], vstart=gold["vstart"], actual=value,
                            original_scalar_expected=gold["output"][element], source_index=31,
                            cycle=int(row["cycle"]), csv_line=line, actual_lhu_pc=hex(pc), category=category)
            if rd and not int(row["trap"]):
                regs[rd] = value
        yield row


def main():
    sys.path.insert(0, str(SEALED))
    loader = importlib.util.spec_from_file_location("vi31_frozen_replay", SEALED / "replay.py")
    worker = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(worker)
    require, read = worker.require, worker.read
    sha = lambda path: worker.sha(Path(path))
    root = OUT / "replay/tests" / worker.NAME
    for path in (root / "console.log", root / "work/run.vcs.log"):
        text = path.read_text()
        bad = worker.checker.VETO.search(text)
        if bad:
            line = text.count("\n", 0, bad.start()) + 1
            save("FIRST_FAILURE.json", dict(status="NOT_ACCEPTED_RAW_FAILURE", path=str(path), line=line,
                raw_line=text.splitlines()[line - 1]))
            raise ValueError("Raw first failure: stop workflow")
        worker.checker.console_gate(text)
    require(sha(OUT / "plan.json") == PLAN_SHA, "Original disk plan SHA differs")
    plan = read(OUT / "plan.json")
    image = Path(plan["image"])
    worker.validate(plan, image)
    require(len(plan["pins"]) == 855 and plan["image_sha256"] == IMAGE_SHA, "855/M6 identity")
    ledger, _, _ = worker.common.image_context(image)
    require(Path(ledger["snapshot"]).parent.name == "current_board_memory_candidate06" and
            ledger["snapshot_sha256"] == SNAP_SHA and plan["snapshot_sha256"] == SNAP_SHA and
            ledger["configuration_sha256"] == CFG_SHA, "M6 snapshot/config drift")
    from ara_verify.trace import validate_trace
    import audit_accepted8
    terminal = read(OUT / "complete.json")
    require(terminal["status"] == worker.PASS and terminal["aborted"] is False and terminal["pins_unchanged"] is True and
            terminal["plan_sha256"] == PLAN_SHA and terminal["retries"] == 0 and terminal["full_child_acceptance"] is False and
            terminal["exact_historical_stopped_tuple"] is None, "Actual terminal contract")
    require(len(terminal["results"]) == 1 and terminal["results"] == read(OUT / "replay/summary.json"), "Actual PASS1 summary")
    data = terminal["results"][0]
    require(type(data["returncode"]) is int and data["returncode"] == 0 and 0 <= data["elapsed_s"] <= 9000 and
            data["artifact_dir"] == str(root), "Actual numeric rc/budget/path")
    result = SimpleNamespace(**dict(data, artifact_dir=root))
    worker.terminal_gate([result], read(OUT / "replay/run.json"), threading.Event(), ledger)
    expected = {str(OUT / p) for p in ("launch.json", "replay/run.json", "replay/summary.json")}
    expected.update(str(root / p) for p in ("input.elf", "inputs.json", "command.json", "console.log", "work/run.vcs.log",
        "commit_trace.csv", "trace_summary.json", "strict_prefix.json"))
    require(len(expected) == 11 and set(terminal["evidence_pins"]) == expected, "Raw evidence exact membership")
    worker.common.base.verify_pins(terminal["evidence_pins"])
    before = dict(terminal["evidence_pins"])
    before.update({str(OUT / "complete.json"): sha(OUT / "complete.json"), str(OUT / "plan.json"): PLAN_SHA})
    launch = read(OUT / "launch.json")
    require(launch["plan_sha256"] == PLAN_SHA, "Launch plan identity")
    worker.common.base.verify_pins(launch["approval_pins"])
    case, routine = worker.scope()
    ref = worker.REF
    require(sha(ref / "READY.json") == worker.READY_SHA, "Reference identity")
    ready = read(ref / "READY.json")
    scope = ready["scope"]
    require((scope["calls"], scope["predecessors"], scope["capacity"], scope["fullcap_results"], scope["guards"],
            scope["unsigned_immediate"], ready["actual_source31"]) == (98, 97, 512, 50176, 196, 31, 32689), "Original reference scope")
    worker.common.base.verify_pins(ready["evidence_pins"])
    proof = read(ref / "source_elf_proof.json")
    original = ref / "prepared" / worker.NAME / "original"
    require(sha(original / "scenario.c") == proof["original_c_sha256"] and
            sha(original / "original_linux.elf") == proof["original_linux_elf_sha256"], "Authentic archived source/ELF")
    archived = audit_accepted8.archived_window(original / "original_linux.elf", routine["routine"])
    require(archived == proof["original_routine"], "Actual archive13 identity")
    spike = worker.checker.source.instructions(Path(proof["spike_elf"]["path"]), worker.NAME + "_op_3")
    require(spike == proof["spike_routine"] and [r["insn"] for r in spike] == [r["insn"] for r in archived], "Spike13 identity")
    worker.checker.common.check_artifacts(result, case, ledger)
    require(result.status == "PASS" and result.name == worker.NAME and not result.reason, "Actual result")
    model = worker.checker.source.model()
    require(model["input"][31] == 32689 and model["input"][0] == 61881, "Original xorshift discriminators")
    supplemental = dict(entries=[], targets=[], selected_loads={}, all_categories={}, call98_categories={})
    start = time.monotonic()
    generic = validate_trace(root / "commit_trace.csv")
    require(generic["cvx_exception_count"] == 0, "Accelerator exception")
    with (root / "commit_trace.csv").open(newline="") as stream:
        strict = worker.checker.retirement(observe(csv.DictReader(stream), routine, model, supplemental), routine, model)
    elapsed = time.monotonic() - start
    require((strict["csv_rows"], strict["csv_last_cycle"], strict["retired_rows"]) ==
            (generic["rows"], generic["last_cycle"], generic["retire_count"]), "Generic/strict counts")
    report = dict(generic=generic, strict=strict, csv_sha256=sha(root / "commit_trace.csv"))
    save("recomputed_strict_prefix.json", report)
    require(report == read(root / "strict_prefix.json") and
            (HERE / "recomputed_strict_prefix.json").read_bytes() == (root / "strict_prefix.json").read_bytes(), "Stored/raw structure or bytes differ")
    require(strict["target_hits"] == strict["returned_vstart_zero"] == 98 and strict["routine_retire_counts"] == [98]*13 and
            strict["fullcap_checks"] == 50176 and strict["guards"] == 196 and strict["actual_output_scalar_loads"] == 50372 and
            strict["soc_ctrl_exit"] == 0, "Full98/oracle/CSR/exit")
    require([c["ordinal"] for c in strict["calls"]] == list(range(1, 99)) and
            [c["original_tuple"] for c in strict["calls"]] == [r["tuple"] for r in model["rows"]] and
            all(c["immediate_unsigned"] == 31 and c["expected_active_value"] == 32689 for c in strict["calls"]), "Natural97 predecessors/vi31")
    require(len(supplemental["entries"]) == len(supplemental["targets"]) == 98 and sum(supplemental["all_categories"].values()) == 50176,
            "Actual args/targets/full categories")
    selected = supplemental["selected_loads"]
    require(selected["call18_element0"]["vl"] == 1 and selected["call18_element0"]["vstart"] == 0 and
            selected["call18_element0"]["actual"] == 32689 and selected["call18_element1"]["actual"] == 91, "VL1 source31 valid/tail")
    require(selected["call98_element255"]["actual"] == 91 and selected["call98_element256"]["actual"] ==
            selected["call98_element511"]["actual"] == 32689 and supplemental["call98_categories"] == dict(prestart=256, active=256), "Endpoint preservation/oracle")
    save("vi31_actual_evidence.json", supplemental)
    require(sha(OUT / "plan.json") == PLAN_SHA and all(sha(p) == d for p, d in before.items()), "Disk original plan/evidence drift")
    worker.common.base.verify_pins(plan["pins"])
    pins = dict(plan["pins"])
    pins.update(before)
    pins.update(launch["approval_pins"])
    for p in (HERE / "audit.py", HERE / "recomputed_strict_prefix.json", HERE / "vi31_actual_evidence.json"):
        pins[str(p)] = sha(p)
    audit = dict(status="VI31_PREFIX98_DUT_CASE_INDEPENDENTLY_ACCEPTED_NOT_FULL2688", name=worker.NAME,
        original_plan_disk_reverified=True, disk_plan_sha256_before_and_after=PLAN_SHA, plan_pins_verified=855,
        raw_evidence_pins_verified=11, image_sha256=IMAGE_SHA, configuration_sha256=CFG_SHA, snapshot_sha256=SNAP_SHA,
        actual_numeric_case_rc=0, elapsed_s=data["elapsed_s"], case_budget_s=9000, service_budget_s=10200,
        runner_status="COMPLETE", runner_status_counts={"PASS": 1}, aborted=False,
        raw_strict_csv_recomputed_once=True, raw_equals_stored_structure_and_bytes=True, recompute_seconds=elapsed,
        calls=98, predecessors=97, capacity=512, helper_instruction_retire_counts=[98]*13,
        fullcap_results=50176, guards=196, actual_output_scalar_loads=50372, returned_vstart_zero=98,
        ordinary_indices_address=hex(routine["addresses"]["indices"]), distinct_indices16_address=hex(routine["addresses"]["indices16"]),
        actual_args_targets_checked=98, a6_t3_zero=True, immediate_unsigned=31, actual_active_source31=32689, wrong_vx_source0=61881,
        vl1_actual=selected["call18_element0"], endpoint=strict["calls"][-1], all_result_categories=supplemental["all_categories"],
        csv_rows=strict["csv_rows"], retired=strict["retired_rows"], last_cycle=strict["csv_last_cycle"],
        soc_elf_sha256=case["sha256"], original_linux_elf_sha256=proof["original_linux_elf_sha256"],
        original_c_sha256=proof["original_c_sha256"], original_artifacts_unchanged=True,
        outer_service_actual_exit="UNKNOWN_GC_NOT_POSITIVE_EXIT0", outer_worker_exit0_verified=False, GC_used_as_exit0_evidence=False,
        full2688_accepted=False, original_linux_replay_accepted=False, historical_stopped_tuple=None,
        live_e8_queried=False, process_or_service_queries=False, no_DUT_or_Host_rerun=True, no_original_or_sealed_writes=True, pins=pins)
    save("audit.json", audit)
    print(json.dumps({k:v for k,v in audit.items() if k != "pins"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        save("AUDIT_NOT_ACCEPTED.json", dict(status="NOT_ACCEPTED", error=repr(error), no_DUT_rerun=True))
        raise
