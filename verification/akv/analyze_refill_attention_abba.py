#!/usr/bin/env python3
"""Attribute the sealed Attention ABBA using existing retirement/write traces.

Retirement gaps are charged to the next retired PC for diagnosis. These are
not exclusive hardware stall causes. Actual older-FMA/write overlap is kept
separate from whole-operator cycles and scalar retirement accounting.
"""
import argparse
from bisect import bisect_right
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_half_scale_soc import hashes, digest
from run_refill_attention_abba import check_log

NM = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-nm")
OBJDUMP = NM.with_name("riscv64-unknown-elf-objdump")


def symbol_table(elf):
    table = []
    for line in subprocess.check_output([str(NM), "-S", "-n", str(elf)], text=True).splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[2] in ("T", "t"):
            table.append((int(fields[0],16), int(fields[1],16), fields[3]))
    table.sort()
    return table


def cycle_read_pcs(elf):
    text = subprocess.check_output([str(OBJDUMP), "-d", "--disassemble=main", str(elf)], text=True)
    pcs = re.findall(r"^\s*([0-9a-f]+):\s+c0002[0-9a-f]{3}\s+rdcycle\s", text, re.M)
    if len(pcs) != 2:
        raise ValueError("Expected exactly two rdcycle PCs in ABBA main")
    return tuple(int(pc,16) for pc in pcs)


def retirement_trials(path, table, pcs, measured):
    starts = [row[0] for row in table]
    trials, active, previous, begin = [], None, None, None
    def owner(pc):
        i = bisect_right(starts, pc)-1
        if i < 0 or pc >= table[i][0]+table[i][1]:
            return "unmapped"
        return table[i][2].removesuffix("_candidate")
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["event"] != "retire":
                continue
            pc, cycle = int(row["pc"],16), int(row["cycle"])
            if pc == pcs[0]:
                if active is not None or len(trials) >= 4:
                    raise ValueError("Nested/extra timed interval")
                active = defaultdict(lambda:dict(instructions=0,retire_gap_cycles=0))
                begin = dict(cycle=cycle, csr_cycle=int(row["rd_wdata"],16))
                previous = cycle
                continue
            if active is None:
                continue
            if cycle < previous or row["trap"] != "0":
                raise ValueError("Nonmonotonic/trapping timed retirement")
            entry = active[owner(pc)]
            entry["instructions"] += 1
            entry["retire_gap_cycles"] += cycle-previous
            previous = cycle
            if pc == pcs[1]:
                csr_cycles = int(row["rd_wdata"],16)-begin["csr_cycle"]
                if csr_cycles != measured[len(trials)]["cycles"]:
                    raise ValueError("Retirement CSR values disagree with measured cycles")
                if sum(x["retire_gap_cycles"] for x in active.values()) != cycle-begin["cycle"]:
                    raise ValueError("Retirement gap partition incomplete")
                trials.append(dict(trial=len(trials), overlap=int(len(trials) in (1,2)),
                    begin=begin, end=dict(cycle=cycle,csr_cycle=int(row["rd_wdata"],16)),
                    csr_cycles=csr_cycles,instructions=sum(x["instructions"] for x in active.values()),
                    functions=dict(sorted(active.items()))))
                active = None
    if len(trials) != 4 or active is not None:
        raise ValueError("Incomplete four-trial retirement trace")
    return trials


def refill_windows(log, trace, trials):
    groups = defaultdict(dict)
    for event,cycle,ordinal,arch,vid in re.findall(
        r"^\[AKV_REFILL_ORDER\] event=(start|first_ar|terminal) cycle=(\d+) ordinal=(\d+) arch=(\d+) vid=(\d+)$",
        log, re.M):
        group = groups[int(ordinal)]
        if event in group:
            raise ValueError("Duplicate refill event")
        group[event] = int(cycle)
        group.setdefault("arch",int(arch)); group.setdefault("vid",int(vid))
        if group["arch"] != int(arch) or group["vid"] != int(vid):
            raise ValueError("Refill identity drift")
    if set(groups) != set(range(1,9)):
        raise ValueError("Expected eight real refill windows")
    fma_alloc, last_write = {}, {}
    with trace.open(newline="") as stream:
        for row in csv.DictReader(stream):
            arch, cycle = int(row["arch_seq"]), int(row["cycle"])
            insn = int(row["insn"],16)
            if row["event"] == "alloc" and insn & 127 == 0x57 and insn >> 26 == 44:
                fma_alloc[arch] = cycle
            elif row["event"] == "write" and arch in fma_alloc:
                last_write[arch] = max(last_write.get(arch,0),cycle)
    keys = sorted(fma_alloc)
    windows = []
    for ordinal in sorted(groups):
        g = groups[ordinal]
        if not all(e in g for e in ("start","first_ar","terminal")) or not g["start"] <= g["first_ar"] <= g["terminal"]:
            raise ValueError("Incomplete/refill timing")
        trial = next((t for t in trials if t["begin"]["cycle"] <= g["start"] < t["end"]["cycle"]),None)
        at = bisect_right(keys,g["arch"]-1)
        older = keys[max(0,at-6):at]
        if trial is None or len(older) != 6 or any(s not in last_write for s in older):
            raise ValueError("Missing older-FMA completion evidence")
        final = max(last_write[s] for s in older)
        windows.append(dict(ordinal=ordinal,trial=trial["trial"],overlap=trial["overlap"],**g,
            older_fma_arch=older,older_last_write=final,
            older_write_overlap_cycles=max(0,final-g["first_ar"]),
            gap_after_older_write=g["first_ar"]-final))
    return windows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--build",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    run,build = args.run.resolve(strict=True), args.build.resolve(strict=True)
    target = args.output.resolve()
    if target.exists(): raise FileExistsError(target)
    status=json.loads((run/"status.json").read_text())
    result=json.loads((run/"result.json").read_text())
    pins=json.loads((run/"manifest.json").read_text())
    if status["state"] != "PASS" or hashes(map(Path,pins)) != pins:
        raise ValueError("Not a sealed passing run or source drift")
    work=run/"work"; log=(work/"run.vcs.log").read_text()
    checked=check_log(log)
    if any(checked[k] != result[k] for k in checked): raise ValueError("ABBA result drift")
    if hashes(map(Path,result["evidence_sha256"])) != result["evidence_sha256"]:
        raise ValueError("Raw trace identity drift")
    report=json.loads((build/"build.json").read_text()); elf=Path(report["elf"])
    if digest(elf) != report["elf_sha256"]: raise ValueError("ELF drift")
    trials=retirement_trials(work/"commit_trace.csv",symbol_table(elf),cycle_read_pcs(elf),result["trials"])
    windows=refill_windows(log,work/"vector_trace.csv",trials)
    modes={}
    for mode in (0,1):
        aggregate=defaultdict(lambda:dict(instructions=0,retire_gap_cycles=0))
        for t in trials:
            if t["overlap"] != mode: continue
            for name,values in t["functions"].items():
                for k,value in values.items(): aggregate[name][k]+=value
        modes[str(mode)]=dict(aggregate)
    delta={}
    for name in sorted(set(modes["0"])|set(modes["1"])):
        values={k:modes["1"].get(name,{}).get(k,0)-modes["0"].get(name,{}).get(k,0)
                for k in ("instructions","retire_gap_cycles")}
        if any(values.values()): delta[name]=values
    answer=dict(state="PASS",scope="Measured retirement attribution and older-FMA write timing, not exclusive stall causes",
        performance_accepted=False,attention_speedup=result["attention_speedup"],
        trials=trials,refills=windows,mode_totals=modes,mode1_minus_mode0=delta,
        evidence_sha256=hashes([run/"result.json",run/"manifest.json",work/"run.vcs.log",
            work/"commit_trace.csv",work/"vector_trace.csv",elf,Path(__file__)]))
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("x") as stream: json.dump(answer,stream,indent=2,sort_keys=True); stream.write("\n")
    print(json.dumps(dict(state="PASS",cycles=result["sums"],instructions=[t["instructions"] for t in trials],
        refill_overlap=[w["older_write_overlap_cycles"] for w in windows],
        largest_gaps=sorted(delta.items(),key=lambda x:abs(x[1]["retire_gap_cycles"]),reverse=True)[:8]),indent=2))


if __name__=="__main__": main()
