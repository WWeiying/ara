"""Pure bit, ELF, UART and structured-native checks; never runs a simulator."""
import hashlib
import csv
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
NAME = "akv_gap54_skew_context"
TEST = "app:" + NAME
FORMAT = "gap54-akv-host-sealed-v1"
RUNTIME_FORMAT = "gap54-akv-runtime-v1"
BASE = ROOT / "verification/out/gap37-control-current-20261004-01"
ANALYSIS = ROOT / "verification/out/gap40-custom-analysis-20261004-01"
BUILD = ROOT / "verification/out/repaired-aligned-build-20260930-01"
WORDS = [0x00b5205b, *[0x0005345b]*3, 0x02a0605b, 0x02a0205b,
         0x0005345b, 0x00b5605b, *[0x0005345b]*3, 0x0000505b]
COMMANDS = [0,2,2,2,5,1,2,4,2,2,2,3]
HOST_CHECKS, DUT_CHECKS = 156, 177
PERF_KEYS = ("seq id command success fault validation_fault validation_error read_fault "
    "context_ready busy_cycles full refill load release v2_full v2_refill v2_row_load "
    "v2_column_load v2_column_panel v2_logical_column v2_k_view_bank_cycles "
    "v2_bank_conflict_cycles v2_rejected q_external_bytes kv_external_bytes replay_bytes "
    "replay_backpressure_cycles read_ranges translations ar r_beats read_payload_bytes "
    "store_wait_cycles read_backpressure_cycles read_outstanding_occ_sum read_outstanding_max "
    "read_outstanding_full_cycles").split()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024*1024), b""):
            h.update(data)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def expected_perf(index):
    cmd = COMMANDS[index]
    fault = 4 <= index <= 6
    full = index in (0,7)
    row = index in (1,2,3,8,9,10)
    result = dict(seq=index+1, command=cmd, success=int(not fault), fault=int(fault),
        validation_fault=int(fault), validation_error=12 if fault else 0,
        read_fault=0, context_ready=int(index < 4 or 7 <= index < 11),
        full=int(cmd == 0), refill=int(cmd == 1), load=int(cmd == 2), release=int(cmd == 3),
        v2_full=int(cmd == 4), v2_refill=int(cmd == 5), v2_row_load=int(8 <= index <= 10),
        v2_column_load=0, v2_column_panel=0, v2_logical_column=0,
        v2_rejected=int(index == 4), q_external_bytes=128 if full else 0,
        kv_external_bytes=256 if full else 0, replay_bytes=128 if row else 0,
        read_ranges=4 if full else 0, read_payload_bytes=448 if full else 0, translations=0)
    if not full:
        result.update(translations=0, ar=0, r_beats=0, store_wait_cycles=0,
            read_backpressure_cycles=0, read_outstanding_occ_sum=0,
            read_outstanding_max=0, read_outstanding_full_cycles=0)
    if not row:
        result["replay_backpressure_cycles"] = 0
    return result


def perf_records(log):
    lines = [s for s in log.splitlines() if "[AKV_PERF]" in s]
    require(len(lines) == 12, "exactly twelve AKV_PERF records required")
    rows = []
    for i, line in enumerate(lines):
        require(line.startswith("[AKV_PERF] "), "malformed PERF prefix")
        tokens = line[len("[AKV_PERF] "):].split()
        require(len(tokens) == len(PERF_KEYS), "PERF field count differs")
        row = {}
        for token in tokens:
            match = re.fullmatch(r"([a-z_][a-z_0-9]*)=([0-9]+)", token)
            require(match and match[1] not in row, "malformed/duplicate PERF field")
            row[match[1]] = int(match[2])
        require(set(row) == set(PERF_KEYS), "PERF fields differ")
        require(all(row[k] == v for k,v in expected_perf(i).items()), f"PERF phase {i+1} differs")
        require(row["busy_cycles"] > 0, "empty command cycle witness")
        if i in (0,7):
            require(row["ar"] >= 4 and row["r_beats"] >= 28 and
                    row["read_outstanding_max"] > 0, "missing FULL read activity")
        rows.append(row)
    return rows


def validate_log(log, host, elf=None):
    require(not re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b|ERROR\b|Fatal\b|Assertion\b)|\$fatal", log),
            "failure/assertion in log")
    phase_lines = [s for s in log.splitlines() if s.startswith("AKV54_PHASE")]
    csr_lines = [s for s in log.splitlines() if s.startswith("AKV54_CSR")]
    trap_lines = [s for s in log.splitlines() if s.startswith("AKV54_TRAP")]
    require(len(phase_lines) == 12, "phase count differs")
    checks = traps = 0
    phases = []
    for i, word in enumerate(WORDS):
        fault = 4 <= i <= 6
        traps += fault
        checks += 13 if host else 14 + 3*fault
        expected = f"AKV54_PHASE phase={i+1} word={word:08x} traps={traps} checks={checks} errors=0"
        require(phase_lines[i] == expected, f"phase {i+1} transcript differs")
        phases.append(dict(phase=i+1, word=f"{word:08x}", traps=traps, checks=checks))
    passed = f"PASSED: {NAME} checks={HOST_CHECKS if host else DUT_CHECKS} errors=0"
    require([s for s in log.splitlines() if s.startswith("PASSED:")] == [passed], "PASS total differs")
    require(log.index(phase_lines[-1]) < log.index(passed), "PASS precedes completion")
    if host:
        require(not csr_lines and not trap_lines and "[AKV_PERF]" not in log, "host cannot claim DUT evidence")
        require(log.splitlines() == phase_lines + [passed], "unexpected host output")
        return dict(status="HOST_PASS_ONLY", phases=phases, checks=checks, traps_modeled=3)
    require(elf is not None, "DUT ELF audit required")
    require(csr_lines == [f"AKV54_CSR phase={i+1} fflags=21 vstart=0" for i in range(12)],
            "missing/non-immediate CSR evidence")
    require(len(trap_lines) == 3, "exactly three trap records required")
    trap_rows = []
    for i, line in zip((4,5,6),trap_lines):
        match = re.fullmatch(r"AKV54_TRAP phase=(\d+) cause=(\d+) pc=([0-9a-f]+) expected=([0-9a-f]+) tval=([0-9a-f]+)", line)
        require(match is not None, "malformed trap record")
        phase,cause = int(match[1]),int(match[2])
        pc,expected,tval = [int(match[k],16) for k in (3,4,5)]
        require(phase == i+1 and cause == 2 and pc == expected == elf["sites"][i]["pc"] and
                tval in (0,WORDS[i]), "trap cause/ELF-PC/tval differs")
        trap_rows.append(dict(phase=phase,cause=cause,pc=pc,tval=tval))
    rows = perf_records(log)
    events = [s.split()[0] for s in log.splitlines()
              if s.startswith(("[AKV_PERF]", "AKV54_CSR", "AKV54_TRAP", "AKV54_PHASE"))]
    expected_events = []
    for i in range(12):
        expected_events += ["[AKV_PERF]", "AKV54_CSR"]
        if 4 <= i <= 6:
            expected_events.append("AKV54_TRAP")
        expected_events.append("AKV54_PHASE")
    require(events == expected_events, "terminal/CSR/trap/phase ordering differs")
    return dict(status="PASS", phases=phases, checks=checks, traps=trap_rows, perf=rows,
                busy_cycles_sum=sum(r["busy_cycles"] for r in rows))


def elf_audit(blob):
    require(blob[:6] == b"\x7fELF\x02\x01", "ELF64 little-endian required")
    header = struct.unpack_from("<HHIQQQIHHHHHH",blob,16)
    require(header[1] == 243 and header[10] == 64, "RISC-V ELF section layout differs")
    sections = [struct.unpack_from("<IIQQQQIIQQ",blob,header[5]+64*i) for i in range(header[11])]
    def section_data(section):
        start,size = section[4:6]
        require(start+size <= len(blob), "truncated ELF section")
        return blob[start:start+size]
    symbols = {}
    for s in sections:
        if s[1] != 2:
            continue
        names = section_data(sections[s[6]])
        data = section_data(s)
        require(s[9] == 24, "bad symbol size")
        for off in range(0,len(data),24):
            name,info,other,shndx,value,size = struct.unpack_from("<IBBHQQ",data,off)
            name = names[name:names.index(0,name)].decode()
            if name and not name.startswith("$") and info&15 != 4:
                require(name not in symbols, "duplicate ELF symbol: " + name)
                symbols[name] = dict(value=value,size=size,section=shndx)
    def code(address,size):
        matches = [s for s in sections if s[2]&4 and s[3] <= address and address+size <= s[3]+s[5]]
        require(len(matches) == 1, "code outside executable section")
        s = matches[0]
        off = s[4]+address-s[3]
        return blob[off:off+size]
    sites = []
    custom = []
    for s in sections:
        if not s[2]&4:
            continue
        data = section_data(s)
        offset = 0
        while offset < len(data):
            half = int.from_bytes(data[offset:offset+2],"little")
            size = 4 if half&3 == 3 else 2
            if size == 4 and half&0x7f == 0x5b:
                custom.append(s[3]+offset)
            offset += size
    for i, word in enumerate(WORDS):
        pc = symbols[f"gap54_site_{i+1}"]["value"]
        actual = struct.unpack("<IIIII",code(pc,20))
        require(actual == (word,0x001022f3,0x00802373,0x00573023,0x00673423),
                f"ELF site {i+1}: opcode/immediate CSR pair/store changed")
        sites.append(dict(phase=i+1,pc=pc,word=f"{word:08x}"))
    require(sorted(custom) == sorted(s["pc"] for s in sites), "extra/missing custom instruction")
    source = symbols["source"]
    require(source["value"]%4096 == 0 and source["size"] == 1536, "source bounds/alignment differ")
    require(symbols["descriptor"]["value"]%64 == 0 and symbols["descriptor"]["size"] == 128,
            "descriptor bounds/alignment differ")
    for name in ("got","initial"):
        require(symbols[name]["value"]%64 == 0 and symbols[name]["size"] == 640, "frame layout differs")
    start = symbols["_start"]["value"]
    reset = code(start,symbols["trap_vector"]["value"]-start)
    mret = reset.find(bytes.fromhex("73002030"))
    require(mret >= 0, "missing CRT MRET")
    calls = []
    for off in range(0,mret-7,2):
        a,b = struct.unpack_from("<II",reset,off)
        if a&0xfff != 0x297 or b&0xfffff != 0x28293:
            continue
        high = a&0xfffff000
        high -= (1<<32) if high&0x80000000 else 0
        low = b>>20
        low -= 4096 if low&0x800 else 0
        if start+off+high+low == symbols["rvtest_init"]["value"]:
            require(reset[off+8:off+14] == bytes.fromhex("638302008292"), "CRT conditional hook call differs")
            calls.append(start+off)
    require(len(calls) == 1, "rvtest_init not called once before MRET")
    return dict(status="PASS",sites=sites,immediate_csr_pair=True,custom_sites=12,
        crt_hook_before_mret=calls[0],source_base=source["value"],source_bytes=source["size"],
        scope="ELF control/data layout only; execution remains pending")


def native_targets(proof):
    from reviewed_20261004.audit_readonly import Design, branch_index, tree_digest
    original = proof.read(ROOT / "verification/out/repaired-aligned-600-20260930-01/plan.json")
    bits = proof.read(BASE / "combined-bits.json")
    ledger = proof.read(BASE / "all-passed-outcomes.json")
    inputs = proof.pin(BASE / "combined-dve/inputs.txt").read_text().splitlines()
    proof.pin(BASE / "combined-dve/summary.csv")
    require(len(ledger) == len(bits["tests"]) == 640 and
            inputs == [original["design_vdb"], *bits["tests"]] and
            bits["tests"] == [r["vdb"] for r in ledger] and
            all(r["status"] == "PASS" and r["vdb_valid"] and not r["reused"] for r in ledger),
            "not the 640 independent PASS baseline")
    design = Design(original["design_vdb"])
    for rel, h in bits["design"].items():
        proof.pin(design.db / rel,h)
    for rel in ("auxiliary/verilog.sourceinfo.xml","shape/line.verilog.info.xml","shape/branch.verilog.info.xml","shape/tgl.verilog.shape.xml","shape/tgl.verilog.info.xml"):
        proof.pin(design.db / rel)
    manifest = proof.read(BUILD / "sim/vcs_source_manifest.json")
    frozen_sources = {f["path"]:f["sha256"] for f in manifest["files"]}
    points = [p for p in proof.read(ANALYSIS / "selected-candidate-points.json") if p["plan"] == "AKV"]
    require(len(points) == 9, "Plan A target count differs")
    for p in points:
        scope,metric = p["scope"],p["metric"]
        require(metric in ("line","branch"), "no inferred FSM IDs")
        d = design.definition(scope,metric)
        row = bits["metrics"][metric][scope]
        require(row["checksum"] == d.get("chksum") == p["definition"]["checksum"] and
                row["width"] == p["definition"]["width"] and
                tree_digest(d) == p["definition"]["definition_sha256"], "native definition differs")
        require(design.source(scope) == p["source"], "native source binding differs")
        proof.pin(p["source"]["resolved_path"],frozen_sources[p["source"]["resolved_path"]])
        if metric == "line":
            matches = [n for n in d.iter("linebb") if n.get("id") == p["xml"]["id"]]
            require(len(matches) == 1 and dict(matches[0].attrib) == p["xml"], "line mapping differs")
            index = int(matches[0].get("index"))
        else:
            index,base,width,spec = branch_index(d,p["spec"]["id"],p["vector"]["id"])
            require(dict(spec.attrib) == p["spec"] and base == p["spec_base"] and width == p["spec_width"] and
                    p["vector"] in [dict(v.attrib) for v in spec.findall("branch_vector")], "branch map differs")
        raw = format(int(row["bits"],16),f"0{row['width']}b")
        require(index == p["raw_index"] and raw[index] == "0" and p["hit_640"] == 0,
                "target is not a verified 0/640 gap")
    for rel in ("hardware/src/vlsu/vlsu.sv", "hardware/src/vlsu/qbs/qbs_read_engine.sv",
                "hardware/include/akv_pkg.sv", "hardware/src/ara_dispatcher.sv"):
        proof.pin(ROOT / rel,frozen_sources[str(ROOT / rel)])
    return dict(status="STATIC_CANDIDATES_ONLY",tests=640,design_vdb=original["design_vdb"],
        compiled_manifest=str(BUILD / "sim/vcs_source_manifest.json"),points=points,
        branch_mapping="reverse_within_each_branch_spec",fsm_claims=[],
        pending="Independent legal DUT PASS plus each raw hit required; no DVE percentage claim")


def native_runtime(vdb, targets, proof):
    from coverage_bitmap_delta import read_metric
    rows = {}
    for metric in ("line","branch"):
        paths = list(Path(vdb).glob(f"snps/coverage/db/testdata/*/{metric}.verilog.data.xml"))
        require(len(paths) == 1, "missing/ambiguous native metric")
        rows[metric] = read_metric(proof.pin(paths[0]))
    points = []
    for p in targets["points"]:
        row = rows[p["metric"]][p["scope"]]
        require(row["width"] == p["definition"]["width"] and
                row["checksum"] == p["definition"]["checksum"], "runtime native shape/checksum differs")
        bit = format(int(row["bits"],16),f"0{row['width']}b")[p["raw_index"]]
        points.append(dict(scope=p["scope"],metric=p["metric"],coordinate=p["coordinate"],
            raw_index=p["raw_index"],baseline=0,runtime=int(bit)))
    return dict(status="COMPLETE" if all(p["runtime"] for p in points) else "GAPS_RETAINED",
        points=points,new_target_hits=sum(p["runtime"] for p in points),fsm_claims=[])


def trace_audit(path, elf, log):
    pending, custom, retired, snapshots = {}, [], [], []
    snapshot_sites = {s["pc"]+off:(s["phase"],off) for s in elf["sites"] for off in (4,8)}
    reqs = resps = exceptions = last_cycle = 0
    with Path(path).open() as stream:
        for r in csv.DictReader(stream):
            cycle, event = int(r["cycle"]),r["event"]
            require(cycle >= last_cycle, "trace cycles regress")
            last_cycle = cycle
            insn,pc = int(r["insn"],16),int(r["pc"],16)
            if event == "cvx_req":
                key = int(r["trans_id"])
                require(key not in pending, "duplicate live request ID")
                pending[key] = (insn,cycle)
                reqs += 1
                if insn&127 == 91:
                    custom.append(dict(word=insn,request_cycle=cycle,id=key))
            elif event == "cvx_resp":
                key = int(r["trans_id"])
                require(key in pending, "orphan response")
                word,start = pending.pop(key)
                fault = int(r["trap"])
                resps += 1
                exceptions += fault
                if word&127 == 91:
                    matches = [x for x in custom if x["id"] == key and x["request_cycle"] == start]
                    require(len(matches) == 1, "ambiguous custom request identity")
                    matches[0].update(response_cycle=cycle,fault=fault)
                else:
                    require(fault == 0, "noncustom vector exception")
            elif event == "retire":
                if insn&127 == 91:
                    retired.append((pc,insn,int(r["trap"])))
                if pc in snapshot_sites:
                    phase,off = snapshot_sites[pc]
                    snapshots.append(dict(phase=phase,offset=off,cycle=cycle,
                        insn=insn,value=int(r["rd_wdata"],16),trap=int(r["trap"])))
    require(not pending and reqs == resps and reqs >= 12 and exceptions == 3, "protocol conservation differs")
    require([x["word"] for x in custom] == WORDS and
            [x.get("fault") for x in custom] == [int(4 <= i <= 6) for i in range(12)],
            "custom request/outcome sequence differs")
    require(retired == [(s["pc"],WORDS[i],0) for i,s in enumerate(elf["sites"]) if not 4 <= i <= 6],
            "successful custom retirement/ELF binding differs")
    require(len(snapshots) == 24, "CSR retirement count differs")
    for i,s in enumerate(snapshots):
        phase,off = i//2+1,4 if i%2 == 0 else 8
        require(s["phase"] == phase and s["offset"] == off and s["trap"] == 0 and
                s["insn"] == (0x001022f3 if off == 4 else 0x00802373) and
                s["value"] == (21 if off == 4 else 0) and
                s["cycle"] >= custom[phase-1]["response_cycle"], "immediate CSR retirement differs")
    contract = re.findall(r"(?m)^\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+) mmu_request_cycles=(\d+) protocol_errors=(\d+) outstanding=(\d+) req_stalled=([01]) resp_stalled=([01])$",log)
    require(len(contract) == 1, "missing/ambiguous protocol summary")
    counts = list(map(int,contract[0]))
    require(counts[:3] == [reqs,resps,3] and counts[4:] == [0,0,0,0], "protocol summary differs from trace")
    return dict(status="PASS",requests=reqs,responses=resps,exceptions=exceptions,
        last_cycle=last_cycle,custom=custom,snapshots=snapshots,
        scope="No FENCE.T/reset; serial per-ID request/response, successful retire PCs and immediate CSR reads")
