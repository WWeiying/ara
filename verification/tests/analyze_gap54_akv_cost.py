#!/usr/bin/env python3
"""Snapshot existing evidence and bound scalar helper instruction costs; no RTL run."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "verification/coverage"))
import gap54_akv_oracle as o

OLD = ROOT / "verification/out/gap46-akv-preflight-20261004-03"
ARTIFACT = ROOT / "verification/out/gap48-current-20261004-01/results/akv_gap46_skew_context/tests/app_akv_gap46_skew_context"


def snapshot(source, dest):
    before = source.stat()
    with source.open("rb") as stream:
        data = stream.read(before.st_size)
    # A live writer can leave an incomplete last record. Never parse that tail.
    data = data[:data.rfind(b"\n")+1]
    dest.write_bytes(data)
    after = source.stat()
    return dict(source=str(source),snapshot=str(dest),bytes=len(data),sha256=o.sha(dest),
        source_size_before=before.st_size,source_size_after=after.st_size,
        mtime_ns_before=before.st_mtime_ns,mtime_ns_after=after.st_mtime_ns,
        scope="complete-line prefix snapshot only; not a terminal verdict")


def instructions(path):
    rows = []
    for line in path.read_text().splitlines():
        m = re.match(r"^([0-9a-f]+):\s+(?:[0-9a-f]{8}|[0-9a-f]{4}|(?:[0-9a-f]{2} ){3}[0-9a-f]{2})\s+([a-z0-9_.]+)\s*(.*)$",line)
        if m:
            rows.append(dict(pc=int(m[1],16),op=m[2],args=m[3]))
    return rows


def function_bound(rows, symbols, name, iterations):
    symbol = symbols[name]
    start,end = symbol["Value"],symbol["Value"]+symbol["Size"]
    body = [r for r in rows if start <= r["pc"] < end]
    o.require(body,"missing bounded helper: "+name)
    loops = []
    for r in body:
        if r["op"].startswith("b") or r["op"] == "j":
            target = re.search(r"0x([0-9a-f]+)",r["args"])
            if target and start <= int(target[1],16) <= r["pc"]:
                loops.append(dict(start=int(target[1],16),end=r["pc"],iterations=iterations))
    # Loop bounds are fixed by source: diff<=64, seed80, source setup192,
    # poison96, and at most2*3 compare visits. Nested loops multiply, not add.
    upper = 0
    for r in body:
        visits = 1
        for loop in loops:
            if loop["start"] <= r["pc"] <= loop["end"]:
                visits *= iterations
        upper += visits
    return dict(name=name,start=start,end=end,static_instructions=len(body),loops=loops,
        local_instructions_upper=upper,call_bodies_excluded=True)


def analyze(out):
    snapshots = [snapshot(ARTIFACT / "commit_trace.csv",out / "gap46-trace-prefix.csv"),
                 snapshot(ARTIFACT / "work/run.vcs.log",out / "gap46-log-prefix.log")]
    commands = {}
    for name in ("gap46-command.json","coverage.command.json"):
        source = ARTIFACT / "work" / name
        commands[name] = o.read(source)
        o.require(commands[name]["command"].count("+AKV_PERF") == 1,"actual AKV_PERF not enabled")
    o.save(out / "gap46-command-snapshot.json",commands)
    retired,custom,pc_hist = [],[],Counter()
    for r in csv.DictReader((out / "gap46-trace-prefix.csv").open()):
        if r["event"] != "retire":
            continue
        pc,word = int(r["pc"],16),int(r["insn"],16)
        retired.append((int(r["cycle"]),pc,word))
        pc_hist[pc] += 1
        if word&127 == 91:
            custom.append(dict(cycle=int(r["cycle"]),pc=pc,word=f"{word:08x}",retired_ordinal=len(retired)))
    old_rows = instructions(OLD / "akv_gap46_skew_context.disassembly.log")
    source_loop = [r for r in old_rows if 0x8000097e <= r["pc"] <= 0x80000a04]
    source_loop_count = sum(pc_hist[r["pc"]] for r in source_loop)
    o.require(len(custom) >= 4,"snapshot lacks four completed custom retires")
    intervals = []
    for previous,current in zip(custom,custom[1:]):
        intervals.append(dict(from_cycle=previous["cycle"],to_cycle=current["cycle"],
            cycles=current["cycle"]-previous["cycle"],
            retired_instructions=current["retired_ordinal"]-previous["retired_ordinal"]))
    perf = []
    log = (out / "gap46-log-prefix.log").read_text()
    for line in log.splitlines():
        if line.startswith("[AKV_PERF] "):
            row = {k:int(v) for k,v in (s.split("=") for s in line.split()[1:])}
            o.require(set(row) == set(o.PERF_KEYS),"actual PERF schema differs")
            o.require(all(row[k] == v for k,v in o.expected_perf(len(perf)).items()),"observed PERF semantics differ")
            perf.append(row)
    o.require(len(perf) >= 4 and [r["busy_cycles"] for r in perf[1:4]] == [13,13,13],"ROW hardware witness differs")
    metadata = o.read(out / (o.NAME+".metadata.log"))[0]
    syms = {r["Symbol"]["Name"]["Name"]:r["Symbol"] for r in metadata["Symbols"]}
    rows = instructions(out / (o.NAME+".disassembly.log"))
    bounds = {n:function_bound(rows,syms,n,bound) for n,bound in
              (("gap54_diff64",64),("compare",6),("seed",80),("setup",192),("poison",96))}
    # Clang recognizes setup/seed copies as calls to the frozen common memcpy.
    # Count the callees, including their alignment test, rather than pretending
    # the caller's straight-line instruction count includes the copy work.
    memcpy = function_bound(rows,syms,"memcpy",1)
    mem_body = [r for r in rows if memcpy["start"] <= r["pc"] < memcpy["end"]]
    word_loops = [loop for loop in memcpy["loops"] if
                  any(r["op"] == "ld" and loop["start"] <= r["pc"] <= loop["end"] for r in mem_body)]
    o.require(len(word_loops) == 1,"memcpy word loop differs")
    loop = word_loops[0]
    copy_width = sum(loop["start"] <= r["pc"] <= loop["end"] for r in mem_body)
    o.require(copy_width == 6,"unexpected aligned memcpy iteration")
    for name in ("source","source_expected","initial","got","source_reference","frame_reference"):
        o.require(syms[name]["Value"]%64 == 0,"unaligned memcpy path: "+name)
    def copy_calls(name, words):
        body = [r for r in rows if bounds[name]["start"] <= r["pc"] < bounds[name]["end"]]
        calls = [r for r in body if "<memcpy>" in r["args"]]
        o.require(len(calls) == 2,"expected two complete copies: "+name)
        extra = 2*(copy_width*words + memcpy["static_instructions"]-copy_width)
        bounds[name]["memcpy_word_count_per_call"] = words
        bounds[name]["memcpy_calls"] = 2
        bounds[name]["memcpy_instructions_upper"] = extra
        bounds[name]["local_instructions_upper"] += extra
        bounds[name]["call_bodies_excluded"] = False
    copy_calls("setup",192)
    copy_calls("seed",80)
    # 15 difference calls:16+48+64+4*8+6*32+2*8=368 word pairs.
    diff = bounds["gap54_diff64"]
    o.require(len(diff["loops"]) == 1,"diff helper must have exactly one simple loop")
    loop = diff["loops"][0]
    loop_width = sum(loop["start"] <= r["pc"] <= loop["end"] for r in rows)
    diff_total = loop_width*368 + (diff["static_instructions"]-loop_width)*15
    compare_upper = bounds["compare"]["local_instructions_upper"]+diff_total
    # Includes a poison on every phase (only two actually execute it), but not
    # printf/trap/CRT/custom latency. This is static instruction work, not cycles.
    phase_upper = compare_upper+bounds["seed"]["local_instructions_upper"]+bounds["poison"]["local_instructions_upper"]
    o.require(phase_upper < 12000,"scalar phase cost not sufficiently reduced")
    proof = dict(status="STATIC_COST_REDUCED_NOT_RUNTIME_PASS",timestamp_utc=datetime.now(timezone.utc).isoformat(),
        snapshots=snapshots,commands=commands,
        old_trace=dict(retired=len(retired),last_cycle=retired[-1][0],last_pc=hex(retired[-1][1]),custom=custom,
            intervals=intervals,source_loop_retired=source_loop_count,
            source_loop_fraction=source_loop_count/len(retired),source_loop=source_loop),
        actual_perf_prefix=perf,perf_prefix_validated=True,
        perf_correction=dict(field="translations",old_static_assumption=">=4 for FULL",actual=0,new_required=0,
            evidence="qbs_read_engine.sv:240-246,658-661: translation_complete requires en_ld_st_translation_i; bare addressing bypasses MMU"),
        new_cost=dict(functions=bounds,diff_loop_instructions=loop_width,word_pairs_per_phase=368,
            diff_calls_per_phase=15,comparison_instructions_upper=compare_upper,
            phase_instructions_upper=phase_upper,setup_instructions_upper=bounds["setup"]["local_instructions_upper"],
            total_scalar_instructions_upper=bounds["setup"]["local_instructions_upper"]+12*phase_upper,
            memcpy=memcpy,memcpy_aligned_loop_instructions=copy_width,
            scope="Conservative scalar helper PASS-path bound including memcpy; excludes printf/CRT/traps/custom and memory latency; not wall time"),
        frozen_inputs={str(p):o.sha(p) for p in (OLD / ("akv_gap46_skew_context.elf"),
            OLD / "akv_gap46_skew_context.disassembly.log",ROOT / "apps/akv_gap46_skew_context/main.c",
            ROOT / "hardware/src/vlsu/qbs/qbs_read_engine.sv")},
        conclusion="CPU checker pattern regeneration dominates observed gaps; observed ROWs terminate in13 busy cycles; no RTL stall fix indicated",
        falsifier="If successor command request-to-terminal busy cycles grow while scalar retired helper cost falls, investigate a separate hardware stall; do not infer full-run correctness from this prefix",
        vcs_launched=False,timeout_s=600,terminal_verdict_claim=False)
    o.save(out / "cost-analysis.json",proof)
    print(json.dumps(dict(old_retired=len(retired),old_source_loop_retired=source_loop_count,
        compare_upper=compare_upper,phase_upper=phase_upper,setup_upper=bounds["setup"]["local_instructions_upper"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build",required=True,type=Path)
    analyze(parser.parse_args().build.resolve())
