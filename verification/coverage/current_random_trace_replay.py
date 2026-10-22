#!/usr/bin/env python3
"""Current-checker sidecar diagnostics for exactly201 random/replay VDBs.

No simulation, historical comparator override, admission or waiver approval.
Historical code pins are recorded separately, never replaced by current hashes.
Only the fresh output directory is writable by this driver.
Checkpoint/store read obligations are derived only from existing ELF symbols.
The random201 originals have final signatures, not per-instruction memory
checkpoints; successful replay does not claim that additional coverage.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
from pathlib import Path
import re
import signal
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "verification"))
import old_image_waiver_admission as admission
from ara_verify import random_rvv as random, spike_trace as scalar_api, vector_commit as vector_api
from ara_verify.contract import check_contract_log
from ara_verify.plan import _full_architecture_match, _full_vector_match, _load_fault_evidence_errors
from ara_verify.trace import validate_trace

OUT = ROOT / "verification/out"
BASELINE = OUT / "gap80-old-image-20261006-01"
LEDGER = admission.old.CURRENT / "all-passed-outcomes.json"
SCRIPT = Path(__file__).resolve()
TEST = HERE / "test_current_random_trace_replay.py"
SCHEMA = "current-random201-sidecar-v1"
require = admission.require


def json_read(path):
    return json.loads(Path(path).read_bytes())


def elf_metadata(blob):
    """Bounded ELF64 LE RISC-V sections/symbols, without readelf/objdump."""
    require(len(blob) >= 64 and blob[:6] == b"\x7fELF\x02\x01", "Invalid ELF64 LE")
    header = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(header[0:3] == (2, 243, 1) and header[10] == 64
            and 0 < header[11] < 65535, "Unsupported ELF machine/sections")
    entry, shoff, count = header[3], header[5], header[11]
    require(shoff + 64 * count <= len(blob), "Truncated ELF sections")
    sections = [struct.unpack_from("<IIQQQQIIQQ", blob, shoff + i * 64) for i in range(count)]
    for sec in sections:
        require(sec[1] == 8 or sec[4] + sec[5] <= len(blob), "Truncated ELF section data")
    symbols, definitions = {}, {}
    for sec in sections:
        if sec[1] != 2:
            continue
        require(sec[9] == 24 and sec[5] % 24 == 0 and sec[6] < count, "Malformed symbol table")
        strings = sections[sec[6]]
        require(strings[1] == 3, "Invalid symbol strings")
        text = blob[strings[4]:strings[4]+strings[5]]
        for off in range(sec[4], sec[4]+sec[5], 24):
            name, info, other, index, value, size = struct.unpack_from("<IBBHQQ", blob, off)
            if not name:
                continue
            require(name < len(text) and b"\0" in text[name:], "Bad ELF symbol name")
            label = text[name:text.index(b"\0", name)].decode("utf-8")
            # RISC-V local mapping symbols describe section contents, not evidence addresses.
            if info == 0 and re.fullmatch(r"\$(?:d|x(?:rv[0-9A-Za-z_]+)?)(?:\.\d+)?", label):
                continue
            used = (label == "tohost" or label.startswith("__ara_vector")
                    or re.fullmatch(r"region_\d+|__ara_region_\d+_end", label))
            if index == 0 and not used:
                continue
            if used:
                require(0 < index < count, "Evidence symbol has no concrete ELF section: "+label)
                owner = sections[index]
                require(owner[2] & 2 and owner[3] <= value <= owner[3]+owner[5]
                        and value+size <= owner[3]+owner[5], "Evidence symbol outside allocated section: "+label)
            definition = (index, value, info, other, size)
            require(label not in definitions or definitions[label] == definition,
                    "Ambiguous ELF symbol: "+label)
            definitions[label] = definition
            symbols[label] = value
    def bytes_at(address, length):
        matches = [s for s in sections if s[1] != 8 and s[2] & 4
                   and s[3] <= address and address + length <= s[3] + s[5]]
        require(len(matches) == 1, "ELF executable address is not uniquely bound")
        sec = matches[0]
        offset = sec[4] + address - sec[3]
        return blob[offset:offset+length]
    bytes_at(entry, 2)
    tohost = symbols.get("tohost")
    require(type(tohost) is int and any(s[2] & 2 and s[3] <= tohost
            and tohost + 8 <= s[3] + s[5] for s in sections), "Missing allocated tohost")
    exit_pc = symbols.get("__ara_vector_signature_exit_ecall")
    if exit_pc is None:
        start = symbols.get("__ara_vector_signature_read_done")
        require(start is not None, "Missing vector signature exit symbol")
        pc = start
        while pc < start + 128:
            half = int.from_bytes(bytes_at(pc, 2), "little")
            size = 4 if half & 3 == 3 else 2
            if size == 4 and bytes_at(pc, 4) == b"\x73\0\0\0":
                exit_pc = pc
                break
            pc += size
    require(exit_pc is not None and bytes_at(exit_pc, 4) == b"\x73\0\0\0", "Exit symbol is not ecall")
    instructions = {}
    for name, pc in symbols.items():
        if name.endswith("_read_loop") and name.startswith("__ara_vector"):
            half = int.from_bytes(bytes_at(pc, 2), "little")
            width = 4 if half & 3 == 3 else 2
            instructions[name] = int.from_bytes(bytes_at(pc, width), "little")
    return dict(entry=entry, tohost=tohost, exit_pc=exit_pc, symbols=symbols,
                sections=[dict(flags=s[2], address=s[3], size=s[5]) for s in sections],
                read_loop_instructions=instructions)


def signature_regions(meta):
    symbols = meta["symbols"]
    required = ("__ara_vector_signature", "__ara_vector_signature_read_loop", "__ara_vector_signature_read_done")
    require(all(s in symbols for s in required), "Missing signature symbols")
    start = symbols[required[0]]
    require(any(s["flags"] & 2 and s["address"] <= start and start + 4096 <= s["address"] + s["size"]
                for s in meta["sections"]), "Truncated signature storage")
    reads = [dict(pc=symbols[required[1]], start=start, size=4096, width=8, label="final_signature")]
    checkpoints = []
    for name in sorted(symbols):
        match = re.fullmatch(r"__ara_vector_checkpoint_(\d+)_start", name)
        if not match:
            continue
        prefix, index = name[:-6], int(match[1])
        require(all(prefix+suffix in symbols for suffix in ("_read_loop", "_read_done")), "Incomplete checkpoint symbols")
        location = dict(index=index, site=prefix, checkpoint_pc=hex(symbols[name]),
            read_loop_pc=hex(symbols[prefix+"_read_loop"]), read_done_pc=hex(symbols[prefix+"_read_done"]),
            memory_read_loop_pcs=[])
        if prefix+"_instruction" in symbols:
            location["instruction_pc"] = hex(symbols[prefix+"_instruction"])
        # Mask-count checkpoints have no full signature loop; scalar replay still checks the result.
        checkpoints.append(location)
        read_instruction = meta["read_loop_instructions"][prefix+"_read_loop"]
        if scalar_api._scalar_memory_access(read_instruction) == ("read", 8):
            reads.append(dict(pc=symbols[prefix+"_read_loop"], start=start, size=4096,
                              width=8, label=prefix+"_register_signature"))
        else:
            require(read_instruction & 127 == 0x57, "Unknown checkpoint read instruction")
        for memory_name in sorted(symbols):
            m = re.fullmatch(re.escape(prefix) + r"_(region_\d+)_read_loop", memory_name)
            if not m:
                continue
            region = m[1]
            require(region in symbols and "__ara_"+region+"_end" in symbols, "Missing store checkpoint region")
            size = symbols["__ara_"+region+"_end"] - symbols[region]
            require(0 <= size <= 1 << 24, "Invalid memory checkpoint extent")
            reads.append(dict(pc=symbols[memory_name], start=symbols[region], size=size, width=1, label=memory_name))
            location["memory_read_loop_pcs"].append(hex(symbols[memory_name]))
        location["memory_signature"] = bool(location["memory_read_loop_pcs"])
    return reads, checkpoints


def strict_verdict(scalar, vector):
    require(scalar.get("status") in ("MATCH", "TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH")
            and scalar.get("stopped_at_unobservable") is None and _full_architecture_match(scalar),
            "Incomplete scalar comparison/PREFIX")
    require(_full_vector_match(vector) and vector.get("first_mismatch") is None
            and vector.get("nr_lanes") == 4 and vector.get("vlen_bits") == 1024
            and type(vector.get("compared_bytes")) is int and vector["compared_bytes"] > 0
            and vector.get("non_bit_exact_instructions") == 0, "Incomplete/non-bit-exact vector comparison")


def require_known_active(value, compare_mask, reference_present):
    require(reference_present or compare_mask == 0, "Missing active reference state")
    require(value is not None or compare_mask == 0, "Unproven active unknown writeback")
    return "ISA_UNKNOWN" if compare_mask == 0 else "KNOWN_ACTIVE"


def unknown_audit(spike, commit, vector, entry, compared):
    lanes, vlen, activities = vector_api._parse_vector_trace(vector)
    starts, retires, traps = vector_api._parse_architecture_mapping(commit)
    arch = vector_api._map_architecture_retires(starts, retires, traps, allow_incomplete_tail=False)
    commits = vector_api._spike_from_entry(spike, entry)
    mapping = vector_api._map_spike_commits(arch, commits)
    by_spike = {index: activities[seq] for seq, index in mapping.items() if seq in activities}
    reference, unknown = {}, {}
    checked, masked, unknown_actual = 0, 0, 0
    compared_indices = {mapping[x["arch_seq"]] for x in compared["instructions"]}
    for index, item in enumerate(commits):
        pre = dict(reference)
        reference.update(item.vector_writes)
        activity = by_spike.get(index)
        if activity is None:
            continue
        vector_api._advance_unknown_state(unknown, activity, item, pre, vlen)
        if index not in compared_indices:
            continue
        require(item.vector_tail_agnostic is not None and item.vector_mask_agnostic is not None
                and item.vector_vl is not None and item.vector_vstart is not None,
                "Missing ISA tail/mask/vl/vstart policy")
        if vector_api._uses_mask_predicate(activity.instruction):
            require(0 in pre, "Unproven predicate state")
        for (register, byte), (value, write) in vector_api._architectural_bytes(activity.writes, lanes, vlen).items():
            if register not in item.vector_writes:
                require(value is not None and register in pre
                        and value == ((pre[register] >> (8 * byte)) & 255),
                        "Unproven transport/preservation write")
                checked += 1
                continue
            mask = vector_api._architectural_compare_mask(activity, register, byte, vlen, pre,
                item.vector_writes.keys(), item.vector_vl, item.vector_vstart,
                item.vector_tail_agnostic, item.vector_mask_agnostic)
            mask &= ~((unknown.get(register, 0) >> (byte * 8)) & 255)
            classification = require_known_active(value, mask, register in reference)
            if classification == "ISA_UNKNOWN":
                masked += 1
            else:
                checked += 1
            unknown_actual += int(value is None)
    return dict(status="PASS", known_active_bytes=checked, isa_unconstrained_bytes=masked,
                unknown_writeback_bytes=unknown_actual, unproven_active_unknown_bytes=0,
                policy="ISA tail/mask and checker-proven propagated unknown bits; never unconditional unknown skip")


def validate_commands(artifact, case, meta, rtl, spike, wrapper):
    require(rtl.get("cwd") == spike.get("cwd") == str(artifact), "Foreign command cwd")
    expected = [wrapper, "-l", "run.vcs.log", "+ntb_random_seed="+str(case["seed"]),
        "+PRELOAD="+str(artifact/"input.elf"), "+TESTCASE="+case["source_name"], "+NO_FSDB",
        "+COMMIT_TRACE="+str(artifact/"ara_commit_trace.csv"),
        "+VECTOR_TRACE="+str(artifact/"ara_vector_trace.csv"),
        "+COMMIT_WATCHDOG="+str(case["watchdog_cycles"]), "+COMMIT_TOHOST=%016x" % meta["tohost"],
        "+COMMIT_EXIT_PC=%016x" % meta["exit_pc"]]
    if case.get("fault_vstart_probe"):
        expected.append("+ARA_FAULT_VSTART_PROBE")
    require(rtl.get("command") == expected, "Producer RTL command/ELF symbols differ")
    expected_spike = [case["spike"], "--isa="+case["contract"]["isa"], "--log-commits",
                      "--log="+str(artifact/"spike_commit.log"), str(artifact/"input.elf")]
    require(spike.get("command") == expected_spike, "Producer Spike command differs")


def select201(inputs, rows):
    require(len(inputs) == 688 and len(set(inputs)) == 688, "Not exact687 input membership")
    selected = [row for row in rows if row.get("kind") in ("random", "replay") and row["vdb"] in inputs[1:]]
    require(len(selected) == 201 and Counter(r["kind"] for r in selected) == {"random": 186, "replay": 15}
            and len({r["vdb"] for r in selected}) == len({r["name"] for r in selected}) == 201,
            "Not exact201 fulltrace population")
    for row in selected:
        require(row.get("status") == "PASS" and row.get("passed_only") is True and row.get("reused") is False
                and row.get("vdb_valid") is True and type(row.get("returncode")) is int
                and row["returncode"] == 0, "Non-PASS historical input")
    return selected


def choose_rows(rows, names=(), limit=1):
    require(type(limit) is int and 1 <= limit <= 201 and len(set(names)) == len(names), "Invalid bounded case selection")
    if not names:
        return rows[:limit]
    selected = []
    for name in names:
        found = [row for row in rows if row["name"] == name or Path(row["vdb"]).parent.name == name]
        require(len(found) == 1, "Missing/ambiguous named sample: "+name)
        require(found[0] not in selected, "Duplicate sample aliases")
        selected.append(found[0])
    require(len(selected) <= limit, "Named samples exceed explicit limit")
    return selected


def check_checkpoint_report(scalar, locations, traps):
    report = random._vector_checkpoint_report(scalar, locations, completed=True, checkpoint_traps=traps)
    require(report["status"] == "PASS", "Checkpoint failure")
    return report


def sourcepins():
    paths = [*sorted((ROOT/"verification/ara_verify").glob("*.py")), SCRIPT, TEST,
             admission.SCRIPT, HERE/"gap74_native_hash_session.py",
             *[HERE/name for name in admission.old.PROTECTED], Path(sys.executable).resolve()]
    return {str(p): admission.sha_bytes(p.read_bytes()) for p in paths}


def bound_json(seal, path, expected=None):
    seal.pin(path, expected)
    return seal.read(path)


def bound_ledger(seal):
    # The sealed collection, not IDENTITY, owns the ledger's expected hash.
    path = admission.old.CURRENT/"collection.json"
    seal.pin(path, admission.old.IDENTITY["collection.json"])
    collection = seal.read(path)
    seal.pin(LEDGER, collection["reports"][str(LEDGER)])
    return seal.read(LEDGER)


def build_profile(row, expected_image, expected_simv):
    seal = admission.FileSeal()
    seal.hashes(row["files"])
    artifact = Path(row["vdb"]).parent
    targets = [p for p in artifact.parents if p.parent.name == "results" and p.name == row["name"]]
    require(len(targets) == 1, "Unknown random result layout")
    target = targets[0]
    producer = target.parent.parent
    plan_hashes = seal.read(producer/"plan.sha256.json")
    require(str(producer/"plan.json") in plan_hashes, "Unbound producer plan")
    plan = bound_json(seal, producer/"plan.json", plan_hashes[str(producer/"plan.json")])
    require(plan["image"] == expected_image and plan["simv"] == expected_simv, "Foreign producer image")
    cases = [c for c in plan["cases"] if c["name"] == row["name"]]
    require(len(cases) == 1, "Ambiguous producer case")
    case = cases[0]
    require(all(case[k] == row[k] for k in ("kind", "elf_sha256", "coverage_test", "contract")),
            "Producer row/case differs")
    require(case["oracle"] == "Spike+scalar+vector+independent-audit", "Foreign oracle")
    outcome = bound_json(seal, producer/"outcomes"/(row["name"]+".json"))
    require(outcome == row, "Producer outcome differs")
    require(str(target/"independent_audit.json") in row["files"], "Unbound original audit")
    original_audit = seal.read(target/"independent_audit.json")
    admission.old.prior.sealed.full.batch.audit_ok(original_audit, case, artifact)
    summary = seal.read(target/"summary.json")
    require(len(summary) == 1 and summary[0]["status"] == "PASS"
            and summary[0]["artifact_dir"] == str(artifact), "Producer summary differs")
    seal.hashes(case["source_files"])
    inputs = seal.read(artifact/"inputs.json")
    result = seal.read(artifact/"result.json")
    require(result["status"] == "PASS" and result["input_errors"] == []
            and result["artifact_dir"] == str(artifact) and result["elf"] == str(artifact/"input.elf")
            and result["spike_returncode"] == result["rtl_returncode"] == 0
            and result["spike_timed_out"] is False and result["rtl_timed_out"] is False
            and result["rtl_success"] is True, "Original runtime incomplete/failed")
    require(inputs["binary"]["path"] == str(artifact/"input.elf")
            and inputs["binary"]["sha256"] == row["elf_sha256"]
            and inputs["spike"]["path"] == case["spike"] and inputs["spike"]["sha256"] == case["spike_sha256"]
            and inputs["simv"]["image_sha256"] == plan["wrapper_image"], "Runtime input binding differs")
    seal.hashes(plan["image"])
    seal.hashes(plan["wrapper_image"])
    seal.pin(case["spike"], case["spike_sha256"])
    elf = seal.pin(artifact/"input.elf", row["elf_sha256"])
    seal.pin(case["frozen_elf"], row["elf_sha256"])
    meta = elf_metadata(elf.read_bytes())
    reads, locations = signature_regions(meta)
    rtl = seal.read(artifact/"rtl.command.json")
    spike = seal.read(artifact/"spike.command.json")
    validate_commands(artifact, case, meta, rtl, spike, inputs["simv"]["path"])
    coverage = seal.read(artifact/"coverage.command.json")
    expected_coverage = [plan["simv"], *rtl["command"][1:], "-cm", "line+cond+fsm+tgl+branch",
                         "-cm_dir", row["vdb"], "-cm_name", row["coverage_test"]]
    require(coverage == dict(command=expected_coverage, cwd=str(artifact)), "Actual simulator command differs")
    vdb_files = admission.old.prior.sealed.full.batch.valid_vdb(Path(row["vdb"]), row["coverage_test"], plan["simv"])
    require(vdb_files == row["vdb_files"], "VDB membership/identity differs")
    seal.hashes(vdb_files)
    for name in ("input.elf", "inputs.json", "result.json", "rtl.command.json", "spike.command.json",
                 "coverage.command.json", "spike_commit.log", "ara_commit_trace.csv", "ara_vector_trace.csv",
                 "rtl_console.log", "run.vcs.log"):
        require(str(artifact/name) in row["files"], "Required replay input is not historically bound: "+name)
        seal.pin(artifact/name, row["files"][str(artifact/name)])
    exceptions = artifact/"trace_hart_0.log"
    if exceptions.exists():
        require(str(exceptions) in row["files"], "Unbound exception log")
        seal.pin(exceptions, row["files"][str(exceptions)])
    seal.finish()
    return dict(name=row["name"], vdb=row["vdb"], artifact=str(artifact), producer=str(producer), case=case,
        elf_metadata=meta, read_regions=reads, checkpoint_locations=locations,
        exception_log=str(exceptions) if exceptions.exists() else None, input_sha256=dict(seal.files),
        historical_checker_pins={p:h for p,h in plan["files"].items() if "/verification/ara_verify/" in p},
        historical_checker_pins_verified_against_current=False)


def deadline_expired(signum, frame):
    raise TimeoutError("Per-case offline replay deadline exhausted")


def read_coverage_obligations(profile, scalar):
    artifact = Path(profile["artifact"])
    retires = scalar_api.parse_ara_retire(artifact/"ara_commit_trace.csv")
    reports = []
    for region in profile["read_regions"]:
        actual = [item for item in retires if not item.trap and item.pc == region["pc"]]
        addresses = [item.mem_addr for item in actual]
        expected = list(range(region["start"], region["start"]+region["size"], region["width"]))
        require(addresses == expected, "Signature/store checkpoint read coverage incomplete: "+region["label"])
        require(all(scalar_api._scalar_memory_access(item.instruction) == ("read", region["width"])
                    for item in actual), "Signature load instruction differs")
        reports.append(dict(label=region["label"], loads=len(actual), checked_bytes=region["size"]))
    traps = random._checkpoint_traps(artifact/"ara_commit_trace.csv", profile["checkpoint_locations"],
                                    Path(profile["exception_log"]) if profile["exception_log"] else None)
    checkpoint = check_checkpoint_report(scalar, profile["checkpoint_locations"], traps)
    for location in profile["checkpoint_locations"]:
        for key in ("checkpoint_pc", "read_loop_pc"):
            pc = int(location[key], 16)
            require(any(not item.trap and item.pc == pc for item in retires), "Checkpoint was not executed")
    return dict(status="PASS", signature_and_store_reads=reports, checkpoints=checkpoint,
                scalar_store_values="checked by current scalar retirement comparator")


def replay(profile, code_pins, timeout_s):
    require(type(timeout_s) is int and 1 <= timeout_s <= 300, "Bounded300s replay deadline required")
    previous = signal.signal(signal.SIGALRM, deadline_expired)
    signal.alarm(timeout_s)
    try:
        with admission.old.no_tools():
            seal = admission.FileSeal()
            seal.hashes(code_pins)
            seal.hashes(profile["input_sha256"])
            a = Path(profile["artifact"])
            logs = [a/"rtl_console.log", a/"run.vcs.log"]
            for log in logs:
                text = log.read_text(errors="replace")
                require(text.count("Core Test *** SUCCESS ***") == 1
                        and not re.search(r"Fatal:|Error:|commit watchdog|Core Test \*\*\* FAIL", text, re.I),
                        "Runtime log is not complete PASS")
                require(not check_contract_log(log), "Contract runtime violation")
            m = profile["elf_metadata"]
            spike, commit, vector = a/"spike_commit.log", a/"ara_commit_trace.csv", a/"ara_vector_trace.csv"
            unobservable = vector_api.unobservable_vector_scalar_write_indices(spike, commit, vector, m["entry"])
            fault = bool(profile["case"].get("fault_vstart_probe"))
            scalar = scalar_api.compare_commit_prefix(spike, commit, m["entry"], unobservable,
                terminal_ecall_pc=m["exit_pc"], terminal_tohost_address=m["tohost"],
                rtl_exception_log=Path(profile["exception_log"]) if profile["exception_log"] else None,
                fault_vector_trace=vector if fault else None, fault_probe_log=a/"run.vcs.log" if fault else None)
            compared = vector_api.compare_vector_commits(spike, commit, vector, m["entry"],
                aligned_vector_faults=scalar.get("aligned_vector_faults"),
                fault_probe_log=a/"run.vcs.log" if fault else None)
            strict_verdict(scalar, compared)
            require(not _load_fault_evidence_errors(a, scalar, compared), "Fault proof binding failed")
            trace = dict(status="VALID", **validate_trace(commit))
            unknown = unknown_audit(spike, commit, vector, m["entry"], compared)
            obligations = read_coverage_obligations(profile, scalar)
            seal.finish()
            return dict(schema=SCHEMA, status="PASS_DIAGNOSTIC_ONLY", name=profile["name"], vdb=profile["vdb"],
                scalar=scalar, vector=compared, trace=trace, unknown_audit=unknown, obligations=obligations,
                input_sha256=profile["input_sha256"], current_checker_sourcepins=code_pins,
                historical_checker_pins=profile["historical_checker_pins"],
                historical_checker_pins_verified_against_current=False,
                all_state_bytes_compared=False, admitted687=False, application_approval=False)
    except Exception as error:
        return dict(schema=SCHEMA, status="FAILED_DIAGNOSTIC_ONLY", name=profile["name"], vdb=profile["vdb"],
                    reason=f"{type(error).__name__}: {error}", admitted687=False, application_approval=False)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def prepare(output, names=(), limit=1, timeout_s=180):
    require(type(timeout_s) is int and 1 <= timeout_s <= 300, "Bounded300s per profile required")
    output = Path(output).absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == OUT.resolve(strict=True), "Fresh sidecar directory required")
    seal = admission.FileSeal()
    state = seal.read(BASELINE/"status.json")
    require(state["status"] == state["coverage_status"] == "COMPLETE"
            and type(state["aggregate_passed"]) is int and state["aggregate_passed"] == 687
            and state.get("live_rtl_reverted") is False,
            "Fixed completed687 required")
    rows = bound_ledger(seal)
    seal.pin(BASELINE/"combined-inputs.txt")
    inputs = (BASELINE/"combined-inputs.txt").read_text().splitlines()
    selected = select201(inputs, rows)
    chosen = choose_rows(selected, names, limit)
    plan = seal.read(admission.old.CURRENT/"plan.json")
    require(inputs[0] == plan["design_vdb"] and state["image"] == plan["simv"], "Foreign design/image")
    seal.pin(admission.old.CURRENT/"plan.json", admission.old.IDENTITY["plan.json"])
    seal.hashes(plan["image"])
    code = sourcepins()
    seal.hashes(code)
    profiles = []
    for row in chosen:
        previous = signal.signal(signal.SIGALRM, deadline_expired)
        signal.alarm(timeout_s)
        try:
            profiles.append(build_profile(row, plan["image"], plan["simv"]))
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
    for profile in profiles:
        seal.hashes(profile["input_sha256"])
    seal.finish()
    manifest = dict(schema=SCHEMA, status="PREPARED_NOT_REPLAYED", baseline=str(BASELINE), corpus_tests=687,
        replay_tests=len(profiles), available_random_fulltrace=201,
        remaining_corpus_not_revalidated=687-len(profiles), profiles=profiles,
        corpus_sha256=dict(seal.files), current_checker_sourcepins=code,
        admitted687=False, simulations_started=False, application_approval=False)
    output.mkdir()
    with (output/"manifest.json").open("x") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return dict(status=manifest["status"], profiles=len(profiles),
                manifest_sha256=admission.sha_bytes((output/"manifest.json").read_bytes()))


def check(output, manifest_sha256, workers=8, timeout_s=180):
    require(type(workers) is int and 1 <= workers <= 8 and type(timeout_s) is int and 1 <= timeout_s <= 300,
            "At most8 workers and bounded300s per case")
    output = Path(output).resolve(strict=True)
    require(output.parent == OUT.resolve(strict=True), "Foreign sidecar directory")
    require(isinstance(manifest_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", manifest_sha256), "Reviewed manifest SHA256 required")
    seal = admission.FileSeal()
    seal.pin(output/"manifest.json", manifest_sha256)
    manifest = seal.read(output/"manifest.json")
    count = manifest.get("replay_tests")
    require(manifest.get("schema") == SCHEMA and manifest.get("status") == "PREPARED_NOT_REPLAYED"
            and type(count) is int and 1 <= count <= 201 and len(manifest["profiles"]) == count
            and manifest.get("available_random_fulltrace") == 201
            and manifest.get("baseline") == str(BASELINE) and manifest.get("corpus_tests") == 687
            and manifest.get("admitted687") is False and manifest.get("application_approval") is False
            and manifest.get("simulations_started") is False,
            "Invalid prepared201 manifest")
    require(not (output/"cases").exists() and not (output/"diagnostic.json").exists(), "Fresh check outputs required")
    seal.hashes(manifest["corpus_sha256"])
    require(manifest["current_checker_sourcepins"] == sourcepins(), "Current checker version changed since prepare")
    (output/"cases").mkdir()
    results = {}
    with ProcessPoolExecutor(max_workers=min(workers, count), mp_context=multiprocessing.get_context("spawn")) as pool:
        jobs = {pool.submit(replay, p, manifest["current_checker_sourcepins"], timeout_s): i
                for i, p in enumerate(manifest["profiles"])}
        for future in as_completed(jobs):
            index = jobs[future]
            try:
                result = future.result()
            except Exception as error:
                profile = manifest["profiles"][index]
                result = dict(status="FAILED_DIAGNOSTIC_ONLY", name=profile["name"],
                              reason=f"Worker failure: {type(error).__name__}: {error}", admitted687=False)
            results[index] = result
            with (output/"cases"/("%03d.json" % index)).open("x") as stream:
                json.dump(result, stream, indent=2)
                stream.write("\n")
    for profile in manifest["profiles"]:
        seal.hashes(profile["input_sha256"])
    seal.finish()
    passed = sum(r["status"] == "PASS_DIAGNOSTIC_ONLY" for r in results.values())
    report = dict(schema=SCHEMA, status="CURRENT_RANDOM_SAMPLE_DIAGNOSTICS_COMPLETE" if passed == count else "CURRENT_RANDOM_SAMPLE_DIAGNOSTICS_FAILED",
        passed=passed, failed=count-passed, corpus_tests=687, replay_tests=count, available_random_fulltrace=201,
        remaining_corpus_not_revalidated=687-count, admitted687=False, application_approval=False,
        simulations_started=False, case_results={str(i):results[i]["status"] for i in sorted(results)})
    with (output/"diagnostic.json").open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--case-timeout", type=int, default=180)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    result = prepare(args.output, args.case, args.limit, args.case_timeout) if args.command == "prepare" else check(
        args.output, args.manifest_sha256, args.workers, args.case_timeout)
    print(json.dumps(result, indent=2))
    if result.get("failed", 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
