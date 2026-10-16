#!/usr/bin/env python3
"""Bounded full RTL adapter test using a frozen package, without synthesis."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def extract(source, name):
    match = re.search(r"(?:localparam|parameter) type\s+" + name + r"\s*=\s*struct packed\s*\{", source)
    if not match:
        raise ValueError("Missing type " + name)
    start = source.index("struct packed", match.start())
    end = source.index("{", start)
    depth = 1
    while depth:
        end += 1
        depth += (source[end] == "{") - (source[end] == "}")
    return "typedef " + source[start:end+1] + " " + name + ";\n"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--candidate", action="store_true", help="Patch only an isolated adapter copy")
    p.add_argument("--extended", action="store_true", help="I-cache, LR and sustained invalidation regressions")
    p.add_argument("--pmd-replay", action="store_true", help="Controlled stale-leaf-to-PMD replay, not historical timing")
    p.add_argument("--pli", type=Path, help="Verdi PLI directory for bounded focused PMD FSDB")
    p.add_argument("--filter", type=int, choices=(0,1,2), default=0,
                   help="0: direct invalidation; 1: real AW filter; 2: disabled AW filter")
    a = p.parse_args()
    if a.pmd_replay and (a.extended or a.filter):
        p.error('PMD replay uses only the bounded two-read direct-invalidation test')
    if a.pli and not a.pmd_replay:
        p.error('--pli currently records only the focused PMD replay')
    root=a.package.resolve(); out=a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    core=root/"rtl/cva6/core"; common=root/"rtl/common_cells"; axi=root/"rtl/axi"
    top=(core/"cva6.sv").read_text(); cache=(core/"cache_subsystem/wt_cache_subsystem.sv").read_text()
    types="// Extracted from frozen RTL; Solderpad Hardware License 0.51.\n"
    for name in ("icache_req_t", "icache_rtrn_t"):
        types += extract(top,name)
    for name in ("dcache_inval_t", "dcache_req_t", "dcache_rtrn_t"):
        types += extract(cache,name)
    (out/"collision_types.svh").write_text(types)
    adapter=core/"cache_subsystem/wt_axi_adapter.sv"
    if a.candidate:
        source=adapter.read_text()
        old="axi_rd_rdy        = ~invalidate;"
        if source.count(old)!=1: raise ValueError("Candidate anchor mismatch")
        adapter=out/"wt_axi_adapter_candidate.sv"
        adapter.write_text(source.replace(old,"axi_rd_rdy        = ~invalidate & ~inval_valid_i;"))
    files=[common/"src/cf_math_pkg.sv",axi/"src/axi_pkg.sv"]
    files += [core/"include"/n for n in ("config_pkg.sv","cv64a6_imafdcv_sv39_config_pkg.sv","riscv_pkg.sv","ariane_pkg.sv","build_config_pkg.sv","wt_cache_pkg.sv")]
    files += [common/"src/lzc.sv",common/"src/rr_arb_tree.sv",common/"src/fifo_v3.sv",
              root/"rtl/ara/hardware/src/axi_inval_filter.sv",core/"cva6_fifo_v3.sv",core/"axi_shim.sv",adapter,Path(__file__).with_name("pmd_read_replay_tb.sv" if a.pmd_replay else "inval_read_collision_tb.sv").resolve()]
    manifest={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    (out/"sources.json").write_text(json.dumps(manifest,indent=2))
    cmd=["vcs","-full64","-sverilog","-timescale=1ns/1ps","-top","inval_read_collision_tb",
         "+incdir+"+str(common/"include"),"+incdir+"+str(axi/"include"),"+incdir+"+str(core/"include"),"+incdir+"+str(out)]
    if a.pli:
        cmd += ['-debug_access+all', '-P', str(a.pli/'novas.tab'),
                str(a.pli/'pli.a'), '+define+PMD_FSDB']
    with (out/"compile.log").open("w") as log:
        subprocess.run(cmd+list(map(str,files))+["-o","simv","-Mdir=csrc"],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
    results=[]
    cases=[(beat,0,1) for beat in (-1,0,1,2,3)]
    if a.pmd_replay:
        cases=[(beat,0,1) for beat in (-1,0)]
    if a.extended:
        if a.filter!=0: raise ValueError('Extended cases use direct invalidation')
        cases += [(3,0,4),(-1,1,1),(0,1,4),(1,1,1),(-1,2,1),(0,2,4)]
    for beat,mode,hold in cases:
        path=out/f"run_{beat}_{mode}_{hold}.log"
        with path.open("w") as log:
            run=subprocess.run([str(out/"simv"),"-no_save",f"+collide={beat}",f"+filter={a.filter}",
                f"+mode={mode}",f"+hold={hold}",f"+wave={out / ('pmd_'+str(beat)+'.fsdb')}"],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=30)
        text=path.read_text()
        passed=run.returncode==0 and f"INVAL_READ_PASS collide={beat}" in text and "Fatal:" not in text
        results.append({"beat":beat,"filter":a.filter,"mode":mode,"hold":hold,"passed":passed,
                        "pmd_mechanism_replay_not_historical_timing":a.pmd_replay})
        print(json.dumps(results[-1]),flush=True)
    (out/"results.json").write_text(json.dumps(results,indent=2))
    return 0 if all(r["passed"] for r in results) else 1


if __name__=="__main__":
    raise SystemExit(main())
