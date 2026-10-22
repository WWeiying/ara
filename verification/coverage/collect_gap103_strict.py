"""Terminal GAP103 strict architecture and measured raw138/105/100 and line202 audit; no admission."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re
import sys

import run_gap103_simulation as runner
import coverage_bitmap_delta as bitmap
from seal_gap101_failure import scalar_store
from ara_verify import spike_trace
from ara_verify.vector_commit import compare_vector_commits, VectorWrite, _architectural_bytes, _write_data
from ara_verify.contract import check_contract_log

life, proof = runner.life, runner.proof
require = proof.require
BASE, DESIGN = proof.BASE, proof.old.BUILD / "sim/simv.vdb"
RUN = life.OUT / "gap103-narrow-prefix-old-image-719-20261006-01"
PREPARED_SEAL = "47fa18201707989ec965570eec546cc7db18454e2ec182228f110b0f7c125edb"
NARROW_PC = 0x800023ac
SCALAR_COUNTS = dict(matched_instructions=110528,matched_scalar_writes=78456,
                     matched_floating_writes=0,matched_scalar_memory_accesses=4871)


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
    original_narrow = []
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
                        ("use_vd","vd","eew","vl","vstart")) == (1,8,1,129,13):
                    original_narrow.append(row)
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
    narrow = [seq for seq,row in starts.items() if int(row["insn"],16) == proof.WORD]
    narrow_retired = [row for row in retired if int(row["insn"],16) == proof.WORD]
    require(symbols["g103_narrow"] == NARROW_PC and len(narrow) == len(narrow_retired) == 1 and
            int(narrow_retired[0]["pc"],16) == symbols["g103_narrow"] and
            int(starts[narrow[0]]["cycle"]) <= int(narrow_retired[0]["cycle"]) and
            len(original_narrow) == 1 and int(original_narrow[0]["arch_seq"]) == narrow[0] and
            int(starts[narrow[0]]["cycle"]) <= int(original_narrow[0]["cycle"]) <= int(narrow_retired[0]["cycle"]) and
            any(seq == narrow[0] for seq,_ in allocations), "Narrow missing/duplicate/unexecuted")
    return dict(requests=len(requests), responses=len(replies), exceptions=0,
                backend_uops=sum(allocations.values()), narrow_arch_seq=narrow[0],
                narrow_retire_pc=hex(symbols["g103_narrow"]), narrow_retire_order=int(narrow_retired[0]["order"]),
                narrow_retire_cycle=int(narrow_retired[0]["cycle"]), original_narrow_allocation=original_narrow[0],
                original_narrow_vstart=13, response_opcode_is_fixed_zero_not_identity=True, internal_state_sampled=False)


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
    require(value("g75_result",size=4) == 1245 and value("g75_result",4,4) ==
            value("num_failed",size=4) == 0 and value("tohost") == 1, "1245 checks failed")
    terminal = [r for r in retired if int(r["mem_addr"],16) == symbols["tohost"] and int(r["mem_wmask"],16)]
    require(len(terminal) == 1 and terminal[0] == retired[-1], "Missing/duplicate/post-terminal retire")
    return dict(checks=1245, failed_checks=0, before_vrf_bytes=4096, after_vrf_bytes=4096, source_and_guard_bytes=1600,
                csr_snapshots=2, recovery_guard_bytes=64, illegal_traps=0)



def transport_exact(rows, commits):
    data = proof.images()
    initial = b"".join(bytes([0x40+r])*128 for r in range(32))
    refs = [c for c in commits if c.vector_writes]
    require(len(refs) == 35, "Exact reference vector population differs")
    pending, last_done, groups, stages = {}, {}, [], Counter()
    original_seen, original_done = set(), set()
    def keys(regs):
        return {(r,b) for r in regs for b in range(128)}
    def interval(base,start,end):
        return {(base+(i//128),i%128) for i in range(start,end)}
    for number,row in enumerate(rows):
        event = row["event"]
        require(int(row["nr_lanes"]) == 4 and int(row["vlen_bits"]) == 1024,
                "Transport configuration differs")
        if event == "config":
            continue
        key = (int(row["arch_seq"]),int(row["vid"]))
        if event == "alloc":
            require(key not in pending,"Duplicate transport allocation")
            insn = int(row["insn"],16)
            cfg = tuple(int(row[k]) for k in ("use_vd","vd","eew","vl","vstart"))
            rd = (insn>>7)&31
            required, allowed = set(), set()
            if insn == (0x5e02c057 | (rd<<7)) and cfg == (1,rd,0,128,0):
                stage, image = "init%d"%rd, initial
                required = allowed = keys([rd])
            elif insn & (0xffffffff ^ (31<<15)) == 0x02006407 and cfg == (1,8,2,256,0):
                stage, image = "seed", data["seeded"]
                required = allowed = keys(range(8,16))
            elif insn & (0xffffffff ^ (31<<15)) == 0x02005607 and cfg == (1,12,1,256,0):
                stage, image = "shift", data["before"]
                required = allowed = keys(range(12,16))
            elif insn == proof.WORD:
                seq = key[0]
                if cfg == (1,8,1,129,13):
                    require(seq not in original_seen,"Duplicate original narrow")
                    original_seen.add(seq)
                    stage, image = "narrow_active", data["after"]
                    required, allowed = interval(8,26,258), keys(range(8,12))
                elif cfg[0] == 1 and cfg[1] in range(8,13) and cfg[2:] == (2,32,0):
                    require(seq not in original_seen,"Source normalization after original")
                    stage, image = "source_normalize_v%d"%cfg[1], data["before"]
                    required = allowed = keys([cfg[1]])
                elif cfg == (1,8,1,13,0):
                    require(seq not in original_seen,"Prefix repair after original")
                    stage, image = "prefix", data["before"]
                    required = allowed = interval(8,0,26)
                elif cfg in ((1,10,1,64,1),(1,11,1,64,0)):
                    require(seq in original_done,"Tail repair before original completion")
                    stage, image = "tail_v%d"%cfg[1], data["after"]
                    required = allowed = interval(cfg[1],cfg[4]*2,128)
                elif cfg in ((0,0,1,129,0),(0,10,1,64,0)):
                    require(seq not in original_seen,"Capture after original")
                    stage, image = "capture_%d_%d"%(cfg[1],cfg[3]), data["before"]
                else:
                    require(False,"Unrecognized narrow transport shape")
            else:
                require(insn & 0x7f == 0x27 and cfg[0] == 0,"Unexpected transport instruction")
                stage, image = "store", data["after"]
            if stage != "store":
                stages[stage] += 1
                require(stages[stage] == 1,"Duplicate transport stage")
            item = dict(stage=stage,image=image,required=required,allowed=allowed,seen=set(),
                        writes=[],alloc=row,done=None,seq=key[0],instruction=insn)
            pending[key] = item
            groups.append(item)
        elif event == "done":
            require(key in pending,"Unallocated transport completion")
            item = pending.pop(key)
            require(int(row["cycle"]) >= int(item["alloc"]["cycle"]),"Premature completion")
            item["done"] = row
            last_done[key] = item
            if item["stage"] == "narrow_active": original_done.add(key[0])
        elif event == "write":
            item = pending.get(key)
            if item is None:
                item = last_done.get(key)
                require(item is not None and int(item["done"]["cycle"]) == int(row["cycle"]),
                        "Write outside allocated/completing uop")
            require(all(row[k] == item["alloc"][k] for k in
                        ("insn","use_vd","vd","eew","vl","vstart")) and
                    int(row["cycle"]) >= int(item["alloc"]["cycle"]),
                    "Transport write metadata/time differs")
            word,known = _write_data(row["wdata"]); be = int(row["be"],16)
            require(0 <= be <= 255 and 0 <= int(row["lane"]) < 4 and not be & ~known,
                    "Unknown/invalid granted byte")
            write = VectorWrite(row=number,cycle=int(row["cycle"]),arch_seq=key[0],vid=key[1],
                lane=int(row["lane"]),source=int(row["source"]),instruction=int(row["insn"],16),
                eew=int(row["eew"]),addr=int(row["addr"]),be=be,data=word,known_be=known)
            for position,(value,_) in _architectural_bytes([write],4,1024).items():
                require(position in item["allowed"],"Unexpected granted register/byte")
                reg,byte = position
                require(value is not None and value == item["image"][reg*128+byte],
                        "Canonical granted active/preservation byte differs")
                item["seen"].add(position)
            item["writes"].append(write)
        else:
            require(False,"Unknown transport event")
    require(not pending and original_seen == original_done and len(original_seen) == 1,
            "Incomplete original/transport")
    required_stages = {"init%d"%r for r in range(32)} | {"seed","shift","narrow_active"}
    require(required_stages.issubset(stages),"Missing architectural write stage")
    by_seq = {}
    for item in groups:
        require(item["done"] is not None and item["required"].issubset(item["seen"]),
                "Missing required granted bytes")
        by_seq.setdefault(item["seq"],[]).append(item)
    writing = [(seq,items) for seq,items in sorted(by_seq.items()) if any(i["writes"] for i in items)]
    # Zero-BE monitor events on read-only uops are not write destinations.
    writing = [(seq,items) for seq,items in writing if any(w.be for i in items for w in i["writes"])]
    require(len(writing) == len(refs),"Actual/reference write-request population differs")
    records = []
    for (seq,items),ref in zip(writing,refs):
        require(all(i["instruction"] == ref.instruction for i in items),"Reference instruction identity differs")
        actual = _architectural_bytes([w for i in items for w in i["writes"]],4,1024)
        expected_image = data["after"] if ref.instruction == proof.WORD else (
            data["seeded"] if any(i["stage"] == "seed" for i in items) else (
            data["before"] if any(i["stage"] == "shift" for i in items) else initial))
        for (reg,byte),(value,_) in actual.items():
            require(value is not None and value == expected_image[reg*128+byte],
                    "Final deshuffled activity image differs")
        skipped = sum(reg not in ref.vector_writes for reg,byte in actual)
        checked = len(actual)-skipped
        require(ref.instruction == proof.WORD or skipped == 0,"Non-narrow skip cannot be supplemented")
        records.append(dict(arch_seq=seq,instruction="0x%08x"%ref.instruction,pc="0x%016x"%ref.pc,
            compared_bytes=checked,supplemented_preservation_bytes=skipped,
            uops=len(items),write_events=sum(len(i["writes"]) for i in items),
            supplemented_registers=sorted({reg for reg,byte in actual if reg not in ref.vector_writes})))
    return dict(status="ALL_GRANTED_BYTES_CANONICAL_EXACT",unknown_bytes=0,
        records=records,stages=dict(stages),
        granted_byte_events=sum(bin(w.be).count("1") for i in groups for w in i["writes"]),
        uop_unique_bytes=sum(len(i["seen"]) for i in groups),
        compared_bytes=sum(r["compared_bytes"] for r in records),
        supplemented_preservation_bytes=sum(r["supplemented_preservation_bytes"] for r in records),
        physical_traffic_inferred_from_spike=False,
        route_inferred_from_metadata_not_direct_state_probe=True)


def vector_exact(result,audit):
    require(audit.get("status") == "ALL_GRANTED_BYTES_CANONICAL_EXACT" and audit.get("unknown_bytes") == 0,
            "Missing strict transport audit")
    fixed = dict(status="PASS",compared_instructions=35,compared_bytes=audit["compared_bytes"],
        skipped_unknown_bytes=audit["supplemented_preservation_bytes"],non_bit_exact_instructions=0,
        unobservable_instructions=0,nr_lanes=4,vlen_bits=1024,selected_index=None,
        stopped_at_spike_index=None,trapped_requests=[],incomplete_requests=[],unretired_requests=[],
        first_mismatch=None)
    for key,value in fixed.items():
        require(key in result and type(result[key]) is type(value) and result[key] == value,
                "Exact vector contract differs: "+key)
    records = result.get("instructions",[])
    require(len(records) == len(audit["records"]) == 35,"Missing per-record evidence")
    for record,expected in zip(records,audit["records"]):
        fields = dict(status="PASS",unknown_write_bytes=0,mismatch_count=0,first_mismatch=None,
            arch_seq=expected["arch_seq"],instruction=expected["instruction"],pc=expected["pc"],
            uops=expected["uops"],write_events=expected["write_events"],
            compared_bytes=expected["compared_bytes"],
            skipped_unknown_bytes=expected["supplemented_preservation_bytes"])
        require(all(k in record and type(record[k]) is type(v) and record[k] == v for k,v in fields.items()),
                "Per-record comparison/independent preservation differs")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-seal", required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args(argv)
    require(args.prepared_seal == PREPARED_SEAL, "Only parent-reviewed GAP103 prepared seal allowed")
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
                runtime["old_image_files_checked"] == 66 and runtime["baseline_tests"] == 719,
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
        transport = transport_exact(vectors,commits)
        life.save(out/"transport-byte-audit.json",transport)
        vector_exact(vector,transport)
        targets = json.loads(read(runner.PRE/"target-before.json"))
        runner.validate_targets(targets)
        before = json.loads(read(BASE/"combined-bits.json"))
        admission = json.loads(read(BASE/"admission-manifest.json",proof.BASE_SEAL))
        require(pins[str(BASE/"combined-bits.json")] == admission["output_pins"][str(BASE/"combined-bits.json")]
                and len(before["tests"]) == len(set(before["tests"])) == 719 and
                read(BASE/"combined-inputs.txt").decode().splitlines() == [str(DESIGN),*before["tests"]],
                "Frozen719 membership differs")
        for path in sorted((RUN/"code.vdb").rglob("*")):
            if path.is_file(): read(path)
        for path in (Path(__file__).resolve(),Path(__file__).with_name("test_collect_gap103_strict.py"),
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
        life.save(out/"status.json",dict(status=("GAP103_STRICT_CANDIDATE_NOT_ADMITTED" if qualified else
            "GAP103_STRICT_ARCHITECTURE_PASS_TARGET_NOT_HIT_NOT_ADMITTED"),baseline_tests=719,
            architecture_oracle_pass=True, coverage_candidate_qualified=qualified, target_hit_verified=qualified,
            coverage_admitted=False,aggregate_admission=False,rtl_changed=False,simulations_started=False,
            official_DVE_report=False,raw_delta=delta["metrics"]))
    except Exception as error:
        if not (out/"evidence-pins.json").exists():
            life.save(out/"evidence-pins.json",pins)
        life.save(out/"failure.json",dict(status="GAP103_COLLECTOR_REJECTED_NOT_ADMITTED",reason=str(error),
                                        coverage_admitted=False,simulations_started=False))
        raise


if __name__ == "__main__":
    main()

