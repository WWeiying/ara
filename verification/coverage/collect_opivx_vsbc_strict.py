"""Offline VSBC terminal audit and raw candidate only; never launch or admit."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re

import build_opivx_vsbc_preflight as software
import run_opivx_vsbc_simulation as runner
import coverage_bitmap_delta as bitmap
from ara_verify import spike_trace
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log

life, require = runner.life, software.require
ROOT, OUT = life.ROOT, life.OUT
RUN = OUT / "opivx-vsbc-vd0-old-image-717-20261006-01"
PRE_SEAL = "3b4e1c23901fe45c0b1e5434e7f244d2a8e041b103e0e0315cfd59ef685e3d09"
RUN_SEAL = "6f8305a62c1dfcc6c646d4faf19465c5fcabafeeec9bf4199449bb017e5dea7b"
BASE = OUT / "cache-port1-offline-admitted-717-20261006-01"
DESIGN = Path(str(life.IMAGE) + ".vdb")
COMMIT_FIELDS = ("cycle", "event", "order", "port", "trans_id", "pc", "insn", "rd",
                 "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata", "trap")
VECTOR_FIELDS = ("cycle", "event", "arch_seq", "vid", "lane", "source", "insn", "use_vd",
                 "vd", "eew", "vl", "vstart", "addr", "be", "wdata", "nr_lanes", "vlen_bits")
BAD, RECOVERY = 0x4883c057, 0x4883c557


def scalar_memory(insn):
    if insn & 3 == 3:
        return spike_trace._scalar_memory_access(insn)
    if insn & 3 in (0, 2):
        return {2: ("read", 4), 3: ("read", 8), 6: ("write", 4), 7: ("write", 8)}.get(insn >> 13)
    return None


def read_csv(raw, fields):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    require(tuple(reader.fieldnames or ()) == fields, "CSV schema differs")
    rows = list(reader)
    require(rows and all(None not in r and all(v is not None and v != "" for v in r.values())
                         for r in rows), "Empty/truncated CSV rows")
    return rows


def reference_counts(commits, symbols):
    prefix = []
    for c in commits:
        if not prefix and c.pc != 0x80000000:
            continue
        prefix.append(c)
        if (symbols["tohost"], 1) in c.memory_accesses:
            break
    require(prefix and prefix[-1].memory_accesses == ((symbols["tohost"], 1),), "Reference terminal missing")
    return dict(matched_instructions=len(prefix),
                matched_scalar_writes=sum(len({r: v for r, v in c.gpr_writes.items() if r}) for c in prefix),
                matched_floating_writes=sum(len(c.fpr_writes) for c in prefix),
                matched_scalar_memory_accesses=sum(bool(c.memory_accesses) and
                    spike_trace._scalar_memory_access(c.instruction) is not None for c in prefix),
                terminal_tohost=dict(pc="0x%016x" % prefix[-1].pc,
                    instruction="0x%08x" % prefix[-1].instruction,
                    address="0x%016x" % symbols["tohost"], write_value="0x1"))


def scalar_exact(result, expected):
    fixed = dict(status="TERMINAL_TOHOST_MATCH", entry="0x0000000080000000",
                 rvfi_store_data_layout="unshifted", skipped_unobservable_register_values=0,
                 stopped_at_unobservable=None, aligned_vector_faults=[], ara_trap_events=0,
                 mismatch=None, terminal_ecall=None, vector_state_compared=False)
    fixed.update(expected)
    fixed.update(ara_retired_instructions=expected["matched_instructions"],
                 ara_committed_instructions=expected["matched_instructions"])
    for key, value in fixed.items():
        require(key in result and type(result[key]) is type(value) and result[key] == value,
                "Complete scalar comparison differs: " + key)


def lifecycle(rows, vectors, symbols):
    starts, pending, requests, responses, rejected = {}, {}, [], [], []
    allocations, completions = Counter(), Counter()
    for row in rows:
        event, tid, seq = row["event"], int(row["trans_id"]), int(row["order"])
        insn = int(row["insn"], 16)
        if event == "arch_start":
            require(seq not in starts and tid not in pending, "Duplicate architectural/live transaction")
            starts[seq], pending[tid] = row, [seq, False]
        elif event == "cvx_req":
            require(tid in pending and not pending[tid][1], "Unknown/duplicate request")
            seq = pending[tid][0]
            require(insn == int(starts[seq]["insn"], 16), "CVX request opcode differs")
            pending[tid][1] = True
            requests.append(seq)
        elif event == "cvx_resp":
            require(tid in pending and pending[tid][1], "Unknown/duplicate response")
            seq, _ = pending.pop(tid)
            responses.append(seq)
            if int(row["trap"]):
                rejected.append(seq)
        elif event in ("uop_alloc", "uop_done"):
            require(seq in starts, "Unowned backend event")
            (allocations if event == "uop_alloc" else completions)[seq, int(row["port"])] += 1
        else:
            require(event == "retire", "Unknown commit event")
    require(not pending and Counter(requests) == Counter(starts.keys()) == Counter(responses),
            "CVX request/response conservation differs")
    require(allocations == completions, "Unfinished backend uop")
    bad = [s for s, r in starts.items() if int(r["insn"], 16) == BAD]
    good = [s for s, r in starts.items() if int(r["insn"], 16) == RECOVERY]
    require(len(bad) == len(good) == 1 and rejected == bad, "Exact illegal/recovery request population differs")
    require(not any(s == bad[0] for s, _ in allocations), "Illegal backend allocation")
    require(any(s == good[0] for s, _ in allocations), "Legal recovery has no backend execution")
    retired_good = [r for r in rows if r["event"] == "retire" and int(r["insn"], 16) == RECOVERY]
    require(len(retired_good) == 1 and int(retired_good[0]["pc"], 16) == symbols["gvs_recovery"],
            "Recovery retirement identity differs")
    va, vd = Counter(), Counter()
    for row in vectors:
        seq, event = int(row["arch_seq"]), row["event"]
        require(int(row["nr_lanes"]) == 4 and int(row["vlen_bits"]) == 1024, "Vector configuration differs")
        require(seq != bad[0], "Illegal vector activity including configuration")
        if event == "config":
            continue
        require(seq in starts and event in ("alloc", "done", "write"), "Unowned/unknown vector activity")
        require(int(row["insn"], 16) == int(starts[seq]["insn"], 16), "Vector opcode differs")
        if event in ("alloc", "done"):
            (va if event == "alloc" else vd)[seq, int(row["vid"])] += 1
    require(va == vd == allocations, "Commit/vector lifecycle differs")
    return dict(requests=len(requests), responses=len(responses), exceptions=1,
                exception_arch_seq=bad[0], recovery_arch_seq=good[0],
                backend_uops=sum(allocations.values()), rejected_backend_uops=0, rejected_vrf_activities=0)


def observed(rows, symbols):
    retired = [r for r in rows if r["event"] == "retire"]
    require(retired and [int(r["order"]) for r in retired] == list(range(len(retired))), "Incomplete retirement order")
    memory, dump_loads, terminals, handler_stores = {}, set(), [], []
    dump_start, dump_end = symbols["gvs_dump"], symbols["gvs_dump"] + 864
    for row in retired:
        insn, pc = int(row["insn"], 16), int(row["pc"], 16)
        require(not int(row["trap"]) and pc not in (symbols["gvs_bad"], symbols["trap_fail"]),
                "Unexpected RVFI trap/illegal retirement")
        address = int(row["mem_addr"], 16)
        rmask, wmask = int(row["mem_rmask"], 16), int(row["mem_wmask"], 16)
        access = scalar_memory(insn)
        handler = symbols["gvs_handler"] <= pc < symbols["gvs_handler_end"]
        if handler:
            require(int(row["rd"]) in (0, 5, 6, 7), "Handler writes protected scalar register")
            if insn & 127 == 0x73 and (insn >> 12) & 7:
                fn, rs1 = (insn >> 12) & 7, (insn >> 15) & 31
                writes_csr = fn in (1, 5) or (fn in (2, 3, 6, 7) and rs1 != 0)
                require(not writes_csr or insn >> 20 in (0x340, 0x341), "Handler writes protected CSR")
        if access:
            kind, size = access
            mask = ((1 << size) - 1) << (address & 7)
            require(address % size == 0 and rmask == (mask if kind == "read" else 0) and
                    wmask == (mask if kind == "write" else 0), "Scalar memory address/mask differs")
            if kind == "write":
                value = int(row["mem_wdata"], 16) & ((1 << (8 * size)) - 1)
                memory.update({address + i: b for i, b in enumerate(value.to_bytes(size, "little"))})
                if address == symbols["tohost"]:
                    terminals.append(row)
                if handler:
                    handler_stores.append((address, size))
            elif dump_start <= address < dump_end:
                require(int(row["rd"]) != 0 and address + size <= dump_end, "Unobservable dump load")
                value = int(row["rd_wdata"], 16) & ((1 << (8 * size)) - 1)
                memory.update({address + i: b for i, b in enumerate(value.to_bytes(size, "little"))})
                dump_loads.update(range(address, address + size))
        else:
            require(not rmask and not wmask, "Unrecognized memory effect")
    require(terminals == [retired[-1]], "Missing/extra/post-terminal retirement")
    require(dump_loads == set(range(dump_start, dump_end)), "Incomplete explicit dump/guard readback")
    def read(name, offset=0, width=8):
        addr = symbols[name] + offset
        require(all(addr + i in memory for i in range(width)), "Missing observed signature: " + name)
        return int.from_bytes(bytes(memory[addr + i] for i in range(width)), "little")
    restore = [read("gvs_restore", i * 8) for i in range(12)]
    require(all(restore[i] == restore[i + 1] for i in range(0, 12, 2)) and
            restore[0] == symbols["trap_fail"] and restore[2] == 0 and
            0x80100000 <= restore[4] < 0x80200000 and restore[4] % 16 == 0 and
            restore[6:] == [0] * 6, "Restore footprint differs")
    sp = restore[4]
    ledger = [read("gvs_ledger", i * 8) for i in range(12)]
    require(ledger == [2, symbols["gvs_bad"], BAD, 4, 0, 1, 5, 1, 0x2222, 3, 117, sp], "Illegal ledger/vstart differs")
    require([read("gvs_post", i * 8) for i in range(9)] ==
            [0x1111, 0x2222, 3, sp, 1, 4, 0, 5, 117], "Post-mret register/CSR/vstart differs")
    require(read("gvs_traps") == 1 and read("g75_result", width=4) == 138 and
            read("g75_result", 4, 4) == read("num_failed", width=4) == 0 and read("tohost") == 1,
            "Software checks/terminal differ")
    for phase in range(2):
        for reg in range(3):
            actual = b"".join(read("gvs_dump", ((phase * 3 + reg) * 18 + w) * 8).to_bytes(8, "little")
                              for w in range(18))
            expected = b"\xa5" * 8 + software.expected_register(reg, bool(phase)) + b"\xa5" * 8
            require(actual == expected, "Observed full VRF/guard/recovery differs")
    allowed = {(symbols["gvs_ledger"] + i * 8, 8) for i in range(12)} | {(symbols["gvs_traps"], 8)}
    require(Counter(handler_stores) == Counter(allowed), "Handler store footprint differs")
    return dict(checks=138, failed_checks=0, ledger=ledger, trap_vstart=1, post_mret_vstart=1,
                observed_vrf_bytes=768, guard_bytes=96, explicit_dump_read_bytes=864,
                handler_store_words=13, context_restored=True, retirements=len(retired))


def vector_exact(result, rejected, reference):
    fixed = dict(status="PASS", compared_instructions=4, skipped_unknown_bytes=0,
                 non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024, selected_index=None,
                 stopped_at_spike_index=None, trapped_requests=[rejected], first_mismatch=None,
                 unobservable_instructions=0, incomplete_requests=[], unretired_requests=[])
    for key, value in fixed.items():
        require(key in result and type(result[key]) is type(value) and result[key] == value,
                "Full vector comparison differs: " + key)
    records = result["instructions"]
    expected = [(c.pc, c.instruction) for c in reference if c.vector_writes]
    require(len(expected) == len(records) == 4 and
            [(int(r["pc"], 16), int(r["instruction"], 16)) for r in records] == expected,
            "Vector PCs/opcodes/population differ")
    require([r["compared_bytes"] for r in records[:3]] == [128] * 3 and
            4 <= records[3]["compared_bytes"] <= 128 and
            result["compared_bytes"] == sum(r["compared_bytes"] for r in records), "Vector byte population differs")
    require(all(r["status"] == "PASS" and r["skipped_unknown_bytes"] == r["unknown_write_bytes"] ==
                r["mismatch_count"] == 0 and r["first_mismatch"] is None for r in records), "Vector record differs")


def tracer_exact(text, rows, symbols):
    regex = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual = [m.groups() for line in text.splitlines() if (m := regex.match(line))]
    retired = [r for r in rows if r["event"] == "retire"]
    wanted = [(str(int(r["cycle"])), "M", r["pc"], r["insn"]) for r in retired]
    require(actual[:len(wanted)] == wanted, "Tracer/scalar full prefix differs")
    tail = actual[len(wanted):]
    require(not tail or tail == [(wanted[-1][0], "M", "%016x" % (int(wanted[-1][2], 16) + 4), "0000a001")],
            "Unknown/post-terminal tracer tail")
    events = re.findall(r'Exception @\s*(\d+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)', text)
    require(len(events) == text.count("Exception @") == 1 and events[0][2] == "Illegal Instruction" and
            int(events[0][1], 16) == symbols["gvs_bad"] and
            re.findall(r'tval: ([0-9a-fA-F]+)', text) == ["000000004883c057"], "Exact exception PC/cause/tval differs")
    return dict(illegal_exceptions=1, cause=2, pc=hex(symbols["gvs_bad"]), tval=hex(BAD), tracer_tail=tail)


def target_hits(before, single, targets):
    require(single["tests"] == [str(RUN / "code.vdb")] and str(RUN / "code.vdb") not in before["tests"],
            "Duplicate/unexpected candidate VDB")
    hits = []
    for metric, t in targets.items():
        old, new = before["metrics"][metric][t["scope"]], single["metrics"][metric][t["scope"]]
        require((old["width"], old["checksum"]) == (t["scope_width"], t["scope_checksum"]) ==
                (new["width"], new["checksum"]), "Target actual shape differs")
        index = t["point"]["raw_index"]; bit = 1 << (old["width"] - 1 - index)
        require(not int(old["bits"], 16) & bit and int(new["bits"], 16) & bit, "Target zero gain/already hit")
        hits.append(dict(metric=metric, scope=t["scope"], raw_index=index, hit_before=False, hit_single=True))
    return hits


def prepare(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct prepare directory")
    run = life.read_bound(RUN.with_name(RUN.name + ".prepared.json"), RUN_SEAL)
    pre = life.read_bound(runner.PRE / "preflight-manifest.json", PRE_SEAL)
    runner.validate(pre)
    pins = dict(run["pins"])
    paths = [Path(__file__).resolve(), Path(__file__).with_name("test_collect_opivx_vsbc_strict.py"),
             Path(bitmap.__file__).resolve(), *sorted((ROOT / "verification/ara_verify").glob("*.py"))]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths})
    pins = life.merge_pins(pins, {str(RUN.with_name(RUN.name + ".prepared.json")): RUN_SEAL})
    life.check(pins)
    reference = software.parse_spike_commits(runner.PRE / "spike.trace")
    plan = dict(status="STRICT_COLLECTOR_PREPARED_NOT_EXECUTED", case=software.NAME, run=str(RUN),
                baseline=str(BASE), baseline_tests=717, reference_counts=reference_counts(reference, pre["symbols"]),
                pins=pins, preflight_seal=PRE_SEAL, prepared_run_seal=RUN_SEAL,
                historical_ZCC_pin="Historical provenance only; collector never executes that tool.",
                coverage_admitted=False, simulations_started=False, exclusions_generated=False)
    out.mkdir(); life.save(out / "plan.json", plan)
    print(json.dumps(dict(plan=str(out / "plan.json"), seal=life.digest(out / "plan.json"), pins=len(pins))))


def collect(plan_path, seal, out):
    plan = life.read_bound(plan_path, seal); life.check(plan["pins"])
    require(plan["status"] == "STRICT_COLLECTOR_PREPARED_NOT_EXECUTED" and plan["run"] == str(RUN), "Plan identity")
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct audit directory")
    pins = dict(plan["pins"]); pins[str(plan_path)] = seal
    def read(path):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(), "Aliased evidence")
        pins.update(life.merge_pins(pins, {str(path): life.digest(path)}))
        return path.read_bytes()
    require((RUN / "simulation-status.json").is_file(), "HOLD: no terminal simulation-status; no audit started")
    out.mkdir()
    try:
        state = json.loads(read(RUN / "simulation-status.json"))
        require(state["status"] == "SIMULATION_EXITED_NOT_ADMITTED" and state["returncode"] == 0 and
                state["case"] == software.NAME and state["coverage_admitted"] is False, "Simulation failed/not terminal PASS")
        prepared = life.read_bound(RUN.with_name(RUN.name + ".prepared.json"), RUN_SEAL)
        require(json.loads(read(RUN / "manifest.json")) == prepared, "Actual runtime contract differs")
        pre = life.read_bound(runner.PRE / "preflight-manifest.json", PRE_SEAL); runner.validate(pre)
        before = json.loads(read(BASE / "combined-bits.json"))
        require(len(before["tests"]) == len(set(before["tests"])) == 717 and
                read(BASE / "combined-inputs.txt").decode().splitlines() == [str(DESIGN), *before["tests"]],
                "Exact717 membership/order differs")
        rows = read_csv(read(RUN / "commit_trace.csv"), COMMIT_FIELDS)
        vectors = read_csv(read(RUN / "vector_trace.csv"), VECTOR_FIELDS)
        console, vcslog = read(RUN / "console.log").decode(), read(RUN / "run.vcs.log").decode()
        tracer = read(RUN / "trace_hart_0.log").decode(); read(RUN / "trace_hart_0_commit.log")
        for path in sorted((RUN / "code.vdb").rglob("*")):
            if path.is_file(): read(path)
        control = lifecycle(rows, vectors, pre["symbols"])
        data = observed(rows, pre["symbols"])
        trap = tracer_exact(tracer, rows, pre["symbols"])
        contract = re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)', console)
        require(len(contract) == 1 and tuple(map(int, contract[0])) ==
                (control["requests"], control["responses"], 1, 0, 0) and
                not check_contract_log(RUN / "run.vcs.log"), "Contract/conservation differs")
        require(vcslog.count("Core Test *** SUCCESS ***") == 1, "Software completion marker missing")
        scalar = spike_trace.compare_commit_prefix(runner.PRE / "spike.trace", RUN / "commit_trace.csv",
                    0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout="unshifted")
        scalar_exact(scalar, plan["reference_counts"])
        reference = software.parse_spike_commits(runner.PRE / "spike.trace")
        vector = compare_vector_commits(runner.PRE / "spike.trace", RUN / "commit_trace.csv",
                                        RUN / "vector_trace.csv", 0x80000000)
        vector_exact(vector, control["exception_arch_seq"], reference)
        life.check(pins)
        with (out / "diagnostic-inputs.txt").open("x") as stream:
            stream.write(str(DESIGN) + "\n" + str(RUN / "code.vdb") + "\n")
        single = bitmap.collect(out / "diagnostic-inputs.txt")
        hits = target_hits(before, single, pre["targets"])
        proposed = bitmap.combine(before, single); delta = bitmap.delta(before, proposed)
        life.check(pins)
        for name, value in [("scalar-comparison.json", scalar), ("vector-comparison.json", vector),
                            ("observed-signatures.json", data), ("lifecycle.json", control),
                            ("trap-proof.json", trap), ("single-raw-bits.json", single),
                            ("raw-union.proposed.json", proposed), ("raw-bitmap-delta.json", delta),
                            ("target-hits.json", hits), ("evidence-pins.json", pins)]:
            life.save(out / name, value)
        outputs = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        life.save(out / "status.json", dict(status="OPIVX_VSBC_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED",
            baseline_tests=717, candidate_tests=1, new_admitted=0, raw_delta=delta["metrics"],
            pins=life.merge_pins(pins, outputs), coverage_admitted=False, aggregate_admission=False,
            official_DVE_report=False, rtl_changed=False, simulations_started=False))
        print(json.dumps(dict(output=str(out), status="STRICT_CANDIDATE_NOT_ADMITTED",
                              seal=life.digest(out / "status.json"), raw_delta=delta["metrics"])))
    except Exception as error:
        # Preserve every available terminal artifact, including failed runs.
        for name in ("manifest.json", "console.log", "run.vcs.log", "commit_trace.csv", "vector_trace.csv",
                     "trace_hart_0.log", "trace_hart_0_commit.log", "simulation-status.json"):
            path = RUN / name
            if path.is_file(): pins[str(path)] = life.digest(path)
        pin_error = None
        try: life.check(pins)
        except Exception as drift: pin_error = str(drift)
        life.save(out / "failure.json", dict(status="STRICT_AUDIT_FAIL_NOT_ADMITTED", reason=str(error),
                    pin_error=pin_error, pins=pins, coverage_admitted=False, rtl_changed=False,
                    simulations_started=False, retry_performed=False))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("prepare", "verify", "collect"))
    p.add_argument("--output", type=Path)
    p.add_argument("--plan", type=Path)
    p.add_argument("--seal")
    a = p.parse_args()
    if a.mode == "prepare":
        require(a.output and not a.plan and not a.seal, "Prepare arguments")
        prepare(a.output.absolute())
    else:
        require(a.plan and a.seal, "Sealed plan required")
        if a.mode == "verify":
            require(not a.output, "Verify is read-only")
            plan = life.read_bound(a.plan, a.seal); life.check(plan["pins"])
            print("VERIFY_PASS strict collector pins; NOT_EXECUTED_NOT_ADMITTED")
        else:
            require(a.output is not None, "Fresh collector output required")
            collect(a.plan.absolute(), a.seal, a.output.absolute())


if __name__ == "__main__":
    main()
