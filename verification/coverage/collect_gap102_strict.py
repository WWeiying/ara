"""Terminal GAP102 offline audit only; no simulation, admission, or retry."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re
import sys

import run_gap102_simulation as runner
import coverage_bitmap_delta as bitmap
from seal_gap101_failure import scalar_store
from ara_verify import spike_trace
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log

life, proof = runner.life, runner.proof
require = proof.require
RUN = life.OUT / "gap102-widen-acc-cross-old-image-20261006-02"
PREPARED_SEAL = "7c9aed3b60eb2249e8555547bc81ac7d7b3b2e647fdbb4a01b35483aab6b4280"
SCALAR_COUNTS = dict(matched_instructions=101339,matched_scalar_writes=74174,
                     matched_floating_writes=0,matched_scalar_memory_accesses=2495)


def reference_counts(commits, symbols):
    prefix = []
    for item in commits:
        if not prefix and item.pc != 0x80000000:
            continue
        prefix.append(item)
        if (symbols["tohost"], 1) in item.memory_accesses:
            break
    require(prefix and prefix[0].pc == 0x80000000 and
            prefix[-1].memory_accesses == ((symbols["tohost"], 1),), "Reference terminal missing")
    return dict(matched_instructions=len(prefix),
                matched_scalar_writes=sum(len({r:v for r,v in c.gpr_writes.items() if r}) for c in prefix),
                matched_floating_writes=sum(len(c.fpr_writes) for c in prefix),
                matched_scalar_memory_accesses=sum(bool(c.memory_accesses) and
                    spike_trace._scalar_memory_access(c.instruction) is not None for c in prefix))


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
                "Complete exact scalar contract differs: " + key)
    terminal = result.get("terminal_tohost")
    require(isinstance(terminal, dict) and terminal.get("address") == "0x0000000080001000" and
            terminal.get("write_value") == "0x1", "Scalar terminal differs")


def vector_exact(result):
    fixed = dict(status="PASS", compared_instructions=35, compared_bytes=6144,
        skipped_unknown_bytes=0, non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024,
        selected_index=None, stopped_at_spike_index=None, trapped_requests=[])
    for key, value in fixed.items():
        require(key in result and type(result[key]) is type(value) and result[key] == value,
                "Full exact vector contract differs: " + key)
    require(all(k in result and not result[k] for k in ("incomplete_requests", "unretired_requests")),
            "Incomplete/unretired vector activity")


def lifecycle(rows, vectors, symbols):
    starts, pending, requests, replies = {}, {}, [], []
    allocations, completions, retired = Counter(), Counter(), []
    for row in rows:
        event, tid, seq = row["event"], int(row["trans_id"]), int(row["order"])
        if event == "arch_start":
            require(seq not in starts and tid not in pending, "Duplicate start/live transaction")
            starts[seq], pending[tid] = row, [seq, False]
        elif event == "cvx_req":
            require(tid in pending and not pending[tid][1], "Unknown/duplicate request")
            arch = pending[tid][0]
            require(row["insn"] == starts[arch]["insn"], "Request opcode differs")
            pending[tid][1] = True
            requests.append(arch)
        elif event == "cvx_resp":
            require(tid in pending and pending[tid][1] and not int(row["trap"]), "Unknown/exception response")
            replies.append(pending.pop(tid)[0])
        elif event in ("uop_alloc", "uop_done"):
            require(seq in starts, "Unowned backend activity")
            (allocations if event == "uop_alloc" else completions)[seq, int(row["port"])] += 1
        else:
            require(event == "retire" and not int(row["trap"]), "Unknown event/trap")
            retired.append(row)
    require(not pending and Counter(requests) == Counter(starts.keys()) == Counter(replies),
            "Request/response conservation differs")
    require(allocations == completions, "Incomplete backend activity")
    va, vd = Counter(), Counter()
    for row in vectors:
        event, seq = row["event"], int(row["arch_seq"])
        if event == "config":
            continue
        require(seq in starts and event in ("alloc", "done", "write"), "Unowned/unknown vector activity")
        if event in ("alloc", "done"):
            (va if event == "alloc" else vd)[seq, int(row["vid"])] += 1
    require(va == vd == allocations, "Commit/vector lifecycle differs")
    # This frozen monitor records PC only on retire, not CVXIF arch_start.
    mac = [seq for seq,row in starts.items() if int(row["insn"],16) == proof.WORD]
    mac_retired = [row for row in retired if int(row["insn"],16) == proof.WORD]
    require(len(mac) == len(mac_retired) == 1 and
            int(mac_retired[0]["pc"],16) == symbols["g102_mac"] and
            int(starts[mac[0]]["cycle"]) <= int(mac_retired[0]["cycle"]) and
            any(seq == mac[0] for seq,_ in allocations), "MAC missing/duplicate/unexecuted")
    return dict(requests=len(requests), responses=len(replies), exceptions=0,
                backend_uops=sum(allocations.values()), mac_arch_seq=mac[0])


def observed(rows, symbols):
    retired = [r for r in rows if r["event"] == "retire"]
    require([int(r["order"]) for r in retired] == list(range(len(retired))), "Retirement prefix incomplete")
    memory = {}
    for row in retired:
        require(not int(row["trap"]) and int(row["pc"],16) != symbols["trap_fail"], "Unexpected trap")
        store = scalar_store(row)
        if store:
            address, data = store
            memory.update({address+i:value for i,value in enumerate(data)})
    def value(name, offset=0, size=8):
        address = symbols[name]+offset
        require(all(address+i in memory for i in range(size)), "Unobserved byte: " + name)
        return int.from_bytes(bytes(memory[address+i] for i in range(size)), "little")
    for (name,offset), expected in proof.expected_words().items():
        require(value(name,offset) == expected, "Independent VRF/CSR/guard/recovery mismatch: %s+%d" % (name,offset))
    require([value("g75_trap",i*8) for i in range(3)] == [0,0,0], "Trap ledger differs")
    require(value("g75_result",size=4) == 723 and value("g75_result",4,4) ==
            value("num_failed",size=4) == 0 and value("tohost") == 1, "723 checks failed")
    terminal = [r for r in retired if int(r["mem_addr"],16) == symbols["tohost"] and int(r["mem_wmask"],16)]
    require(len(terminal) == 1 and terminal[0] == retired[-1], "Missing/duplicate/post-terminal retire")
    return dict(checks=723, failed_checks=0, full_vrf_bytes=4096, source_guard_bytes=1536,
                csr_snapshots=2, recovery_guard_bytes=64, illegal_traps=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-seal", required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args(argv)
    require(args.prepared_seal == PREPARED_SEAL, "Only parent-reviewed GAP102 attempt02 seal allowed")
    out = args.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), "Fresh direct candidate output required")
    out.mkdir()
    pins = {}
    def read(path, expected=None):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(), "Aliased input")
        raw = path.read_bytes()
        import hashlib
        digest = hashlib.sha256(raw).hexdigest()
        require(expected is None or digest == expected, "Expected input hash differs: " + str(path))
        pins.update(life.merge_pins(pins,{str(path):digest}))
        return raw
    try:
        prepared = json.loads(read(RUN.with_name(RUN.name+".prepared.json"),args.prepared_seal))
        runtime = json.loads(read(RUN/"manifest.json"))
        require(runtime == prepared and runtime["case"] == runner.NAME and
                runtime["command"] == runner.command(RUN) and runtime["timeout_s"] == 600 and
                runtime["old_image_files_checked"] == 66 and runtime["baseline_tests"] == 717,
                "Exact frozen run contract differs")
        runner.validate(runtime["preflight"])
        pins.update(life.merge_pins(pins,runtime["pins"]))
        life.check(pins)
        state = json.loads(read(RUN/"simulation-status.json"))
        require(state["status"] == "SIMULATION_EXITED_NOT_ADMITTED" and state["returncode"] == 0 and
                state["case"] == runner.NAME and state["coverage_admitted"] is False, "Not terminal SUCCESS")
        pre = runtime["preflight"]
        commits = proof.s.parse_spike_commits(runner.PRE/"spike.trace")
        require(proof.validate(commits,pre["symbols"],read(runner.PRE/"spike.trace").decode()) == pre["validation"],
                "Sealed reference differs")
        rows = list(csv.DictReader(io.StringIO(read(RUN/"commit_trace.csv").decode())))
        vectors = list(csv.DictReader(io.StringIO(read(RUN/"vector_trace.csv").decode())))
        console, vcslog, tracer = [read(RUN/name).decode() for name in ("console.log","run.vcs.log","trace_hart_0.log")]
        require("Exception @" not in tracer, "Independent tracer exception")
        pattern = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
        actual = [m.groups() for line in tracer.splitlines() if (m := pattern.match(line))]
        retired = [r for r in rows if r["event"] == "retire"]
        expected = [(str(int(r["cycle"])),"M",r["pc"],r["insn"]) for r in retired]
        require(expected and actual[:len(expected)] == expected, "Tracer prefix differs")
        tail = actual[len(expected):]
        require(not tail or tail == [(expected[-1][0],"M","%016x" % (int(expected[-1][2],16)+4),"0000a001")], "Unknown tracer tail")
        control, data = lifecycle(rows,vectors,pre["symbols"]), observed(rows,pre["symbols"])
        contract = re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',console)
        require(len(contract) == 1 and tuple(map(int,contract[0])) ==
                (control["requests"],control["responses"],0,0,0) and not check_contract_log(RUN/"run.vcs.log") and
                vcslog.count("Core Test *** SUCCESS ***") == 1, "Contract/software SUCCESS differs")
        scalar = spike_trace.compare_commit_prefix(runner.PRE/"spike.trace",RUN/"commit_trace.csv",0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout="unshifted")
        life.save(out/"scalar-comparison.json",scalar)
        counts = reference_counts(commits,pre["symbols"])
        require(counts == SCALAR_COUNTS, "Sealed independent reference scalar counts differ")
        scalar_exact(scalar,counts)
        vector = compare_vector_commits(runner.PRE/"spike.trace",RUN/"commit_trace.csv",RUN/"vector_trace.csv",0x80000000)
        life.save(out/"vector-comparison.json",vector)
        vector_exact(vector)
        life.save(out/"observed-data.json",data)
        life.save(out/"lifecycle.json",control)
        targets = json.loads(read(runner.PRE/"target-before.json"))
        runner.validate_targets(targets)
        before = json.loads(read(proof.BASE/"combined-bits.json"))
        admission = json.loads(read(proof.BASE/"admission-manifest.json",proof.BASE_SEAL))
        require(pins[str(proof.BASE/"combined-bits.json")] == admission["output_pins"][str(proof.BASE/"combined-bits.json")]
                and len(before["tests"]) == len(set(before["tests"])) == 717 and
                read(proof.BASE/"combined-inputs.txt").decode().splitlines() == [str(proof.old.BUILD/"sim/simv.vdb"),*before["tests"]],
                "Frozen717 membership differs")
        for path in sorted((RUN/"code.vdb").rglob("*")):
            if path.is_file(): read(path)
        for path in (Path(__file__).resolve(),Path(__file__).with_name("test_collect_gap102_strict.py"),
                     Path(bitmap.__file__).resolve(),Path(scalar_store.__code__.co_filename).resolve(),
                     *sorted((proof.ROOT/"verification/ara_verify").glob("*.py"))): read(path)
        for module in tuple(sys.modules.values()):
            filename = getattr(module,"__file__",None)
            if filename and str(proof.ROOT/"verification") in filename:
                read(Path(filename).resolve())
        life.check(pins)
        (out/"diagnostic-inputs.txt").write_text(str(proof.old.BUILD/"sim/simv.vdb")+"\n"+str(RUN/"code.vdb")+"\n")
        single = bitmap.collect(out/"diagnostic-inputs.txt")
        require(single["tests"] == [str(RUN/"code.vdb")] and str(RUN/"code.vdb") not in before["tests"], "Wrong/duplicate VDB")
        proposed = bitmap.combine(before,single)
        delta = bitmap.delta(before,proposed)
        for name,obj in (("single-raw-bits.json",single),("raw-union.proposed.json",proposed),
                         ("raw-bitmap-delta.json",delta)):
            life.save(out/name,obj)
        hits = []
        for target in targets["targets"]:
            scope, metric, index = target["scope"],target["metric"],target["point"]["raw_index"]
            old, new = before["metrics"][metric][scope],single["metrics"][metric][scope]
            require((old["width"],old["checksum"]) == (target["width"],target["checksum"]) ==
                    (new["width"],new["checksum"]), "Target shape differs")
            bit = 1 << (old["width"]-1-index)
            require(not int(old["bits"],16)&bit and int(new["bits"],16)&bit, "Target not incremented; not an admitted coverage gain")
            hits.append(dict(scope=scope,metric=metric,raw_index=index,hit_before=False,hit_single=True))
        life.check(pins)
        for name,obj in (("target-hits.json",hits),
            ("evidence-pins.json",pins)):
            life.save(out/name,obj)
        life.save(out/"status.json",dict(status="GAP102_STRICT_CANDIDATE_NOT_ADMITTED",baseline_tests=717,
            coverage_admitted=False,aggregate_admission=False,rtl_changed=False,simulations_started=False,
            official_DVE_report=False,raw_delta=delta["metrics"]))
    except Exception as error:
        if not (out/"evidence-pins.json").exists():
            life.save(out/"evidence-pins.json",pins)
        life.save(out/"failure.json",dict(status="GAP102_COLLECTOR_REJECTED_NOT_ADMITTED",reason=str(error),
                                        coverage_admitted=False,simulations_started=False))
        raise


if __name__ == "__main__":
    main()
