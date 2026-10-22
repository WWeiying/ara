"""Independent native AKV evidence collector; no admission, EDA or Spike launch."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import sys

import admit_gap97_offline as common
import audit_gap73_akv as legacy
import build_akv_column_boundary_v2_preflight as software
import run_akv_column_boundary_v2_simulation as runner

life, require = runner.life, software.require
RUN = life.OUT / "akv-column-boundary-v2-old-image-20261006-01"
RUN_SEAL = "7c8f3564b941ef167ff7c6156be5072f0eaefe74837e2f107a5f95adc735d974"
WORDS = [0x00b5605b, 0x0005745b, 0x0005745b, 0x0005745b,
         0x0005355b, 0x0005365b, 0x0005375b, 0x0000505b]
HEX = {"pc", "insn", "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata"}


def request_instruction(word):
    return word & 127 in (0x07, 0x27, 0x57, 0x5b) or (
        word & 127 == 0x73 and (word >> 12) & 7 and
        word >> 20 in (0x008, 0x009, 0x00a, 0xc20, 0xc21, 0xc22, 0x00f))


def instruction_lifecycle(rows, starts):
    retired = [r for r in rows if r["event"] == "retire"]
    expected = Counter(r["insn"] for r in retired if request_instruction(r["insn"]))
    trapped = [r for r in retired if r["trap"]]
    if not trapped:
        expected[WORDS[2]] += 1
    actual = Counter(r["insn"] for r in starts.values())
    require(actual == expected and all(request_instruction(w) for w in actual),
            "CVX instructions do not match complete sealed-ELF retirements")
    csr_requests = sum(n for w, n in actual.items() if w & 127 == 0x73)
    require(csr_requests == 23 and sum(actual.values()) == 196,
            "Expected 32 seeds +128 stores +8 custom +5 vsets +23 vector CSR requests")
    require(sum(r["insn"] == 0x30200073 and not r["trap"] for r in retired) == 1,
            "Missing/extra actual mret")
    return dict(vector_CSR_requests=23, total_requests=196, complete_retirement_binding=True,
                expected_fault_RVFI_rows=len(trapped))


def csr_boundary_audit(csr, commands, vsets, uops, done):
    addresses = [0x001, 0x008, 0xc20, 0xc21, 0x00a, 0x009]
    initial = [r for r in csr if r["insn"] >> 20 in addresses and
               not ((r["insn"] >> 12) & 7 == 2 and (r["insn"] >> 15) & 31 == 0)]
    require([(r["insn"] >> 20, (r["insn"] >> 12) & 7, (r["insn"] >> 15) & 31)
             for r in initial] == [(1, 5, 21), (0xa, 5, 2), (9, 5, 1), (8, 1, 0)] and
            all(r["cycle"] < vsets[0]["cycle"] and r["rd"] == 0 and not r["trap"] for r in initial),
            "Initial fflags/vxrm/vxsat/vstart writes differ or occur after seeding")
    probes = [r for r in csr if r["insn"] >> 20 in addresses and
              (r["insn"] >> 12) & 7 == 2 and (r["insn"] >> 15) & 31 == 0]
    require(len(probes) == 24 and len(vsets) == 5, "Missing/extra boundary CSR probes/vsets")
    for phase, command_phase in enumerate((1, 2, 3, 7)):
        frame = probes[phase*6:phase*6+6]
        command = commands[command_phase]
        require([r["insn"] >> 20 for r in frame] == addresses and
                [r["rd_wdata"] for r in frame] == [21, 0, 64, 8, 2, 1] and
                all(r["rd"] != 0 and not r["trap"] for r in frame),
                "Actual phase CSR values/order differ")
        seq = command["seq"]
        require(seq in uops and seq in done and
                max(command["response_cycle"], done[seq]["cycle"]) <= frame[0]["cycle"] and
                frame[-1]["cycle"] < vsets[phase+1]["cycle"],
                "CSR snapshot outside completed-command/pre-snapshot-vset window")
    return dict(actual_readbacks=24, frame_values=[21, 0, 64, 8, 2, 1],
                pre_snapshot_vset_order_verified=True)


def commit_rows(path):
    rows = [{k: v if k == "event" else int(v, 16 if k in HEX else 10)
             for k, v in r.items()} for r in common.read_csv(path, common.COMMIT_FIELDS)]
    require(rows and all(r["event"] in {"retire", "arch_start", "cvx_req", "cvx_resp", "uop_alloc", "uop_done"}
            and r["trap"] in (0, 1) and r["cycle"] >= 0 and 0 <= r["rd"] < 32 for r in rows), "Unknown/malformed commit event")
    require(all(a["cycle"] <= b["cycle"] for a, b in zip(rows, rows[1:])), "Commit cycle regression")
    require(all(not r["trap"] or r["event"] in ("retire", "cvx_resp") for r in rows), "Trap in wrong event")
    for r in rows:
        if r["event"] != "retire":
            require(all(r[k] == 0 for k in ("pc", "rd", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata")) and
                    (r["event"] == "cvx_resp" or r["rd_wdata"] == 0), "Foreign monitor side-effect fields")
        if r["event"] in ("arch_start", "cvx_req", "cvx_resp"):
            require(r["port"] == -1 and r["trans_id"] >= 0, "Foreign frontend monitor fields")
        if r["event"] in ("cvx_req", "cvx_resp"):
            require(r["order"] == -1 and (r["event"] != "cvx_resp" or r["insn"] == 0),
                    "Foreign request/response fields")
    retires = [r for r in rows if r["event"] == "retire"]
    require([r["order"] for r in retires] == list(range(len(retires))), "Incomplete retirement order")
    return rows


def elf_code(blob, pc):
    h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    matches = []
    for i in range(h[9]):
        kind, flags, off, address, _, size, _, _ = struct.unpack_from("<IIQQQQQQ", blob, h[4]+56*i)
        if kind == 1 and flags & 1 and address <= pc and pc+4 <= address+size:
            matches.append(int.from_bytes(blob[off+pc-address:off+pc-address+4], "little"))
    require(len(matches) == 1 and pc % 4 == 0, "Retired PC outside exact no-C ELF text")
    return matches[0]


def expected_memory(symbols):
    snapshots = [0x343f if reg == 8 and index == 0 else
                 {10: 0x2400, 12: 0x3400, 14: 0x4400}[reg]+index
                 if phase == 3 and reg in (10, 12, 14) else 0x1000+64*reg+index
                 for phase in range(4) for reg in range(32) for index in range(64)]
    values = dict(boundary_snapshots=struct.pack("<8192H", *snapshots),
        boundary_status=struct.pack("<8I", 0, 0, 7, 0, 0, 0, 0, 0),
        boundary_trap=struct.pack("<4Q", 1, 2, symbols["boundary_bad"], 0),
        g75_result=struct.pack("<2I", 8420, 0), num_failed=struct.pack("<I", 0),
        boundary_csrs=struct.pack("<24Q", *([21, 0, 64, 8, 2, 1]*4)),
        boundary_scan=struct.pack("<8I", *([2048, 0]*4)), g75_trap=bytes(24),
        seed=struct.pack("<2048H", *range(0x1000, 0x1800)))
    for name, base in (("query", 0x2400), ("key", 0x3400), ("value", 0x4400)):
        values[name] = struct.pack("<64H", *range(base, base+64))
    descriptor = struct.pack("<4B2H4I5Q", 1, 1, 1, 0, 64, 1, 128, 128, 128, 0,
        symbols["query"], symbols["key"], symbols["value"], 0, 0)
    values["descriptor"] = descriptor
    return {symbols[n]+i: v for n, data in values.items() for i, v in enumerate(data)}


def command_faults(commands):
    require(len(commands) == 8 and [c["word"] for c in commands] == WORDS and
            [c.get("fault") for c in commands] == [0, 0, 1, 0, 0, 0, 0, 0], "Exact custom outcomes differ")


def commit_audit(rows, symbols, blob):
    wanted, memory, gpr = expected_memory(symbols), {}, {0: 0}
    starts, claimed, pending, commands = {}, set(), {}, []
    uops, active, done = {}, {}, {}
    requests = responses = faults = 0
    custom_retired, vsets, csr = [], [], []
    csr_writes = {}
    terminal = []
    seed_requests = store_requests = 0
    for r in rows:
        event, word, cycle = r["event"], r["insn"], r["cycle"]
        if event == "arch_start":
            require(r["order"] not in starts, "Duplicate arch sequence")
            starts[r["order"]] = r
        elif event == "cvx_req":
            transaction = r["trans_id"]
            require(transaction not in pending, "Live transaction reuse")
            matches = [s for s in starts.values() if s["order"] not in claimed and s["trans_id"] == transaction
                       and s["insn"] == word and s["cycle"] <= cycle]
            require(len(matches) == 1, "Ambiguous/unbound CVX request")
            start = matches[0]; claimed.add(start["order"])
            item = dict(word=word, seq=start["order"], id=transaction, request_cycle=cycle)
            if word & 127 in (7, 0x27):
                register = (word >> 15) & 31
                if word & 127 == 7:
                    require(seed_requests < 32 and gpr.get(register) == symbols["seed"]+128*seed_requests,
                            "VRF seed request address/order differs")
                    seed_requests += 1
                else:
                    require(store_requests < 128 and gpr.get(register) == symbols["boundary_snapshots"]+128*store_requests,
                            "Full snapshot store address/order differs")
                    store_requests += 1
            if word & 127 == 0x5b:
                phase = len(commands)
                require(phase < 8 and word == WORDS[phase], "Extra/reordered custom opcode")
                operands = [(symbols["descriptor"], 0), (63, None), (64, None), (63, None),
                            (0, None), (1, None), (2, None), (None, None)][phase]
                require(operands[0] is None or gpr.get(10) == operands[0], "Wrong actual selector/descriptor operand")
                require(operands[1] is None or gpr.get(11) == operands[1], "Wrong actual tile operand")
                if phase == 0:
                    require(all(memory.get(symbols[name]+i) == wanted[symbols[name]+i]
                                for name, size in (("descriptor", 64), ("query", 128), ("key", 128), ("value", 128))
                                for i in range(size)), "Actual FULL descriptor/payload bytes differ")
                item["phase"] = phase
                commands.append(item)
            pending[transaction] = item
            requests += 1
        elif event == "cvx_resp":
            require(r["trans_id"] in pending, "Orphan response")
            item = pending.pop(r["trans_id"])
            require(item["request_cycle"] <= cycle, "Early response")
            item.update(fault=r["trap"], response_cycle=cycle)
            require(not r["trap"] or item.get("phase") == 2, "Unexpected CVX exception")
            if item["word"] & 127 == 0x57:
                require(r["rd_wdata"] == 64, "Actual vset CVX return VL differs")
            if item["word"] & 127 == 0x73 and (item["word"] >> 12) & 7 == 2:
                require(r["rd_wdata"] == {8:0, 9:1, 10:2, 0xc20:64, 0xc21:8}[item["word"] >> 20],
                        "Actual vector CSR CVX return differs")
            responses += 1; faults += r["trap"]
        elif event in ("uop_alloc", "uop_done"):
            seq, vid = r["order"], r["port"]
            require(seq in starts and 0 <= vid < 8 and r["insn"] == starts[seq]["insn"] and
                    r["trans_id"] == starts[seq]["trans_id"] and starts[seq]["cycle"] <= cycle and
                    all(r[k] == 0 for k in ("pc", "rd", "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata", "trap")),
                    "Unbound uop metadata")
            if event == "uop_alloc":
                require(vid not in active and seq not in uops, "Duplicate/reused backend allocation")
                active[vid] = r; uops[seq] = r
            else:
                require(vid in active and active[vid]["order"] == seq and seq not in done and
                        active[vid]["cycle"] <= cycle, "Orphan/early/duplicate backend completion")
                active.pop(vid); done[seq] = r
        else:
            require(elf_code(blob, r["pc"]) == word, "Retired instruction differs from sealed ELF")
            if r["trap"]:
                require(r["pc"] == symbols["boundary_bad"] and word == WORDS[2] and
                        r["mem_wmask"] == r["mem_rmask"] == 0, "Unexpected precise trap PC/instruction/side effect")
            else:
                if r["rd"]:
                    gpr[r["rd"]] = r["rd_wdata"]
                if r["mem_wmask"]:
                    for a, v in legacy.scalar_store_bytes(r["mem_addr"], r["mem_wdata"], r["mem_wmask"]):
                        if a in wanted: memory[a] = v
                    if r["mem_addr"] == symbols["tohost"]:
                        require(r["mem_wmask"] == 255, "Partial terminal store")
                        terminal.append((r["order"], r["mem_wdata"]))
                if r["mem_rmask"]:
                    for a, v in legacy.scalar_store_bytes(r["mem_addr"], r["rd_wdata"], r["mem_rmask"]):
                        if a in wanted: memory[a] = v
                if word & 127 == 0x57:
                    require(word == 0x0082f057 and gpr.get(5) == 64, "Unexpected vset or actual AVL")
                    vsets.append(r)
                if word & 127 == 0x73 and (word >> 12) & 7:
                    csr.append(r)
                    if (word >> 12) & 7 == 1:
                        register = (word >> 15) & 31
                        require(register in gpr, "Unknown actual CSR write operand")
                        csr_writes.setdefault(word >> 20, []).append(gpr[register])
            if word & 127 == 0x5b:
                custom_retired.append(r)
    command_faults(commands)
    require(not pending and not active and set(done) == set(uops) and requests == responses == 196 and faults == 1 and
            len(starts) == len(claimed) == 196, "Incomplete exact CVX/backend lifecycle")
    require([r["order"] for r in sorted(starts.values(), key=lambda r: r["order"])] == list(range(196)),
            "Missing arch sequence")
    require(len(vsets) == 5, "Missing five exact vsets")
    require(seed_requests == 32 and store_requests == 128, "Incomplete actual seed/snapshot addresses")
    good = [r["insn"] for r in custom_retired if not r["trap"]]
    require(good == WORDS[:2]+WORDS[3:] and len([r for r in custom_retired if r["trap"]]) <= 1,
            "Incomplete/duplicate custom retirement")
    retires = [r for r in rows if r["event"] == "retire"]
    require(terminal == [(retires[-1]["order"], 1)] and memory == wanted, "Wrong final signature/full observed memory")
    for address, expected in ((0x304, [0]), (0x302, [0]),
            (0x305, [symbols["trap_fail"], symbols["boundary_handler"]]),
            (0x341, [symbols["boundary_bad"]+4])):
        require(csr_writes.get(address) == expected, "Actual trap-control CSR writes differ")
    for address, expected in ((0x342, 2), (0x341, symbols["boundary_bad"]), (0x343, 0)):
        probes = [r for r in csr if r["insn"] >> 20 == address and (r["insn"] >> 12) & 7 == 2 and
                  (r["insn"] >> 15) & 31 == 0]
        require(len(probes) == 1 and probes[0]["rd_wdata"] == expected, "Actual handler CSR readback differs")
    return dict(status="AKV_NATIVE_OBSERVED_COMMAND_TRAP_VRF_MEMORY_EXACT_NOT_FULL_SCALAR_COMPARISON",
        commands=commands, requests=requests, responses=responses, exceptions=faults, retirement_rows=len(retires),
        observed_memory_bytes=len(wanted), uops=list(uops.values()), completions=list(done.values()),
        exact_vsets=5, handler_CSR_readbacks=True, trap_control_CSR_writes=csr_writes,
        full_scalar_differential_qualified=False,
        boundary_CSR_audit=csr_boundary_audit(csr, commands, vsets, uops, done),
        instruction_lifecycle=instruction_lifecycle(rows, starts),
        unobserved_CSRs=[])


def vector_audit(path, arch):
    rows = common.read_csv(path, common.VECTOR_FIELDS)
    require(rows and rows[0]["event"] == "config" and all((int(r["nr_lanes"]), int(r["vlen_bits"])) == (4, 1024)
            for r in rows), "Missing/foreign vector config")
    require(all(r["event"] in ("alloc", "done", "write") for r in rows[1:]), "Unknown/reset vector event")
    commands = {c["seq"]: c for c in arch["commands"]}
    groups, active, state, mirrors = {}, {}, {}, {}
    seeds, stores, custom_writes = [], [], Counter()
    previous = -1
    for r in rows[1:]:
        cycle, seq, vid = int(r["cycle"]), int(r["arch_seq"]), int(r["vid"])
        word = int(r["insn"], 16)
        require(cycle >= previous, "Vector cycle regression"); previous = cycle
        key = (seq, vid)
        metadata = tuple(int(r[k]) for k in ("use_vd", "vd", "eew", "vl", "vstart"))
        require(0 <= int(r["source"]) < 5 and 0 <= vid < 8 and 0 <= seq,
                "Invalid native vector source/VID/sequence")
        if r["event"] in ("alloc", "done"):
            require(all(int(r[k], 16 if k in ("be", "wdata") else 10) == 0
                        for k in ("lane", "source", "addr", "be", "wdata")),
                    "Side-effect fields in lifecycle mirror")
        if r["event"] == "alloc":
            require(key not in groups and vid not in active, "Duplicate/live vector allocation")
            use, vd, eew, vl, start = metadata
            require(eew == 1 and start == 0, "Wrong effective EEW/vstart")
            group = dict(word=word, metadata=metadata, writes=set(), done=False)
            if word & 127 == 0x5b:
                require(seq in commands and commands[seq]["word"] == word, "Unbound native custom vector allocation")
                phase = commands[seq]["phase"]
                require(len(stores) == [0, 0, 32, 64, 96, 96, 96, 96][phase],
                        "Custom command outside complete snapshot boundaries")
                require(state == {(rr, i): (0x1000+64*rr+i//2).to_bytes(2, "little")[i%2]
                                   for rr in range(32) for i in range(128)} if phase == 0 else len(state) == 4096,
                        "Incomplete VRF seed/state before custom")
                # The dispatcher allocates vd8 for a COLUMN before engine validation.
                # Rejection must have zero accepted writes, not use_vd=0 metadata.
                expected_use = int(phase in (1, 2, 3, 4, 5, 6))
                require(use == expected_use and vl == (64 if expected_use else 1), "Wrong custom reservation/VL")
                require(not use or vd == {1: 8, 2: 8, 3: 8, 4: 10, 5: 12, 6: 14}[phase], "Wrong custom destination")
                group["phase"] = phase
            elif use:
                require(vl == 64 and word & 127 == 7 and word & ~(31<<15 | 31<<7) == 0x02005007 and
                        vd == len(seeds) < 32 and (word>>7)&31 == vd, "Unexpected/duplicate VRF seed writer")
                seeds.append(vd); group["seed"] = vd
            else:
                phases = [g["phase"] for g in groups.values() if "phase" in g]
                require(len(stores) < 128 and phases and phases[-1] == (1, 2, 3, 7)[len(stores)//32],
                        "Snapshot store outside exact custom boundary")
                require(vl == 64 and word & 127 == 0x27 and word & ~(31<<15 | 31<<7) == 0x02005027 and
                        (word>>7)&31 == len(stores)%32 and len(stores) < 128, "Unexpected vector store/protection order")
                stores.append((word>>7)&31)
            groups[key] = group; active[vid] = key
        else:
            require(key in groups and groups[key]["word"] == word and groups[key]["metadata"] == metadata,
                    "Untracked vector metadata")
            group = groups[key]
            if r["event"] == "done":
                require(not group["done"] and active.get(vid) == key, "Duplicate/orphan vector done")
                group.update(done=True, done_cycle=cycle); active.pop(vid)
            else:
                require(metadata[0] == 1 and group.get("phase") != 2 and
                        (not group["done"] or cycle == group["done_cycle"]),
                        "Illegal/late VRF write")
                reg, chunk = divmod(int(r["addr"]), 4)
                lane, be, data = int(r["lane"]), int(r["be"], 16), int(r["wdata"], 16)
                require(reg == metadata[1] and 0 <= lane < 4 and 0 < be < 256, "Neighbor/invalid accepted write")
                for byte in range(8):
                    if not be >> byte & 1: continue
                    slot, within = divmod(byte, 2)
                    natural = ((slot&1)<<1) | (slot>>1)
                    offset = chunk*32+(natural*4+lane)*2+within
                    require(offset < (2 if group.get("phase") in (1, 3) else 128) and offset not in group["writes"], "Duplicate/out-of-range accepted byte")
                    phase = group.get("phase")
                    half = 0x1000+64*reg+offset//2 if "seed" in group else (
                        0x343f if offset//2 == 0 else 0) if phase in (1, 3) else (
                        {4: 0x2400, 5: 0x3400, 6: 0x4400}[phase]+offset//2)
                    value = (data >> (8*byte)) & 255
                    require(value == half.to_bytes(2, "little")[offset%2], "Independent accepted VRF byte differs")
                    state[reg, offset] = value; group["writes"].add(offset)
                    if phase is not None: custom_writes[phase] += 1
        if r["event"] in ("alloc", "done"):
            event = "uop_alloc" if r["event"] == "alloc" else "uop_done"
            require((event, seq) not in mirrors, "Duplicate vector lifecycle mirror")
            mirrors[event, seq] = (cycle, vid, word)
    reference = {(e, r["order"]): (r["cycle"], r["port"], r["insn"])
                 for e, rows_ in (("uop_alloc", arch["uops"]), ("uop_done", arch["completions"])) for r in rows_}
    require(mirrors == reference and not active and all(g["done"] for g in groups.values()), "Commit/vector completion disagreement")
    require(seeds == list(range(32)) and stores == list(range(32))*4 and
            [g["phase"] for g in groups.values() if "phase" in g] == list(range(8)), "Missing/reordered seed/store/custom groups")
    require(all(g["writes"] == set(range(2 if g.get("phase") in (1, 3) else 128)) if g["metadata"][0] and g.get("phase") != 2 else not g["writes"]
                for g in groups.values()),
            "Partial destination or unexpected nondestination writes")
    require(custom_writes == {1: 2, 3: 2, 4: 128, 5: 128, 6: 128}, "Wrong exact388 custom bytes")
    final = {(reg, byte): (0x343f if reg == 8 and byte//2 == 0 else
             {10: 0x2400, 12: 0x3400, 14: 0x4400}[reg]+byte//2 if reg in (10, 12, 14)
             else 0x1000+64*reg+byte//2).to_bytes(2, "little")[byte%2]
             for reg in range(32) for byte in range(128)}
    require(state == final, "Final whole VRF state differs")
    return dict(status="EXACT_NATIVE_VRF_WRITE_ORACLE_NOT_SPIKE_COMPARISON", custom_destination_bytes=388,
                rejected_write_bytes=0, fully_seeded_registers=32, snapshot_stores=128,
                backend_lifecycle_mirrored=True, effective_EEW16_VL64_vstart0=True)


def stdout_audit(log):
    require(not re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b|Error:|Fatal:|Assertion\b)|\$fatal", log), "Runtime error")
    require(log.count("Core Test *** SUCCESS ***") == 1 and len(re.findall(r"^\$finish at simulation time\s+\d+", log, re.M)) == 1,
            "Nonunique/missing completion")
    for level in ("ERROR", "FATAL"):
        require(re.findall(r"^UVM_"+level+r"\s*:\s*(\d+)", log, re.M) == ["0"], "UVM error/missing final severity")
    contract = re.findall(r"^\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+) mmu_request_cycles=\d+ protocol_errors=(\d+) outstanding=(\d+)", log, re.M)
    require(contract == [("196", "196", "1", "0", "0")], "Exact CVX contract differs")
    lines = [l for l in log.splitlines() if l.startswith("[AKV_PERF] ")]
    require(len(lines) == 8, "Missing/extra native PERF records")
    perf = []
    for phase, line in enumerate(lines):
        matches = [re.fullmatch(r"([a-z_][a-z_0-9]*)=([0-9]+)", t) for t in line.split()[1:]]
        require(all(matches) and len(matches) == len(legacy.PERF_KEYS), "Malformed native PERF")
        row = {m[1]: int(m[2]) for m in matches}
        require(set(row) == set(legacy.PERF_KEYS), "Duplicate/missing PERF key")
        expected = dict(seq=phase+1, command=[4,6,6,6,2,2,2,3][phase], success=int(phase != 2),
            fault=int(phase == 2), validation_fault=int(phase == 2), validation_error=13 if phase == 2 else 0,
            read_fault=0, context_ready=int(phase != 7), full=0, refill=0, load=int(phase in (4,5,6)),
            release=int(phase == 7), v2_full=int(phase == 0), v2_refill=0, v2_row_load=int(phase in (4,5,6)),
            v2_column_load=int(phase in (1,2,3)), v2_column_panel=0, v2_logical_column=int(phase in (1,2,3)),
            v2_bank_conflict_cycles=0, v2_rejected=int(phase == 2), q_external_bytes=128 if phase == 0 else 0,
            kv_external_bytes=256 if phase == 0 else 0, replay_bytes=2 if phase in (1,3) else 128 if phase in (4,5,6) else 0,
            read_ranges=4 if phase == 0 else 0, translations=0, read_payload_bytes=448 if phase == 0 else 0)
        require(all(row[k] == v for k, v in expected.items()) and row["busy_cycles"] > 0, "Native PERF phase contract differs")
        if phase != 0:
            require(row["ar"] == row["r_beats"] == 0, "Unexpected external read on column/reject/replay/release")
        perf.append(row)
    return dict(status="EXACT_NATIVE_PERF_AND_CONTRACT", perf=perf)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    out = parser.parse_args().output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    out.mkdir()
    pins = {}
    try:
        manifest = life.read_bound(RUN / "manifest.json", RUN_SEAL)
        require(life.read_bound(RUN.with_name(RUN.name+".prepared.json"), RUN_SEAL) == manifest,
                "Executed manifest differs from prepared")
        pre = manifest["preflight"]
        directory = Path(pre["input_elf"]).parent
        runner.validate(pre, directory)
        require(manifest["command"] == runner.command(pre, RUN) and manifest["timeout_s"] == 900,
                "Executed command/timeout differs")
        require(json.loads((RUN / "simulation-status.json").read_bytes()) ==
                dict(status="SIMULATION_EXITED_NOT_ADMITTED", returncode=0, case=runner.NAME, coverage_admitted=False),
                "Nonterminal/failed simulation")
        pins = life.merge_pins(pins, manifest["pins"])
        for p in (RUN / "manifest.json", RUN.with_name(RUN.name+".prepared.json"), RUN / "simulation-status.json",
                  RUN / "console.log", RUN / "run.vcs.log", RUN / "commit_trace.csv", RUN / "vector_trace.csv",
                  Path(__file__).resolve(), Path(__file__).with_name("test_check_akv_column_boundary_v2_offline.py"),
                  Path(common.__file__).resolve(), Path(legacy.__file__).resolve(), Path(common.bitmap.__file__).resolve()):
            pins = life.merge_pins(pins, {str(p): life.digest(p)})
        monitor = life.ROOT / "hardware/tb/ara_commit_monitor.sv"
        sources = json.loads((software.BUILD / "build-source-pins.json").read_bytes())
        pins = life.merge_pins(pins, {str(monitor): sources[str(monitor)]})
        for p in (life.ROOT / "verification/ara_verify").rglob("*.py"):
            pins = life.merge_pins(pins, {str(p): life.digest(p)})
        for module in list(sys.modules.values()):
            name = getattr(module, "__file__", None)
            if name:
                p = Path(name).resolve()
                if p.suffix == ".py" and p.parent == Path(__file__).resolve().parent:
                    pins = life.merge_pins(pins, {str(p): life.digest(p)})
        vdb = RUN / "code.vdb"
        require(vdb.resolve() == vdb and vdb.is_dir(), "Missing/aliased VDB root")
        members = sorted(p for p in vdb.rglob("*") if p.is_file())
        require(members and not any(p.is_symlink() for p in vdb.rglob("*")), "Missing/aliased VDB")
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in members})
        life.check(pins)
        require((RUN / "console.log").read_text().count("Core Test *** SUCCESS ***") == 1, "Missing console completion")
        symbols = dict(pre["symbols"])
        for n in ("query", "key", "value", "descriptor", "seed"):
            symbols[n] = software.shared._elf_symbol(directory / "input.elf", software.shared.LLVM / "llvm-readelf", n)
        perf = stdout_audit((RUN / "run.vcs.log").read_text())
        arch = commit_audit(commit_rows(RUN / "commit_trace.csv"), symbols, (directory / "input.elf").read_bytes())
        vector = vector_audit(RUN / "vector_trace.csv", arch)
        for phase, row in enumerate(perf["perf"]):
            groups = [r for r in arch["uops"] if r["order"] == arch["commands"][phase]["seq"]]
            require(len(groups) == 1 and row["id"] == groups[0]["port"], "PERF id is not exact backend VID")
        for name, value in (("native-contract-audit.json", perf), ("architecture-audit.json", arch),
                            ("native-vector-audit.json", vector)):
            life.save(out / name, value)
        inputs = out / "sample-inputs.txt"
        with inputs.open("x") as stream:
            stream.write(str(common.DESIGN)+"\n"+str(vdb)+"\n")
        sample = common.bitmap.collect(inputs)
        require(sample["tests"] == [str(vdb)], "Unexpected sample membership")
        pins = life.merge_pins(pins, sample["input_hashes"])
        target = sample["metrics"]["branch"][software.SCOPE]
        require(target["width"] == 166 and target["checksum"] == "131544421",
                "Target compiled shape differs")
        hit = bool(int(target["bits"], 16) & (1 << 141))
        life.save(out / "sample-bits.json", sample)
        life.save(out / "target-hit-audit.json", dict(raw_index=24, scope=software.SCOPE,
            sample_hit=hit, relative_gain_pending_verified_latest_baseline=True,
            baseline_not_rebound=True, native_GUI_ID_qualification=False))
        require(members == sorted(p for p in vdb.rglob("*") if p.is_file()), "VDB membership changed")
        life.check(pins)
        life.save(out / "status.json", dict(status="STRICT_AKV_NATIVE_CANDIDATE_NOT_ADMITTED",
            raw24_sample_hit=hit, aggregate_union_performed=False,
            relative_gain_pending_verified_latest_baseline=True,
            full_scalar_differential_qualified=False, software_Spike_not_native_oracle=True,
            CSR_observation_scope=arch["unobserved_CSRs"], coverage_admitted=False,
            simulations_started=False, rtl_changed=False, official_DVE_report=False))
        outputs = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        life.save(out / "candidate-seal.json", dict(input_pins=pins, output_pins=outputs,
            status="NATIVE_OBSERVED_EVIDENCE_ONLY_NOT_ADMISSION", full_scalar_differential_qualified=False))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / "candidate-seal.json"), raw24_hit=hit)))
    except Exception as error:
        life.save(out / "failure.json", dict(status="AKV_STRICT_COLLECTOR_FAILED_NOT_ADMITTED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
