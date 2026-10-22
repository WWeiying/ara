#!/usr/bin/env python3
"""Read-only raw GAP83 acceptance into a fresh sidecar. Never starts VCS/DVE."""
import argparse
import json
from pathlib import Path

import run_gap83_old_image as g

RAW = g.OUT/"gap83-midmant-old-image-20261006-01"
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name("test_recheck_gap83_old_image.py")
ELF_SHA = "302adc8bc67502a9c4a94d52ef07afb89c914a2e4b26d7e11bf9a3e14d414c9f"


def comparison_gate(scalar,vector):
    g.require(scalar["status"] == "TERMINAL_TOHOST_MATCH" and scalar["ara_trap_events"] == 0
        and scalar["skipped_unobservable_register_values"] == 0 and scalar["stopped_at_unobservable"] is None
        and scalar["matched_instructions"] == scalar["ara_retired_instructions"],"Incomplete scalar comparison")
    g.require(vector["status"] == "PASS" and vector["selected_index"] is None
        and vector["stopped_at_spike_index"] is None
        and vector["prefix_vector_destination_requests"] == vector["vector_destination_requests"] == vector["compared_instructions"]
        and vector["skipped_unknown_bytes"] == vector["non_bit_exact_instructions"] == vector["unobservable_instructions"] == 0
        and not any(vector[k] for k in ("incomplete_requests","unretired_requests","trapped_requests")),
        "Incomplete/nonexact vector comparison for this tu/mu fixture")


def accept(output):
    output = output.absolute()
    g.require(not output.exists() and output.parent == g.OUT,"Fresh sidecar required")
    seal = g.seals.FileSeal()
    state = seal.read(RAW/"simulation-status.json")
    g.require(state == dict(status="SIMULATION_EXITED_NOT_ADMITTED",returncode=0,coverage_admitted=False),
              "Successful raw process required; no failed-run reinterpretation")
    raw = seal.read(RAW/"manifest.json")
    g.require(raw["coverage_admitted"] is False and raw["rtl_changed"] is False and raw["timeout_s"] == 600,"Wrong raw context")
    seal.hashes(raw["pins"])
    plan = seal.read(g.OUT/"closure90-current-20261005-01/plan.json")
    g.require(all(raw["pins"].get(p) == d for p,d in plan["image"].items()),"Old image pins differ")
    elf = seal.pin(g.PREFLIGHT/"input.elf",ELF_SHA)
    readelf = Path("/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-readelf")
    seal.pin(readelf)
    tohost = g.h._elf_symbol(elf,readelf,"tohost")
    result = g.h._elf_symbol(elf,readelf,"g75_result")
    expected = [plan["simv"],"-l","run.vcs.log","+NO_FSDB","+ntb_random_seed=1",
        "+PRELOAD="+str(elf),"+TESTCASE="+g.NAME,"+COMMIT_TOHOST=%x"%tohost,
        "+COMMIT_TRACE="+str(RAW/"commit_trace.csv"),"+VECTOR_TRACE="+str(RAW/"vector_trace.csv"),
        "-cm","line+cond+fsm+tgl+branch","-cm_dir",str(RAW/"code.vdb"),"-cm_name",g.NAME]
    g.require(raw["command"] == expected,"Raw command differs from exact old-image case")
    for p in (SCRIPT,TEST,Path(g.__file__),Path(g.h.__file__),Path(g.lzc.__file__),Path(g.seals.__file__),
        Path(g.seals.bitmaps.__file__),g.SOURCE,g.RETAINED,
        *[g.ROOT/"verification/ara_verify"/n for n in ("spike_trace.py","vector_commit.py","trace.py","contract.py","random_rvv.py")],
        *[RAW/n for n in ("commit_trace.csv","vector_trace.csv","run.vcs.log","console.log")]):seal.pin(p)
    before = seal.read(g.BASELINE/"combined-bits.json")
    provenance = seal.read(g.BASELINE/"provenance.json")
    g.require(provenance["status"] == "RAW_DIAGNOSTIC_UNION_COMPLETE" and provenance["historical_tests"] == 689,"Wrong baseline")
    seal.hashes(provenance["outputs"])
    ts = g.targets(seal.read(g.RETAINED))
    g.require(all(g.bit(before,p) == 0 for p in ts),"Targets not historical zeros")
    commits = g.h.parse_spike_commits(g.PREFLIGHT/"spike.trace")
    g.require(len(commits) == 5000 and sum(c.instruction == 0xc2821857 for c in commits) == 2,"Wrong Spike population")
    g.signature({addr:value for c in commits for addr,value in c.memory_accesses if value is not None},tohost,result)
    trace = g.h.validate_trace(RAW/"commit_trace.csv")
    scalar = g.h.compare_commit_prefix(g.PREFLIGHT/"spike.trace",RAW/"commit_trace.csv",0x80000000,
        terminal_tohost_address=tohost,rvfi_store_data_layout="unshifted")
    vector = g.h.compare_vector_commits(g.PREFLIGHT/"spike.trace",RAW/"commit_trace.csv",RAW/"vector_trace.csv",0x80000000)
    comparison_gate(scalar,vector)
    retired = g.parse_ara_retire(RAW/"commit_trace.csv")
    g.require(sum(r.instruction == 0xc2821857 for r in retired) == 2,"Wrong DUT vfwadd count")
    writes = {r.mem_addr:g._packed_store_value(r.mem_wmask,r.mem_wdata,"unshifted")
              for r in retired if r.mem_wmask and r.mem_wdata is not None}
    g.signature(writes,tohost,result)
    g.require(not g.h.check_contract_log(RAW/"run.vcs.log") and
              "Core Test *** SUCCESS ***" in (RAW/"run.vcs.log").read_text(),"DUT/contract failed")
    seal.tree(RAW/"code.vdb")
    output.mkdir()
    try:
        g.save(output/"scalar-comparison.json",scalar)
        g.save(output/"vector-comparison.json",vector)
        with (output/"new-inputs.txt").open("x") as stream:
            stream.write(plan["design_vdb"]+"\n"+str(RAW/"code.vdb")+"\n")
        sample = g.seals.bitmaps.collect(output/"new-inputs.txt")
        g.require(sample["tests"] == [str(RAW/"code.vdb")],"Foreign VDB population")
        g.lzc.assert_zero(sample,seal.read(g.lzc.capture.CANDIDATES)["candidates"])
        after = g.seals.bitmaps.combine(before,sample)
        measured = [dict(scope=p["scope"],raw_index=p["raw_index"],vector=p["vector"],
            before=g.bit(before,p),single=g.bit(sample,p),after=g.bit(after,p)) for p in ts]
        g.save(output/"target-measurement.json",dict(targets=measured,all_targets_hit=all(p["single"] == 1 for p in measured)))
        g.save(output/"new-bits.json",sample)
        g.save(output/"raw-bitmap-delta.json",g.seals.bitmaps.delta(before,after))
        g.save(output/"runtime-audit.json",dict(status="PASS",trace=trace,checks=262,failures=0,
            vfwadd_instructions=2,signature_address=result,tohost_address=tohost,
            VL_fflags_vstart="fixture selfcheck plus full scalar/vector comparison",simulation_rerun=False))
        seal.hashes(sample["input_hashes"])
        seal.finish()
        artifacts = {str(p):g.seals.sha_bytes(p.read_bytes()) for p in output.iterdir() if p.is_file()}
        g.save(output/"evidence-pins.json",dict(inputs=seal.files,artifacts=artifacts))
        status = dict(status="PASS_SINGLE_CASE_DIAGNOSTIC",checks=262,failures=0,
            all_targets_hit=all(p["single"] == 1 for p in measured),historical_only=True,
            aggregate_admitted=False,dve_run=False,waivers_applied=False,new_RTL_signoff=False,simulation_rerun=False)
        g.save(output/"status.json",status)
        return status
    except Exception as error:
        g.save(output/"status.json",dict(status="FAIL",reason=f"{type(error).__name__}: {error}",aggregate_admitted=False))
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    print(json.dumps(accept(p.parse_args().output),indent=2))
