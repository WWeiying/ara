#!/usr/bin/env python3
"""Short real-sequencer VCS test with independently driven PE completion."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from sys import path as python_path

ROOT=Path(__file__).resolve().parents[2]
python_path.insert(0,str(ROOT/"verification/qbs"))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    packages=["hardware/deps/common_cells/src/cf_math_pkg.sv","hardware/deps/axi/src/axi_pkg.sv",
        "hardware/deps/fpnew/src/fpnew_pkg.sv","hardware/deps/cva6/core/include/config_pkg.sv",
        "hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv","hardware/deps/cva6/core/include/riscv_pkg.sv",
        "hardware/deps/cva6/core/include/build_config_pkg.sv","hardware/include/rvv_pkg.sv","hardware/include/ara_pkg.sv",
        "hardware/include/qbs_pkg.sv","hardware/include/akv_pkg.sv"]
    sources=[ROOT/s for s in packages]+[ROOT/f"hardware/deps/common_cells/src/{s}.sv" for s in ("lzc","delta_counter","counter")]+[
        ROOT/"hardware/src/vlsu/akv/akv_refill_order_guard.sv",ROOT/"hardware/src/ara_sequencer.sv",
        ROOT/"verification/akv/refill_sequencer_tb.sv"]
    ara=ROOT/"hardware/src/ara.sv";text=ara.read_text()
    start=text.index("  // Interfaces between Ara's dispatcher and Ara's backend\n")
    end=text.index("  } ara_resp_t;",start)+len("  } ara_resp_t;")
    package=out/"types.sv"
    package.write_text('''package dispatcher_check_pkg;
  import ara_pkg::*; import rvv_pkg::*;
  localparam config_pkg::cva6_cfg_t CVA6Cfg=build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  localparam int VLEN=1024,NrLanes=4;
  typedef logic[$clog2(VLEN+1)-1:0] vlen_t;
  `include "ara/intf_typedef.svh"
  `CVA6_TYPEDEF_EXCEPTION(exception_t, CVA6Cfg)
'''+text[start:end]+'\n`include "ara/ara_typedef.svh"\nendpackage\n')
    pins=hashes([*sources,ara,Path(__file__),*ROOT.glob("hardware/include/ara/*.svh"),
        *ROOT.glob("hardware/deps/common_cells/include/common_cells/*.svh"),package])
    atomic_json(out/"manifest.json",pins)
    command=["vcs","-full64","-sverilog","-assert","svaext","-timescale=1ns/1ps","-top","refill_sequencer_tb",
        "+incdir+"+str(ROOT/"hardware/include"),"+incdir+"+str(ROOT/"hardware/deps/common_cells/include"),
        *map(str,sources[:len(packages)]),str(package),*map(str,sources[len(packages):]),"-o",str(out/"simv")]
    atomic_json(out/"commands.json",[command,[str(out/"simv")]])
    state=dict(state="BUILDING",scope="Actual sequencer with PE/AddrGen fixtures; not numerical execution or performance")
    try:
        for label,cmd in (("compile",command),("run",[str(out/"simv")])):
            state["state"]="BUILDING" if label=="compile" else "RUNNING";atomic_json(out/"status.json",state)
            with (out/(label+".log")).open("x") as f:subprocess.run(cmd,cwd=out,env=os.environ.copy(),stdout=f,stderr=subprocess.STDOUT,check=True,timeout=240)
        text=(out/"run.log").read_text()
        if not re.search(r"^AKV_REFILL_SEQ_PASS checks=\d+ scenarios=6$",text,re.M):raise ValueError("Missing test completion")
        scenarios=re.findall(r"^REFILL_SEQ_SCENARIO order=(-?\d) fault=([01]) PASS$",text,re.M)
        if scenarios!=[(str(o),str(f)) for o in (-1,0,1) for f in (0,1)]:raise ValueError("Missing/order scenario checks")
        if hashes(map(Path,pins))!=pins:raise ValueError("Source drift")
        state.update(state="PASS",scenarios=6,log_sha256=digest(out/"run.log"),manifest_sha256=digest(out/"manifest.json"))
    except BaseException as exc:state.update(state="FAIL",error=repr(exc));raise
    finally:atomic_json(out/"status.json",state)


if __name__=="__main__":main()
