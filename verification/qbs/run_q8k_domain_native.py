#!/usr/bin/env python3
"""Bounded VLEN/CSR equivalence gate for the successor integer preflight."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from run_half_scale_soc import ROOT,atomic_json,digest,hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build


def check_output(text,vlen):
    if re.search(r"Kernel panic|Illegal instruction|Segmentation fault|qemu: fatal",text,re.I):raise ValueError("Guest failure")
    lines=[s.strip() for s in text.splitlines() if "Q8K_DOMAIN_" in s]
    if len(lines)!=3 or lines[0]!=f"Q8K_DOMAIN_BEGIN vlen={vlen}" or lines[-1]!="Q8K_DOMAIN_EXIT=0":
        raise ValueError("Missing/extra or failed protocol")
    result=re.fullmatch(r"Q8K_DOMAIN_PASS datasets=134 checks=12060 digest=([0-9a-f]{16}) csr=unchanged input=unchanged",lines[1])
    if not result:raise ValueError("Incomplete numerical/CSR coverage")
    return dict(state="PASS",datasets=134,checks=12060,digest=result[1],vlen=vlen)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("configuration","capture-build","output"):p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();config=json.loads(a.configuration.read_text())
    platform,qemu=Path(config["platform"]),Path(config["qemu"])
    previous=a.capture_build.resolve(strict=True);prior=json.loads((previous/"build.json").read_text())
    inherited=json.loads((previous/"manifest.json").read_text())
    if prior["state"]!="READY" or digest(previous/"manifest.json")!=prior["manifest_sha256"] or hashes(map(Path,inherited))!=inherited:
        raise ValueError("Capture source build drift")
    captures=[previous/(n+".bin") for n in ("real_attn_first","real_attn_last","real_gate_first","real_gate_last","real_down_first","real_down_last")]
    if any(str(path) not in inherited for path in captures):raise ValueError("Unsealed capture")
    source=ROOT/"verification/qbs/q8k_domain_native.cpp"
    header=ROOT/"verification/qbs/q8k_m4_domain_vla.h"
    cxx=platform/"tools/bin/riscv64-linux-g++"
    cpio=platform/"sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    pins=hashes([Path(__file__),source,header,*captures,previous/"manifest.json",a.configuration.resolve(),
        cxx.resolve(),Path(str(cxx)+".br_real").resolve(),cpio,qemu,platform/"images/Image",platform/"images/fw_dynamic.bin",
        *map(Path,verify_native_build(qemu)),ROOT/"verification/qbs/run_half_scale_soc.py",
        ROOT/"verification/qbs/run_tile_context_engine.py",ROOT/"verification/qbs/run_ggml_segmented.py"])
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    atomic_json(out/"manifest.json",pins)
    state=dict(state="BUILDING",pid=os.getpid(),child_pid=None,cases=[])
    def save():atomic_json(out/"status.json",state)
    def started(pid):state.update(child_pid=pid);save()
    save()
    try:
        command=list(map(str,[cxx,"-std=c++17","-march=rv64gcv","-mabi=lp64d","-O3","-static",
            "-fno-fast-math","-fno-tree-vectorize","-Wall","-Wextra","-Werror",source,"-o",out/"init"]))
        atomic_json(out/"compile-command.json",command)
        if run_command(command,out/"build.log",120,os.environ.copy(),started):raise RuntimeError("Native build failed")
        listing=out/"init.list"
        listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"+f"file /init {out/'init'} 755 0 0\n"+
            ''.join(f"file /{c.name} {c} 444 0 0\n" for c in captures))
        with (out/"init.cpio").open("xb") as f:subprocess.run([cpio,listing],stdout=f,check=True,timeout=60)
        artifacts=hashes([out/"init",out/"init.cpio",listing,out/"compile-command.json"])
        atomic_json(out/"artifacts-before.json",artifacts)
        for vlen in (128,1024):
            if hashes(map(Path,pins))!=pins:raise ValueError("Source drift before execution")
            command=list(map(str,[qemu,"-M","virt","-cpu",f"rv64,v=true,vlen={vlen},elen=64,xaraqbs=true",
                "-smp","1","-m","512M","-display","none","-monitor","none","-serial","stdio",
                "-bios",platform/"images/fw_dynamic.bin","-kernel",platform/"images/Image","-initrd",out/"init.cpio",
                "-append","console=ttyS0 rdinit=/init"]))
            state.update(state="RUNNING",vlen=vlen,command=command);save()
            log=out/f"qemu-{vlen}.log"
            if run_command(command,log,900,os.environ.copy(),started):raise RuntimeError("Guest failed/timed out")
            state["child_pid"]=None
            state["cases"].append(dict(report=check_output(log.read_text(),vlen),log_sha256=digest(log)))
            save()
        if state["cases"][0]["report"]["digest"]!=state["cases"][1]["report"]["digest"]:raise ValueError("VLEN-dependent classification")
        if hashes(map(Path,pins))!=pins or hashes(map(Path,artifacts))!=artifacts:raise ValueError("Source/artifact drift")
        state.update(state="PASS",checks=24120,manifest_unchanged=True)
    except BaseException as exc:state.update(state="FAIL",error=repr(exc));raise
    finally:state["child_pid"]=None;save()


if __name__ == "__main__":main()
