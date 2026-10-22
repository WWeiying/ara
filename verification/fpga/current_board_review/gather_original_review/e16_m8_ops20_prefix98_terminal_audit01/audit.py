#!/usr/bin/env python3
"""Offline EI16 acceptance with one strict CSV pass and lossless row observation."""
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
OWNER = HERE.parent
SEALED = OWNER / "e16_m8_ops20_prefix98_vcs_m6_plan01"
OUT = SEALED / "prepared01"
PLAN_SHA = "711e1f5ff862e9da4697ad3b6b2dfd278e78ec079f011b14665f4bfebb84d510"
IMAGE_SHA = "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0"


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def observe(rows, spec, model, evidence):
    # Forward every original row unchanged to the frozen checker; no oracle substitution.
    registers, ordinal = {0: 0}, 0
    addresses, entry = spec["addresses"], spec["routine"][0]["pc"]
    for line, row in enumerate(rows, 2):
        if row["event"] == "retire":
            pc, insn = int(row["pc"], 16), int(row["insn"], 16)
            value, rd = int(row["rd_wdata"], 16), int(row["rd"])
            if pc == entry:
                ordinal += 1
                a1 = registers.get(11)
                if a1 != addresses["indices16"] or a1 == addresses["indices"]:
                    raise ValueError("Actual a1 is not distinct indices16 at call%d" % ordinal)
                evidence["actual_a1_entries"].append(dict(call=ordinal, cycle=int(row["cycle"]),
                    csv_line=line, a1=hex(a1), expected_indices16=hex(addresses["indices16"])))
            address = int(row["mem_addr"], 16)
            if ordinal and int(row["mem_rmask"], 16) and addresses["output"] <= address < addresses["output"] + 1028:
                element = (address - addresses["output"]) // 2 - 1
                if 0 <= element < 512:
                    gold = model["rows"][ordinal - 1]
                    index = model["indices16"][element]
                    picked = bool((gold["predicate"][element // 8] >> (element % 8)) & 1)
                    active = gold["vstart"] <= element < gold["vl"] and picked
                    detail = dict(call=ordinal, element=element, index=index, actual=value,
                        original_scalar_expected=gold["output"][element], cycle=int(row["cycle"]), csv_line=line,
                        actual_lhu_pc=hex(pc), vl=gold["vl"], vstart=gold["vstart"])
                    if (ordinal, element) in ((49, 2), (66, 255), (66, 511), (98, 511)):
                        evidence["selected_actual_loads"]["call%d_element%d" % (ordinal, element)] = detail
                    if ordinal == 98 and active and index >= 512:
                        if value != 0:
                            raise ValueError("Active EI16 OOR was not zero")
                        evidence["call98_active_oor_zero_loads"].append(detail)
                    if ordinal == 74 and not active and gold["vstart"] <= element < gold["vl"] and index >= 512:
                        if "call74_inactive_oor" not in evidence:
                            evidence["call74_inactive_oor"] = detail
                    category = "active" if active else "retained"
                    if active:
                        category = "active_oor" if index >= 512 else "active_inrange"
                    elif element < gold["vstart"]:
                        category = "prestart"
                    elif element >= gold["vl"]:
                        category = "tail"
                    else:
                        category = "inactive"
                    counts = evidence["call98_categories"] if ordinal == 98 else None
                    if counts is not None:
                        counts[category] = counts.get(category, 0) + 1
            if rd and not int(row["trap"]):
                registers[rd] = value
        yield row


def main():
    sys.path.insert(0, str(SEALED))
    spec = importlib.util.spec_from_file_location("ei16_frozen_replay", SEALED / "replay.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    require, read = worker.require, worker.read
    sha = lambda path: worker.sha(Path(path))
    root = OUT / "replay/tests" / worker.NAME
    for log in (root / "console.log", root / "work/run.vcs.log"):
        text = log.read_text()
        bad = worker.checker.VETO.search(text)
        if bad:
            line = text.count("\n", 0, bad.start()) + 1
            save("FIRST_FAILURE.json", dict(status="NOT_ACCEPTED_RAW_FAILURE", source=str(log),
                line=line, raw_line=text.splitlines()[line - 1]))
            raise ValueError("Real raw failure; stop workflow")
        worker.checker.console_gate(text)
    # Disk bytes, both before and after analysis: the sealed worker's memory-plan gate is insufficient here.
    require(sha(OUT / "plan.json") == PLAN_SHA, "Original disk plan SHA differs")
    plan = read(OUT / "plan.json")
    image = Path(plan["image"])
    worker.validate(plan, image)
    require(len(plan["pins"]) == 786 and plan["image_sha256"] == IMAGE_SHA, "786/M6 identity")
    ledger, _, _ = worker.common.image_context(image)
    require(Path(ledger["snapshot"]).parent.name == "current_board_memory_candidate06" and
            ledger["snapshot_sha256"] == plan["snapshot_sha256"] and ledger["configuration_sha256"] ==
            "6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785", "Frozen M6 config/snapshot")
    from ara_verify.trace import validate_trace
    import audit_accepted8
    terminal = read(OUT / "complete.json")
    require(terminal["status"] == worker.PASS and terminal["aborted"] is False and terminal["pins_unchanged"] is True and
            terminal["plan_sha256"] == PLAN_SHA and terminal["retries"] == 0 and
            terminal["full_child_acceptance"] is False and terminal["exact_historical_stopped_tuple"] is None,
            "Not exact accepted terminal")
    require(len(terminal["results"]) == 1 and read(OUT / "replay/summary.json") == terminal["results"], "Actual case summary mismatch")
    data = terminal["results"][0]
    require(data["artifact_dir"] == str(root) and data["returncode"] == 0 and 0 <= data["elapsed_s"] <= 9000,
            "Actual numeric case rc/budget/artifact")
    result = SimpleNamespace(**dict(data, artifact_dir=root))
    worker.terminal_gate([result], read(OUT / "replay/run.json"), threading.Event(), ledger)
    expected = {str(OUT / f) for f in ("launch.json", "replay/run.json", "replay/summary.json")}
    expected.update(str(root / f) for f in ("input.elf", "inputs.json", "command.json", "console.log", "work/run.vcs.log",
        "commit_trace.csv", "trace_summary.json", "strict_prefix.json"))
    require(len(expected) == 11 and set(terminal["evidence_pins"]) == expected, "Exact raw evidence membership")
    worker.common.base.verify_pins(terminal["evidence_pins"])
    before = dict(terminal["evidence_pins"])
    before[str(OUT / "complete.json")] = sha(OUT / "complete.json")
    before[str(OUT / "plan.json")] = PLAN_SHA
    launch = read(OUT / "launch.json")
    require(launch["plan_sha256"] == PLAN_SHA, "Launch plan mismatch")
    worker.common.base.verify_pins(launch["approval_pins"])
    case, routine = worker.scope()
    reference = worker.REF
    require(sha(reference / "READY.json") == worker.READY_SHA, "Reference READY identity")
    ready = read(reference / "READY.json")
    require((ready["calls"], ready["predecessors"], ready["capacity"], ready["fullcap_results"], ready["guards"]) ==
            (98, 97, 512, 50176, 196), "Original source/reference scope")
    worker.common.base.verify_pins(ready["evidence_pins"])
    proof = read(reference / "source_elf_proof.json")
    original = reference / "prepared" / worker.NAME / "original"
    require(sha(original / "scenario.c") == proof["original_c_sha256"] and
            sha(original / "original_linux.elf") == proof["original_linux_elf_sha256"], "Authentic source/ELF")
    archived = audit_accepted8.archived_window(original / "original_linux.elf", routine["routine"])
    require(archived == proof["original_routine"], "Actual archive13 disassembly differs")
    spike = worker.checker.source.instructions(Path(proof["spike_elf"]["path"]), worker.NAME + "_op_20")
    require(spike == proof["spike_routine"] and [r["insn"] for r in spike] == [r["insn"] for r in archived], "Actual Spike13 identity")
    worker.checker.common.check_artifacts(result, case, ledger)
    require(result.status == "PASS" and result.name == worker.NAME and not result.reason, "Wrong actual result")
    model = worker.checker.source.model()
    supplemental = dict(actual_a1_entries=[], selected_actual_loads={}, call98_active_oor_zero_loads=[], call98_categories={})
    start = time.monotonic()
    generic = validate_trace(root / "commit_trace.csv")
    require(generic["cvx_exception_count"] == 0, "Actual accelerator exception")
    with (root / "commit_trace.csv").open(newline="") as stream:
        strict = worker.checker.retirement(observe(csv.DictReader(stream), routine, model, supplemental), routine, model)
    elapsed = time.monotonic() - start
    require((strict["csv_rows"], strict["csv_last_cycle"], strict["retired_rows"]) ==
            (generic["rows"], generic["last_cycle"], generic["retire_count"]), "Generic/raw strict counts differ")
    report = dict(generic=generic, strict=strict, csv_sha256=sha(root / "commit_trace.csv"))
    save("recomputed_strict_prefix.json", report)
    require(report == read(root / "strict_prefix.json"), "Stored versus actual CSV analysis differs")
    require(strict["target_hits"] == strict["returned_vstart_zero"] == 98 and strict["routine_retire_counts"] == [98] * 13 and
            strict["fullcap_checks"] == 50176 and strict["guards"] == 196 and strict["actual_output_scalar_loads"] == 50372 and
            strict["soc_ctrl_exit"] == 0, "Full98/cap/oracle/vstart/exit")
    require([c["ordinal"] for c in strict["calls"]] == list(range(1, 99)) and
            [c["original_tuple"] for c in strict["calls"]] == [r["tuple"] for r in model["rows"]] and
            len(supplemental["actual_a1_entries"]) == 98, "Missing97 natural predecessors or actual a1")
    selected = supplemental["selected_actual_loads"]
    for key, index, value in (("call49_element2", 511, 44879), ("call66_element255", 512, 0),
                              ("call98_element511", 1, 538)):
        require(selected[key]["index"] == index and selected[key]["actual"] == selected[key]["original_scalar_expected"] == value,
                "Dynamic original EI16 discriminator: " + key)
    require(selected["call66_element511"]["actual"] == 91 and supplemental["call74_inactive_oor"]["actual"] == 91,
            "Inactive/OOR or tail must retain original sentinel")
    require(len(supplemental["call98_active_oor_zero_loads"]) == 85 and
            supplemental["call98_categories"] == dict(prestart=256, active_oor=85, active_inrange=171),
            "Call98 full retained/dynamic/OOR partition")
    save("dynamic_oor_actual_evidence.json", supplemental)
    require(sha(OUT / "plan.json") == PLAN_SHA, "Original disk plan changed after raw analysis")
    require(all(sha(path) == digest for path, digest in before.items()), "Original terminal/evidence drift")
    worker.common.base.verify_pins(plan["pins"])
    pins = dict(plan["pins"])
    pins.update(before)
    pins.update(launch["approval_pins"])
    for path in (HERE / "audit.py", HERE / "recomputed_strict_prefix.json", HERE / "dynamic_oor_actual_evidence.json"):
        pins[str(path)] = sha(path)
    audit = dict(status="EI16_PREFIX98_DUT_CASE_INDEPENDENTLY_ACCEPTED_NOT_FULL2688", name=worker.NAME,
        disk_plan_sha256_before_and_after=PLAN_SHA, original_plan_disk_reverified=True, plan_pins_verified=786,
        raw_evidence_pins_verified=11, image_sha256=IMAGE_SHA, configuration_sha256=ledger["configuration_sha256"],
        snapshot_sha256=ledger["snapshot_sha256"], actual_numeric_case_rc=0, elapsed_s=data["elapsed_s"],
        runner_status="COMPLETE", runner_status_counts={"PASS": 1}, terminal_aborted=False,
        raw_strict_csv_recomputed_once=True, raw_equals_stored=True, recompute_seconds=elapsed,
        calls=98, predecessors=97, capacity=512, helper_instruction_retire_counts=[98] * 13,
        fullcap_results=50176, guards=196, actual_output_scalar_loads=50372, returned_vstart_zero=98,
        actual_a1_indices16_checked=98, indices16_address=hex(routine["addresses"]["indices16"]),
        distinct_wrong_indices_address=hex(routine["addresses"]["indices"]),
        call66_last_active=selected["call66_element255"], call66_full_tail_last=selected["call66_element511"],
        call98_last_active=selected["call98_element511"], call98_active_oor_zero_count=85,
        call98_partition=supplemental["call98_categories"], endpoint=strict["calls"][-1],
        csv_rows=strict["csv_rows"], retired=strict["retired_rows"], last_cycle=strict["csv_last_cycle"],
        soc_elf_sha256=case["sha256"], original_linux_elf_sha256=proof["original_linux_elf_sha256"],
        original_c_sha256=proof["original_c_sha256"], archived_target_pc=hex(archived[8]["pc"]),
        original_artifacts_unchanged=True, outer_service_actual_exit="UNAVAILABLE_AFTER_PARENT_REPORTED_GC",
        outer_worker_exit0_verified=False, GC_used_as_exit0_evidence=False, full2688_accepted=False,
        original_linux_replay_accepted=False, historical_stopped_tuple=None, active_VI31_queried=False,
        process_or_service_queries=False, no_DUT_or_Host_rerun=True, no_original_or_sealed_writes=True, pins=pins)
    save("audit.json", audit)
    print(json.dumps({key: value for key, value in audit.items() if key != "pins"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        save("AUDIT_NOT_ACCEPTED.json", dict(status="NOT_ACCEPTED", error=repr(error), no_DUT_rerun=True))
        raise
