"""Successor: exact VSET result and complete terminal contract fields; no admission."""
import check_akv_lifecycle_offline as predecessor
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

import akv_lifecycle_scalar_oracle as oracle

base, runner, fixture = oracle.base, oracle.runner, oracle.fixture
native, life, require = base.native, base.life, base.require
RUN = life.OUT/"akv-lifecycle-old-image-parent-20261006-01"
RUN_SEAL = "e3acf310ba9d2a1b0d260c3052ccc2fcd67be27bd5efbde4125a930f3ae6c951"


def terminal_status(status):
    expected=dict(status="SIMULATION_EXITED_NOT_ADMITTED",returncode=0,case=runner.NAME,
                  coverage_admitted=False,native_oracle_qualified=False,full_scalar_independent_qualified=False)
    require(set(status) == set(expected) and all(type(status[k]) is type(v) and status[k] == v
                                                for k,v in expected.items()), "Failed/nonterminal run")


def commit_audit(rows, model):
    starts, pending, responses, allocations, done, active = {}, {}, {}, {}, {}, {}
    commands = []
    expectations = model.requests
    backend = [r for r in expectations if r["word"]&127 in (7,0x27,0x5b)]
    for row in rows:
        event, seq = row["event"], row["order"]
        if event == "arch_start":
            i = len(starts)
            require(i < len(expectations) and seq not in starts and row["insn"] == expectations[i]["word"],
                    "Foreign/missing/reordered architectural request")
            starts[seq] = dict(row, expectation=expectations[i])
        elif event == "cvx_req":
            candidates = [s for s in starts.values() if s["trans_id"] == row["trans_id"] and
                          s["insn"] == row["insn"] and s["order"] not in responses and
                          s["order"] not in {p["order"] for p in pending.values()}]
            require(len(candidates) == 1 and row["trans_id"] not in pending and
                    candidates[0]["cycle"] <= row["cycle"], "Unbound/duplicate CVX request")
            pending[row["trans_id"]] = dict(candidates[0],request_cycle=row["cycle"])
        elif event == "cvx_resp":
            require(row["trans_id"] in pending, "Orphan CVX response")
            s = pending.pop(row["trans_id"]); key=s["order"]
            require(key not in responses and s["request_cycle"] <= row["cycle"], "Duplicate/early response")
            op = s["insn"]&127
            fault = False
            if op == 0x5b:
                phase = len(commands)
                require(phase < 10 and s["insn"] == model.commands[phase]["word"], "Custom order")
                fault = model.commands[phase]["fault"]
                commands.append(dict(model.commands[phase],seq=key,response_cycle=row["cycle"]))
            require(row["trap"] == int(fault), "Unexpected/missing CVX exception")
            expected_value = s["expectation"]["response_value"]
            require(row["rd_wdata"] == expected_value, "CVX response data differs")
            responses[key] = row
        elif event in ("uop_alloc","uop_done"):
            require(seq in starts and row["insn"] == starts[seq]["insn"] and
                    row["trans_id"] == starts[seq]["trans_id"] and 0 <= row["port"] < 8 and
                    starts[seq]["cycle"] <= row["cycle"] and row["rd_wdata"] == 0,
                    "Unbound backend event")
            vid = row["port"]
            if event == "uop_alloc":
                require(seq not in allocations and vid not in active and row["insn"]&127 in (7,0x27,0x5b),
                        "Duplicate/live/foreign backend allocation")
                allocations[seq] = row; active[vid] = seq
            else:
                require(seq in allocations and seq not in done and active.get(vid) == seq and
                        allocations[seq]["cycle"] <= row["cycle"], "Orphan/early/duplicate backend done")
                done[seq] = row; del active[vid]
    require(len(starts) == len(expectations) == 426 and len(responses) == 426 and not pending and
            not active and set(allocations) == set(done) and
            [r["insn"] for r in allocations.values()] == [r["word"] for r in backend] and len(commands) == 10,
            "Incomplete frontend/backend lifecycle")
    probes = [r for r in rows if r["event"] == "retire" and r["insn"]&127 == 0x73 and
              r["insn"]>>20 in (1,8,0xc20,0xc21,10,9) and r["insn"]>>12&7 == 2 and r["insn"]>>15&31 == 0]
    vsets = [r for r in rows if r["event"] == "retire" and r["insn"] == 0x0082f057]
    require(len(probes) == 60 and len(vsets) == 11, "Missing CSR frames/VSET")
    for p, command in enumerate(commands):
        frame=probes[p*6:(p+1)*6];seq=command["seq"]
        require([r["insn"]>>20 for r in frame] == [1,8,0xc20,0xc21,10,9] and
                [r["rd_wdata"] for r in frame] == [21,0,64,8,2,1] and all(r["rd"] for r in frame) and
                max(command["response_cycle"],done[seq]["cycle"]) <= frame[0]["cycle"] and
                frame[-1]["cycle"] < vsets[p+1]["cycle"], "CSR observation outside completed-command boundary")
    return dict(commands=commands,starts=starts,allocations=allocations,done=done,
                requests=426,exceptions=4,CSR_readbacks=60)


def vector_audit(rows, model, arch):
    require(rows and rows[0]["event"] == "config" and int(rows[0]["nr_lanes"]) == 4 and
            int(rows[0]["vlen_bits"]) == 1024 and sum(r["event"] == "config" for r in rows) == 1 and
            all(int(r["nr_lanes"]) == 4 and int(r["vlen_bits"]) == 1024 for r in rows),
            "Wrong/missing native vector configuration")
    require(all(int(rows[0][k],16 if k in ("insn","be","wdata") else 10) == 0 for k in
                ("cycle","arch_seq","vid","lane","source","insn","use_vd","vd","eew","vl","vstart","addr","be","wdata")),
            "Foreign configuration metadata")
    expected = {}
    seeds = [s for s,r in arch["allocations"].items() if r["insn"]&127 == 7]
    for effect in model.vector_effects:
        seq = seeds[effect["vd"]] if effect["kind"] == "seed" else arch["commands"][effect["phase"]]["seq"]
        expected[seq] = {(effect["vd"],i):v for i,v in enumerate(bytes.fromhex(effect["data"]))}
    accepted = {s:{} for s in expected}
    metadata, mirrors, active, previous = {}, {}, {}, -1
    command_seq = {c["seq"]:c for c in arch["commands"]}
    for r in rows[1:]:
        require(r["event"] in ("alloc","done","write"), "Unknown native vector event")
        cycle, seq, vid = int(r["cycle"]), int(r["arch_seq"]), int(r["vid"])
        word = int(r["insn"],16)
        meta = tuple(int(r[k]) for k in ("use_vd","vd","eew","vl","vstart"))
        require(cycle >= previous and seq in arch["allocations"] and word == arch["allocations"][seq]["insn"] and
                vid == arch["allocations"][seq]["port"] and 0 <= int(r["source"]) < 5, "Native lifecycle identity")
        previous = cycle
        if r["event"] in ("alloc","done"):
            require(all(int(r[k],16 if k in ("be","wdata") else 10) == 0
                        for k in ("lane","source","addr","be","wdata")), "Lifecycle side effects")
            event="uop_alloc" if r["event"] == "alloc" else "uop_done"
            reference=arch["allocations"] if r["event"] == "alloc" else arch["done"]
            require((event,seq) not in mirrors and cycle == reference[seq]["cycle"], "Vector/commit mirror mismatch")
            mirrors[event,seq] = True
            if r["event"] == "alloc":
                require(seq not in metadata and vid not in active, "Duplicate/live vector allocation")
                op = word&127
                if op == 0x5b:
                    phase = command_seq[seq]["phase"]
                    use = int(phase in (5,8))
                    require(meta[0] == use and meta[2:] == (1,96 if phase == 5 else 64 if use else 1,0) and
                            (not use or meta[1] == 8), "Custom reservation metadata")
                else:
                    require(meta[0] == int(op == 7) and meta[2:] == (1,64,0) and
                            (op != 7 or meta[1] == word>>7&31), "Vector memory metadata")
                metadata[seq] = meta;active[vid] = seq
            else:
                require(metadata.get(seq) == meta and active.get(vid) == seq, "Orphan/mutated vector done")
                del active[vid]
        else:
            require(metadata.get(seq) == meta and cycle >= arch["allocations"][seq]["cycle"] and
                    cycle <= arch["done"][seq]["cycle"] and seq in expected,
                    "Unexpected/rejected/late VRF writer")
            lane, addr, be, data = int(r["lane"]),int(r["addr"]),int(r["be"],16),int(r["wdata"],16)
            require(0 <= lane < 4 and 0 < be < 256 and 0 <= data <= oracle.MASK and
                    int(r["source"]) == 4, "Foreign writer/zero-enable grant")
            reg, chunk = divmod(addr,4)
            for byte in range(8):
                if not be>>byte&1: continue
                slot,within=divmod(byte,2);natural=((slot&1)<<1)|(slot>>1)
                key=(reg,chunk*32+(natural*4+lane)*2+within)
                require(key in expected[seq] and key not in accepted[seq] and
                        data>>(byte*8)&255 == expected[seq][key], "Independent native byte mismatch/neighbor write")
                accepted[seq][key] = expected[seq][key]
    require(not active and set(metadata) == set(arch["allocations"]) and
            len(mirrors) == 2*len(metadata) and accepted == expected, "Incomplete native roundtrip/effects")
    return dict(status="NATIVE_BYTES_BOUND_TO_INDEPENDENT_MODEL",seed_bytes=4096,custom_write_bytes=128,
                snapshot_stores=320,rejected_write_bytes=0,backend_mirror_complete=True)


def stdout_audit(log):
    require(not re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b|Error:|Fatal:|Assertion\b)|\$fatal",log), "Runtime failure")
    require(log.count("Core Test *** SUCCESS ***") == 1 and
            len(re.findall(r"^\$finish at simulation time\s+\d+",log,re.M)) == 1 and
            log.count('$finish called from file "'+str(life.ROOT/"hardware/tb/ara_commit_monitor.sv")+'", line 270.') == 1,
            "Incomplete/nonunique monitor terminal")
    for level in ("ERROR","FATAL"):
        lines=re.findall(r"^\s*UVM_"+level+r"\b[^\n]*",log,re.M)
        require(len(lines) <= 1 and all(re.fullmatch(r"\s*UVM_"+level+r"\s*:\s*0\s*",l) for l in lines),
                "Actual UVM error/fatal")
    lines=[l for l in log.splitlines() if l.startswith("[ARA_CONTRACT]")]
    require(len(lines) == 1, "Missing/duplicate terminal contract")
    keys=("requests","responses","exceptions","mmu_request_cycles","protocol_errors",
          "outstanding","req_stalled","resp_stalled")
    fields=[re.fullmatch(r"([a-z_]+)=([0-9]+)",t) for t in lines[0].split()[1:]]
    require(all(fields) and tuple(m[1] for m in fields) == keys, "Incomplete/foreign/duplicate contract fields")
    contract={m[1]:int(m[2]) for m in fields}
    # These are terminal valid&&!ready flags, not cumulative backpressure cycles.
    require(contract == dict(requests=426,responses=426,exceptions=4,mmu_request_cycles=0,
            protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0), "Incomplete native contract")
    return contract


def perf_audit(log, arch, model):
    lines=[l for l in log.splitlines() if l.startswith("[AKV_PERF] ")]
    require(len(lines) == 10,"Incomplete native PERF ledger")
    commands=[3,5,4,1,0,2,1,0,2,3]
    result=[]
    for phase,line in enumerate(lines):
        fields=[re.fullmatch(r"([a-z_][a-z_0-9]*)=([0-9]+)",t) for t in line.split()[1:]]
        require(all(fields) and len(fields) == len(native.legacy.PERF_KEYS),"Malformed native PERF")
        row={m[1]:int(m[2]) for m in fields}
        require(set(row) == set(native.legacy.PERF_KEYS),"Duplicate/foreign PERF keys")
        c=model.commands[phase];full=phase in (2,4,7)
        expected=dict(seq=phase+1,command=commands[phase],success=int(not c["fault"]),
            fault=int(c["fault"]),validation_fault=int(c["fault"]),validation_error=c["validation_error"],
            read_fault=0,context_ready=int(c["context_ready_after"]),full=int(phase in (4,7)),
            refill=int(phase in (3,6)),load=int(phase in (5,8)),release=int(phase in (0,9)),
            v2_full=int(phase == 2),v2_refill=int(phase == 1),v2_row_load=0,v2_column_load=0,
            v2_column_panel=0,v2_logical_column=0,v2_bank_conflict_cycles=0,v2_rejected=int(phase == 1),
            q_external_bytes=128 if full else 0,kv_external_bytes=256 if full else 0,
            replay_bytes=128 if phase == 8 else 0,read_ranges=4 if full else 0,
            translations=0,read_payload_bytes=448 if full else 0)
        require(all(row[k] == v for k,v in expected.items()) and row["busy_cycles"] > 0 and
                row["id"] == arch["allocations"][arch["commands"][phase]["seq"]]["port"],
                "Native PERF lifecycle/data/VID mismatch")
        if not full: require(row["ar"] == row["r_beats"] == 0,"Unexpected native external read")
        result.append(row)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True)
    out=p.parse_args().output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    manifest=life.read_bound(RUN/"manifest.json",RUN_SEAL)
    require(life.read_bound(RUN.with_name(RUN.name+".prepared.json"),RUN_SEAL) == manifest, "Executed/prepared drift")
    runner.validate(manifest["preflight"],runner.PRE)
    require(manifest["command"] == runner.command(manifest["preflight"],RUN) and manifest["timeout_s"] == 600,
            "Wrong parent600 command")
    terminal_status(json.loads((RUN/"simulation-status.json").read_text()))
    pins=dict(manifest["pins"])
    files=[RUN/"manifest.json",RUN.with_name(RUN.name+".prepared.json"),RUN/"simulation-status.json",
           RUN/"console.log",RUN/"run.vcs.log",RUN/"commit_trace.csv",RUN/"vector_trace.csv",
           Path(__file__).resolve(),Path(__file__).with_name("test_check_akv_lifecycle_offline.py"),
           Path(oracle.__file__).resolve(),Path(oracle.__file__).with_name("test_akv_lifecycle_scalar_oracle.py")]
    files+=list((life.ROOT/"verification/ara_verify").rglob("*.py"))
    vdb=RUN/"code.vdb"
    require(vdb.is_dir() and vdb.resolve() == vdb and not any(p.is_symlink() for p in vdb.rglob("*")), "Missing/aliased VDB")
    members=sorted(p for p in vdb.rglob("*") if p.is_file());require(members,"Empty VDB")
    files+=members
    for module in list(sys.modules.values()):
        name=getattr(module,"__file__",None)
        if name and Path(name).resolve().parent == Path(__file__).resolve().parent: files.append(Path(name).resolve())
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    sources_path=fixture.BUILD/"build-source-pins.json"
    sources=life.read_bound(sources_path,pins[str(sources_path)])
    pins,source_proof=base.source_contract(sources,pins)
    life.check(pins)
    out.mkdir()
    try:
        require((RUN/"console.log").read_text().count("Core Test *** SUCCESS ***") == 1,"Console terminal missing")
        rows=native.commit_rows(RUN/"commit_trace.csv")
        pre=manifest["preflight"]
        model,scalar=oracle.replay(Path(pre["input_elf"]).read_bytes(),pre["symbols"],rows)
        arch=commit_audit(rows,model)
        vector=vector_audit(native.common.read_csv(RUN/"vector_trace.csv",native.common.VECTOR_FIELDS),model,arch)
        contract=stdout_audit((RUN/"run.vcs.log").read_text())
        perf=perf_audit((RUN/"run.vcs.log").read_text(),arch,model)
        require(sorted(str(p) for p in vdb.rglob("*") if p.is_file()) == [str(p) for p in members],"VDB membership drift")
        life.check(pins)
        for name,value in (("scalar-qualification.json",scalar),("native-vector.json",vector),
                           ("architecture.json",arch),("source-contract.json",source_proof),("contract.json",contract),
                           ("perf-ledger.json",perf)):
            life.save(out/name,value)
        life.save(out/"qualification-seal.json",dict(status="NATIVE_AND_SCALAR_QUALIFIED_NOT_ADMITTED",
            run=str(RUN),run_seal=RUN_SEAL,input_pins=pins,output_pins={str(p):life.digest(p) for p in out.iterdir()},
            coverage_admitted=False,minimum_future_formal_baseline=722,requires_fresh_positive_delta=True,
            native_Spike_comparison=False))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/"qualification-seal.json"))))
    except Exception as e:
        life.save(out/"failure.json",dict(status="QUALIFICATION_REJECTED_NOT_ADMITTED",reason=str(e)))
        raise


if __name__ == "__main__": main()
