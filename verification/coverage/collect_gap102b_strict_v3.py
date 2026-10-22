"""Terminal GAP102B strict architecture and measured raw127 audit; no admission."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re
import sys

import run_gap102b_simulation as runner
import coverage_bitmap_delta as bitmap
from seal_gap101_failure import scalar_store
from ara_verify import spike_trace
from ara_verify.vector_commit import compare_vector_commits, VectorWrite, _architectural_bytes, _write_data
from ara_verify.contract import check_contract_log

life, proof = runner.life, runner.proof
require = proof.require
BASE, DESIGN = proof.frozen.BASE, proof.frozen.old.BUILD / "sim/simv.vdb"
RUN = life.OUT / "gap102b-widen-acc-vstart-old-image-717-20261006-01"
PREPARED_SEAL = "767835e44c1c2f952645f2e12045defad1ce20d77e6fa346d593acdd5cfcbd59"
MAC_PC = 0x80002234
SCALAR_COUNTS = dict(matched_instructions=35366,matched_scalar_writes=25488,
                     matched_floating_writes=0,matched_scalar_memory_accesses=3519)


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


def vector_exact(result, audit):
    require(audit["status"] == "ALL_GRANTED_BYTES_EXACT" and audit["uop_unique_bytes"] == 5382 and
            audit["activity_unique_bytes"] == 5380 and audit["unknown_bytes"] == 0,
            "Independent physical byte audit missing")
    fixed = dict(status="PASS", compared_instructions=35, compared_bytes=4096+1024+128+4,
        skipped_unknown_bytes=128, non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024,
        selected_index=None, stopped_at_spike_index=None, trapped_requests=[])
    for key, value in fixed.items():
        require(key in result and type(result[key]) is type(value) and result[key] == value,
                "Full exact vector contract differs: " + key)
    require(all(k in result and not result[k] for k in ("incomplete_requests", "unretired_requests")),
            "Incomplete/unretired vector activity")
    records = result.get("instructions", [])
    require(len(records) == 35, "Missing per-instruction vector evidence")
    for index, record in enumerate(records):
        opcode = (0x5e02c057 | (index << 7)) if index < 32 else (0x02066407,0x0206d607,proof.WORD)[index-32]
        expected_bytes = 128 if index < 32 else (1024,128,4)[index-32]
        require(record.get("instruction") == "0x%08x" % opcode and
                record.get("status") == "PASS" and record.get("compared_bytes") == expected_bytes and
                record.get("skipped_unknown_bytes") == (128 if index == 34 else 0) and
                record.get("unknown_write_bytes") == 0 and record.get("mismatch_count") == 0 and
                record.get("first_mismatch") is None and
                record.get("uops") == (2 if index >= 33 else 1),
                "Per-instruction exact/preservation contract differs")
    require(records[-1].get("pc") == "0x%016x" % MAC_PC and
            records[-1].get("write_events") == 81, "MAC preservation record identity differs")


def lifecycle(rows, vectors, symbols):
    starts, pending, requests, replies = {}, {}, [], []
    allocations, completions, retired = Counter(), Counter(), []
    pending_uops = {}
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
            require(int(row["insn"],16) == 0 and int(row["pc"],16) == 0 and seq == -1,
                    "Frozen CVX response placeholder format differs")
            replies.append(pending.pop(tid)[0])
        elif event in ("uop_alloc", "uop_done"):
            require(seq in starts, "Unowned backend activity")
            key = (seq,int(row["port"]))
            require(int(row["insn"],16) == int(starts[seq]["insn"],16) and
                    int(row["cycle"]) >= int(starts[seq]["cycle"]), "Backend identity/time differs")
            if event == "uop_alloc":
                require(key not in pending_uops, "Backend VID reused before done")
                pending_uops[key] = row
                allocations[key] += 1
            else:
                require(key in pending_uops and int(row["cycle"]) >= int(pending_uops[key]["cycle"]),
                        "Unknown/premature backend completion")
                pending_uops.pop(key)
                completions[key] += 1
        else:
            require(event == "retire" and not int(row["trap"]), "Unknown event/trap")
            retired.append(row)
    require(not pending and Counter(requests) == Counter(starts.keys()) == Counter(replies),
            "Request/response conservation differs")
    require(not pending_uops and allocations == completions, "Incomplete backend activity")
    va, vd = Counter(), Counter()
    vector_pending, vector_last_done = {}, {}
    original_mac = []
    for row in vectors:
        event, seq = row["event"], int(row["arch_seq"])
        if event == "config":
            continue
        require(seq in starts and event in ("alloc", "done", "write"), "Unowned/unknown vector activity")
        require(int(row["insn"],16) == int(starts[seq]["insn"],16) and
                int(row["nr_lanes"]) == 4 and int(row["vlen_bits"]) == 1024,
                "Vector architectural identity/configuration differs")
        if event in ("alloc", "done"):
            key = (seq,int(row["vid"]))
            if event == "alloc":
                require(key not in vector_pending, "Vector VID reused before done")
                vector_pending[key] = row
                va[key] += 1
                if int(row["insn"],16) == proof.WORD and tuple(int(row[k]) for k in
                        ("use_vd","vd","eew","vl","vstart")) == (1,8,2,129,128):
                    original_mac.append(row)
            else:
                require(key in vector_pending, "Unallocated vector completion")
                alloc = vector_pending.pop(key)
                require(int(row["cycle"]) >= int(alloc["cycle"]) and all(row[k] == alloc[k] for k in
                        ("insn","use_vd","vd","eew","vl","vstart")), "Vector completion metadata/time differs")
                vector_last_done[key] = row
                vd[key] += 1
        else:
            key = (seq,int(row["vid"]))
            alloc = vector_pending.get(key)
            if alloc is None:
                done = vector_last_done.get(key)
                require(done is not None and int(done["cycle"]) == int(row["cycle"]),
                        "Write outside allocated/completing uop")
                alloc = done
            require(int(row["cycle"]) >= int(alloc["cycle"]) and all(row[k] == alloc[k] for k in
                    ("insn","use_vd","vd","eew","vl","vstart")), "Vector write metadata/time differs")
    require(not vector_pending and va == vd == allocations, "Commit/vector lifecycle differs")
    # This frozen monitor records PC only on retire, not CVXIF arch_start.
    mac = [seq for seq,row in starts.items() if int(row["insn"],16) == proof.WORD]
    mac_retired = [row for row in retired if int(row["insn"],16) == proof.WORD]
    require(symbols["g102b_mac"] == MAC_PC and len(mac) == len(mac_retired) == 1 and
            int(mac_retired[0]["pc"],16) == symbols["g102b_mac"] and
            int(starts[mac[0]]["cycle"]) <= int(mac_retired[0]["cycle"]) and
            len(original_mac) == 1 and int(original_mac[0]["arch_seq"]) == mac[0] and
            int(starts[mac[0]]["cycle"]) <= int(original_mac[0]["cycle"]) <= int(mac_retired[0]["cycle"]) and
            any(seq == mac[0] for seq,_ in allocations), "MAC missing/duplicate/unexecuted")
    return dict(requests=len(requests), responses=len(replies), exceptions=0,
                backend_uops=sum(allocations.values()), mac_arch_seq=mac[0],
                mac_retire_pc=hex(symbols["g102b_mac"]), mac_retire_order=int(mac_retired[0]["order"]),
                mac_retire_cycle=int(mac_retired[0]["cycle"]), original_mac_allocation=original_mac[0],
                original_mac_vstart=128, response_opcode_is_fixed_zero_not_identity=True, internal_state_sampled=False)


def measure_targets(before, single, targets):
    runner.validate_targets(targets)
    hits = []
    for target in targets["targets"]:
        scope, metric, index = target["scope"],target["metric"],target["point"]["raw_index"]
        old,new = before["metrics"][metric][scope],single["metrics"][metric][scope]
        require((old["width"],old["checksum"]) == (target["width"],target["checksum"]) ==
                (new["width"],new["checksum"]), "Target shape differs")
        bit = 1 << (old["width"]-1-index)
        require(not int(old["bits"],16)&bit,"Target was not zero in baseline")
        hits.append(dict(scope=scope,metric=metric,raw_index=index,hit_before=False,
                         hit_single=bool(int(new["bits"],16)&bit)))
    return hits


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


def transport_exact(rows):
    from build_gap102b_preflight_v2 import images
    data = images()
    require(data["before"][14*128:15*128] == data["after"][14*128:15*128],
            "MAC maintenance preimage is not preserved")
    initial = b"".join(bytes([0x40+r])*128 for r in range(32))
    pending, stage_counts, activity_bytes = {}, Counter(), {}
    uop_bytes, granted_bytes = 0, 0
    def keys(regs):
        return {(r,b) for r in regs for b in range(128)}
    for row in rows:
        event = row["event"]
        if event == "config":
            continue
        key = (int(row["arch_seq"]),int(row["vid"]))
        if event == "alloc":
            require(key not in pending,"Duplicate transport allocation")
            insn = int(row["insn"],16)
            cfg = tuple(int(row[k]) for k in ("use_vd","vd","eew","vl","vstart"))
            rd = (insn>>7)&31
            if insn == (0x5e02c057 | (rd<<7)) and cfg == (1,rd,0,128,0):
                stage, image, expected = "init%d"%rd, initial, keys([rd])
            elif insn == 0x02066407 and cfg == (1,8,2,256,0):
                stage, image, expected = "seed", data["seeded"], keys(range(8,16))
            elif insn == 0x0206d607 and cfg == (1,14,1,64,0):
                stage, image, expected = "source_reshape", data["seeded"], keys([14])
            elif insn == 0x0206d607 and cfg == (1,12,1,129,128):
                stage, image, expected = "source_active", data["before"], {(14,0),(14,1)}
            elif insn == proof.WORD and cfg == (1,8,2,129,128):
                stage, image, expected = "mac_active", data["after"], {(12,b) for b in range(4)}
            elif insn == proof.WORD and cfg == (1,14,2,32,0):
                stage, image, expected = "mac_preservation", data["after"], keys([14])
            else:
                require((insn & 0x7f) == 0x27 and cfg[0] == 0,"Unexpected transport stage")
                stage, image, expected = "store", data["after"], set()
            pending[key] = dict(stage=stage,image=image,expected=expected,seen=set(),row=row)
            if stage != "store":
                stage_counts[stage] += 1
        elif event == "write":
            require(key in pending,"Unallocated transport write")
            item = pending[key]
            data_word, known = _write_data(row["wdata"])
            be = int(row["be"],16)
            require(0 <= be <= 255 and 0 <= int(row["lane"]) < 4 and be & ~known == 0,
                    "Unknown/invalid granted transport byte")
            write = VectorWrite(row=0,cycle=int(row["cycle"]),arch_seq=key[0],vid=key[1],
                lane=int(row["lane"]),source=int(row["source"]),instruction=int(row["insn"],16),
                eew=int(row["eew"]),addr=int(row["addr"]),be=be,data=data_word,known_be=known)
            mapped = _architectural_bytes([write],4,1024)
            for position,(value,_) in mapped.items():
                require(position in item["expected"],"Unexpected transport register/byte")
                reg, byte = position
                require(value is not None and value == item["image"][reg*128+byte],
                        "Transport preservation/active byte differs")
                item["seen"].add(position)
                activity_bytes.setdefault(key[0],set()).add(position)
                granted_bytes += 1
        elif event == "done":
            require(key in pending,"Unallocated transport done")
            item = pending.pop(key)
            require(item["seen"] == item["expected"],"Missing exact transport bytes")
            uop_bytes += len(item["seen"])
        else:
            require(False,"Unknown transport event")
    require(not pending and stage_counts == Counter(
        {"init%d"%r:1 for r in range(32)},seed=1,source_reshape=1,source_active=1,
        mac_active=1,mac_preservation=1),"Missing/duplicate exact transport stages")
    require(uop_bytes == 4096+1024+128+2+4+128,"Transport byte derivation differs")
    unique = sum(map(len,activity_bytes.values()))
    require(unique == 4096+1024+128+4+128,"Activity byte derivation differs")
    return dict(status="ALL_GRANTED_BYTES_EXACT",uop_unique_bytes=uop_bytes,
        activity_unique_bytes=unique,granted_byte_events=granted_bytes,unknown_bytes=0,
        stages=dict(stage_counts),shared_comparer_architectural_bytes=4096+1024+128+4,
        shared_comparer_preservation_bytes_independently_checked=128,
        spike_declared_bytes=4096+1024+128+256,source_active_overlap_bytes=2,
        preservation_register=14,preservation_eew=2,
        preservation_reason="v14 maintenance lies outside Spike destination declarations v10/v12",
        preimage_proven_by="seed writes plus two source-active bytes, every maintenance write checked",
        postimage_proven_by="all granted writes plus independent full4096-byte scalar snapshot")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-seal", required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args(argv)
    require(args.prepared_seal == PREPARED_SEAL, "Only parent-reviewed GAP102B prepared seal allowed")
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
        monitor = runner.life.ROOT/"hardware/tb/ara_commit_monitor.sv"
        monitor_text = read(monitor,"38b7642703c49e31fd0493b81e948388f2dbc72f97da418f3ed76e73bd42c782").decode()
        require("cvx_resp,-1,-1,%0d,0000000000000000,00000000" in monitor_text,
                "Frozen monitor response format differs")
        pre = runtime["preflight"]
        commits = proof.s.parse_spike_commits(Path(pre["input_spike_trace"]))
        require(proof.validate(commits,pre["symbols"],read(Path(pre["input_spike_trace"])).decode()) == pre["validation"],
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
        control = lifecycle(rows,vectors,pre["symbols"])
        life.save(out/"lifecycle.json",control)
        data = observed(rows,pre["symbols"])
        life.save(out/"observed-data.json",data)
        contract = re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',console)
        require(len(contract) == 1 and tuple(map(int,contract[0])) ==
                (control["requests"],control["responses"],0,0,0) and not check_contract_log(RUN/"run.vcs.log") and
                vcslog.count("Core Test *** SUCCESS ***") == 1, "Contract/software SUCCESS differs")
        scalar = spike_trace.compare_commit_prefix(Path(pre["input_spike_trace"]),RUN/"commit_trace.csv",0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout="unshifted")
        life.save(out/"scalar-comparison.json",scalar)
        counts = reference_counts(commits,pre["symbols"])
        require(counts == SCALAR_COUNTS, "Sealed independent reference scalar counts differ")
        scalar_exact(scalar,counts)
        vector = compare_vector_commits(Path(pre["input_spike_trace"]),RUN/"commit_trace.csv",RUN/"vector_trace.csv",0x80000000)
        life.save(out/"vector-comparison.json",vector)
        transport = transport_exact(vectors)
        life.save(out/"transport-byte-audit.json",transport)
        vector_exact(vector,transport)
        targets = json.loads(read(runner.PRE/"target-before.json"))
        runner.validate_targets(targets)
        before = json.loads(read(BASE/"combined-bits.json"))
        admission = json.loads(read(BASE/"admission-manifest.json",proof.frozen.BASE_SEAL))
        require(pins[str(BASE/"combined-bits.json")] == admission["output_pins"][str(BASE/"combined-bits.json")]
                and len(before["tests"]) == len(set(before["tests"])) == 717 and
                read(BASE/"combined-inputs.txt").decode().splitlines() == [str(DESIGN),*before["tests"]],
                "Frozen717 membership differs")
        for path in sorted((RUN/"code.vdb").rglob("*")):
            if path.is_file(): read(path)
        for path in (Path(__file__).resolve(),Path(__file__).with_name("test_collect_gap102b_strict_v3.py"),
                     Path(bitmap.__file__).resolve(),Path(scalar_store.__code__.co_filename).resolve(),
                     *sorted((proof.ROOT/"verification/ara_verify").glob("*.py"))): read(path)
        for module in tuple(sys.modules.values()):
            filename = getattr(module,"__file__",None)
            if filename and str(proof.ROOT/"verification") in filename:
                read(Path(filename).resolve())
        life.check(pins)
        (out/"diagnostic-inputs.txt").write_text(str(DESIGN)+"\n"+str(RUN/"code.vdb")+"\n")
        single = bitmap.collect(out/"diagnostic-inputs.txt")
        require(single["tests"] == [str(RUN/"code.vdb")] and str(RUN/"code.vdb") not in before["tests"], "Wrong/duplicate VDB")
        proposed = bitmap.combine(before,single)
        delta = bitmap.delta(before,proposed)
        for name,obj in (("single-raw-bits.json",single),("raw-union.proposed.json",proposed),
                         ("raw-bitmap-delta.json",delta)):
            life.save(out/name,obj)
        hits = measure_targets(before,single,targets)
        life.check(pins)
        for name,obj in (("target-hits.json",hits),
            ("evidence-pins.json",pins)):
            life.save(out/name,obj)
        qualified = all(row["hit_single"] for row in hits)
        life.save(out/"status.json",dict(status=("GAP102B_STRICT_V3_CANDIDATE_NOT_ADMITTED" if qualified else
            "GAP102B_STRICT_V3_ARCHITECTURE_PASS_TARGET_NOT_HIT_NOT_ADMITTED"),baseline_tests=717,
            architecture_oracle_pass=True, coverage_candidate_qualified=qualified, target_hit_verified=qualified,
            coverage_admitted=False,aggregate_admission=False,rtl_changed=False,simulations_started=False,
            official_DVE_report=False,raw_delta=delta["metrics"]))
    except Exception as error:
        if not (out/"evidence-pins.json").exists():
            life.save(out/"evidence-pins.json",pins)
        life.save(out/"failure.json",dict(status="GAP102B_V3_COLLECTOR_REJECTED_NOT_ADMITTED",reason=str(error),
                                        coverage_admitted=False,simulations_started=False))
        raise


if __name__ == "__main__":
    main()
