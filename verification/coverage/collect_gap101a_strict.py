"""One terminal GAP101A offline candidate audit; no admission, EDA, or rerun."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re

import build_gap101a_preflight as software
import run_gap101a_simulation as runner
from seal_gap101_failure import scalar_store
import coverage_bitmap_delta as bitmap
from ara_verify.spike_trace import compare_commit_prefix
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log

ROOT, OUT, require = software.ROOT, software.OUT, software.require
RUN = OUT / "gap101a-nf-emul-only-old-image-715-20261006-01"
PREPARED_SEAL = "8446a01850f62b32efa73fbb2673bb4aadcecba020724afccffc88b85526eed3"
BASE = software.original.BASE
DESIGN = software.original.BUILD / "sim/simv.vdb"


def lifecycle(rows, vectors):
    starts, pending, requests, replies = {}, {}, [], []
    allocations, completions = Counter(), Counter()
    rejected = []
    for row in rows:
        event, tid, seq = row["event"], int(row["trans_id"]), int(row["order"])
        insn = int(row["insn"], 16)
        require(insn != 0x22050fa7, "Original failing phase present")
        if event == "arch_start":
            require(seq not in starts and tid not in pending, "Duplicate start/live transaction")
            starts[seq] = row
            pending[tid] = [seq, False]
        elif event == "cvx_req":
            require(tid in pending and not pending[tid][1], "Unknown/duplicate CVX request")
            arch = pending[tid][0]
            require(insn == int(starts[arch]["insn"], 16), "CVX instruction identity differs")
            pending[tid][1] = True
            requests.append(arch)
        elif event == "cvx_resp":
            require(tid in pending and pending[tid][1], "Unknown/duplicate CVX response")
            arch, _ = pending.pop(tid)
            replies.append(arch)
            if int(row["trap"]): rejected.append(arch)
        elif event in ("uop_alloc", "uop_done"):
            require(seq in starts, "Unowned uop")
            (allocations if event == "uop_alloc" else completions)[(seq, int(row["port"]))] += 1
        else:
            require(event == "retire", "Unknown architectural trace event")
    require(not pending and Counter(requests) == Counter(starts.keys()) == Counter(replies), "CVX conservation differs")
    require(allocations == completions, "Incomplete uops")
    bad = [seq for seq, row in starts.items() if int(row["insn"], 16) == 0xe2050827]
    require(len(bad) == 1 and rejected == bad, "Rejected NF request/exception population differs")
    require(not any(seq == bad[0] for seq, _ in allocations), "Rejected instruction allocated backend uop")
    va, vd = Counter(), Counter()
    for row in vectors:
        event, seq = row["event"], int(row["arch_seq"])
        if event == "config": continue
        require(seq in starts and seq != bad[0], "Unowned/rejected vector activity")
        require(event in ("alloc", "done", "write"), "Unknown vector event")
        if event in ("alloc", "done"):
            (va if event == "alloc" else vd)[(seq, int(row["vid"]))] += 1
    require(va == vd == allocations, "Commit/vector uop lifecycle differs")
    return dict(requests=len(requests), responses=len(replies), exception_arch_seq=bad[0],
                backend_uops=sum(allocations.values()), rejected_backend_uops=0,
                rejected_vrf_activities=0)


def observed(rows, symbols):
    retired = [r for r in rows if r["event"] == "retire"]
    require([int(r["order"]) for r in retired] == list(range(len(retired))), "Retirement prefix incomplete")
    require(not any(int(r["pc"], 16) == symbols["g101a_bad_a"] for r in retired), "Rejected instruction retired")
    require(not any(int(r["trap"]) for r in retired), "Unexpected RVFI trap row")
    memory = {}
    for row in retired:
        store = scalar_store(row)
        if store:
            address, data = store
            memory.update({address+i: value for i, value in enumerate(data)})
    def value(name, offset=0, size=8):
        address = symbols[name] + offset
        require(all(address+i in memory for i in range(size)), "Unobserved bytes: " + name)
        return int.from_bytes(bytes(memory[address+i] for i in range(size)), "little")
    for (name, offset), expected in software.expected_words().items():
        require(value(name, offset) == expected, "VRF/target/guard/recovery mismatch: %s+%d" % (name, offset))
    ledger = [value("g101a_ledger", i*8) for i in range(8)]
    require(ledger == [2, symbols["g101a_bad_a"], 0xe2050827, 1, 1, 0, 0, 1], "Trap CSR ledger differs")
    restored = [value("g101a_restore", i*8) for i in range(4)]
    require(restored[0] == restored[1] and restored[2] == restored[3], "Trap CSR restore differs")
    require(value("g75_result", size=4) == 539 and value("g75_result", 4, 4) ==
            value("num_failed", size=4) == 0 and value("tohost") == 1, "539 checks/selfcheck failed")
    terminal = [r for r in retired if int(r["mem_addr"],16) == symbols["tohost"] and int(r["mem_wmask"],16)]
    require(len(terminal) == 1 and terminal[0] == retired[-1], "Missing/extra/post-terminal retire")
    return dict(checks=539, failed_checks=0, trap_ledger=ledger,
                unchanged_vrf_bytes=4096, target_guard_bytes=64, recovery_guard_bytes=64,
                complete_retirement_rows=len(retired), mtvec_mscratch_restored=True)


def vector_exact(result, rejected):
    require(result.get("status") == "PASS" and result.get("compared_instructions") == 32 and
            result.get("compared_bytes") == 4096 and result.get("skipped_unknown_bytes") == 0 and
            result.get("non_bit_exact_instructions") == 0 and result.get("nr_lanes") == 4 and
            result.get("vlen_bits") == 1024 and result.get("selected_index") is None and
            result.get("stopped_at_spike_index") is None and
            result.get("trapped_requests") == [rejected] and
            all(k in result and not result[k] for k in ("incomplete_requests", "unretired_requests")),
            "Full vector comparison differs")


def tracer_exact(text, rows, symbols):
    pattern = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    instructions = [m.groups() for line in text.splitlines() if (m := pattern.match(line))]
    retired = [r for r in rows if r["event"] == "retire"]
    expected = [(str(int(r["cycle"])), "M", r["pc"], r["insn"]) for r in retired]
    require(instructions[:len(expected)] == expected, "Independent tracer/retirement prefix differs")
    tail = instructions[len(expected):]
    require(not tail or tail == [(expected[-1][0], "M", "%016x" % (int(expected[-1][2],16)+4), "0000a001")],
            "Unknown tracer tail")
    events = re.findall(r'Exception @\s*(\d+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)', text)
    require(len(events) == text.count("Exception @") == 1 and events[0][2] == "Illegal Instruction" and
            int(events[0][1],16) == symbols["g101a_bad_a"] and
            re.findall(r'tval: ([0-9a-fA-F]+)', text) == ["00000000e2050827"], "Actual exception identity differs")
    return dict(exception_pc=hex(symbols["g101a_bad_a"]), cause=2, tval="0xe2050827", tracer_tail=tail)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    out = p.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    pins = {}
    def read(path, expected=None):
        path = Path(path).absolute()
        require(not path.is_symlink() and path.resolve() == path, "Aliased input")
        actual = runner.life.digest(path)
        require(expected is None or actual == expected, "Expected input pin differs: " + str(path))
        pins.update(runner.life.merge_pins(pins, {str(path): actual}))
        return path.read_bytes()
    prepared = json.loads(read(RUN.with_name(RUN.name + ".prepared.json"), PREPARED_SEAL))
    runtime = json.loads(read(RUN / "manifest.json"))
    require(runtime == prepared and runtime["case"] == runner.NAME and runtime["command"] == runner.command(RUN)
            and runtime["old_image_files_checked"] == 66 and runtime["timeout_s"] == 600, "Exact run contract differs")
    runner.validate(runtime["preflight"])
    pins.update(runner.life.merge_pins(pins, runtime["pins"]))
    runner.life.check(pins)
    state = json.loads(read(RUN / "simulation-status.json"))
    require(state["status"] == "SIMULATION_EXITED_NOT_ADMITTED" and state["returncode"] == 0 and
            state["case"] == runner.NAME and state["coverage_admitted"] is False, "Run not terminal successful")
    before = json.loads(read(BASE / "combined-bits.json"))
    old_status = json.loads(read(BASE / "status.json"))
    require(old_status["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and old_status["aggregate_passed"] ==
            len(before["tests"]) == len(set(before["tests"])) == 715 and
            all("gap101-illegal-segment-store-old-image" not in t for t in before["tests"]), "Wrong715 membership/FAIL mixed")
    require(read(BASE / "combined-inputs.txt").decode().splitlines() == [str(DESIGN), *before["tests"]], "715 order differs")
    rows = list(csv.DictReader(io.StringIO(read(RUN / "commit_trace.csv").decode())))
    vectors = list(csv.DictReader(io.StringIO(read(RUN / "vector_trace.csv").decode())))
    console = read(RUN / "console.log").decode()
    vcslog = read(RUN / "run.vcs.log").decode()
    text = read(RUN / "trace_hart_0.log").decode()
    for path in sorted((RUN / "code.vdb").rglob("*")):
        if path.is_file(): read(path)
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_collect_gap101a_strict.py"),
                 Path(bitmap.__file__).resolve(), ROOT / "verification/coverage/seal_gap101_failure.py",
                 ROOT / "verification/coverage/check_gap100_runtime.py",
                 *sorted((ROOT / "verification/ara_verify").glob("*.py"))): read(path)
    targets = json.loads(read(runner.PRE / "target-before.json"))
    runner.validate_targets(targets)
    control = lifecycle(rows, vectors)
    data = observed(rows, runtime["preflight"]["symbols"])
    trap = tracer_exact(text, rows, runtime["preflight"]["symbols"])
    contract = re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)', console)
    require(len(contract) == 1 and tuple(map(int, contract[0])) ==
            (control["requests"], control["responses"], 1, 0, 0) and not check_contract_log(RUN / "run.vcs.log"),
            "Full contract/conservation differs")
    require(vcslog.count("Core Test *** SUCCESS ***") == 1, "Software SUCCESS marker missing")
    scalar = compare_commit_prefix(runner.PRE / "spike.trace", RUN / "commit_trace.csv", 0x80000000,
                                  terminal_tohost_address=0x80001000, rvfi_store_data_layout="unshifted")
    require(scalar["status"] == "TERMINAL_TOHOST_MATCH" and scalar["ara_trap_events"] == 0 and
            scalar["mismatch"] is None, "Complete architecture comparison differs")
    vector = compare_vector_commits(runner.PRE / "spike.trace", RUN / "commit_trace.csv",
                                   RUN / "vector_trace.csv", 0x80000000)
    vector_exact(vector, control["exception_arch_seq"])
    runner.life.check(pins)
    require(out.parent == OUT and not out.exists(), "Output changed")
    out.mkdir()
    try:
        with (out / "diagnostic-inputs.txt").open("x") as stream:
            stream.write(str(DESIGN)+"\n"+str(RUN / "code.vdb")+"\n")
        single = bitmap.collect(out / "diagnostic-inputs.txt")
        require(single["tests"] == [str(RUN / "code.vdb")] and str(RUN / "code.vdb") not in before["tests"], "Duplicate/wrong new VDB")
        proposed = bitmap.combine(before, single)
        delta = bitmap.delta(before, proposed)
        hits = []
        for row in targets["targets"]:
            metric, scope, index = row["metric"], row["scope"], row["point"]["raw_index"]
            old, new = before["metrics"][metric][scope], single["metrics"][metric][scope]
            require((old["width"],old["checksum"]) == (row["width"],row["checksum"]) ==
                    (new["width"],new["checksum"]), "Target shape differs")
            bit = 1 << (old["width"]-1-index)
            require(not int(old["bits"],16)&bit and int(new["bits"],16)&bit, "Target not incremented")
            hits.append(dict(metric=metric, scope=scope, raw_index=index, hit_before=False, hit_single=True))
        runner.life.check(pins)
        for name, obj in [("scalar-comparison.json",scalar),("vector-comparison.json",vector),
                          ("trap-ledger.json",trap),("observed-data.json",data),("lifecycle.json",control),
                          ("single-raw-bits.json",single),("raw-union.proposed.json",proposed),
                          ("raw-bitmap-delta.json",delta),("target-hits.json",hits),("evidence-pins.json",pins)]:
            runner.life.save(out/name,obj)
        runner.life.save(out / "status.json",dict(status="GAP101A_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED",
            baseline_tests=715, candidate_tests=1, new_admitted=0, original_gap101_fail_excluded=True,
            coverage_admitted=False, aggregate_admission=False, official_DVE_report=False,
            rtl_changed=False, simulations_started=False, raw_delta=delta["metrics"]))
        print(json.dumps(dict(output=str(out), status="GAP101A_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED",
                              seal=runner.life.digest(out / "status.json"), raw_delta=delta["metrics"])))
    except Exception as error:
        runner.life.save(out / "failure.json",dict(status="GAP101A_COLLECTOR_REJECTED_NOT_ADMITTED",reason=str(error)))
        raise


if __name__ == "__main__": main()
