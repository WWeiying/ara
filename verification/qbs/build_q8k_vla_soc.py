#!/usr/bin/env python3
"""Derive a VLA-preflight ELF from a freshly rebuilt, unchanged ABBA harness."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from build_q8k_vla_native import check_core
from run_half_scale_soc import ROOT,atomic_json,digest,hashes


def replace_one(args,old,new):
    if args.count(str(old))!=1:raise ValueError("Ambiguous/missing build argument")
    return [str(new) if s==str(old) else s for s in args]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=("prepare","projection"),required=True)
    for name in ("native-run","golden-run","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--data",type=Path)
    a=p.parse_args()
    if a.mode=="projection" and not a.data:p.error("projection requires --data")
    native=a.native_run.resolve(strict=True);status=json.loads((native/"status.json").read_text())
    pins=json.loads((native/"manifest.json").read_text());source=ROOT/"verification/qbs"
    header=source/"ggml_q8k_m4_prepare_vla_candidate.h"
    if (status["state"]!="PASS" or status["checks"]!=12000 or
        digest(native/"manifest.json")!=status["manifest_sha256"] or hashes(map(Path,pins))!=pins or
        pins.get(str(header))!=digest(header)):
        raise ValueError("Require accepted unchanged full-quantizer numerical gate")
    check_core((source/"ggml_q8k_m4_prepare_candidate.h").read_text(),header.read_text())
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);base=out/"baseline"
    builder=source/f"build_q8k_{a.mode}_soc.py"
    command=[sys.executable,str(builder),"--golden-run",str(a.golden_run.resolve(strict=True)),"--output",str(base)]
    if a.mode=="projection":command += ["--data",str(a.data.resolve(strict=True))]
    atomic_json(out/"baseline-command.json",command)
    with (out/"baseline-build.log").open("x") as f:
        subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=600)
    base_report=json.loads((base/"build.json").read_text());base_pins=json.loads((base/"manifest.json").read_text())
    if base_report["state"]!="BUILT_NOT_EXECUTED" or hashes(map(Path,base_pins))!=base_pins:
        raise ValueError("Fresh baseline build drift")
    commands=json.loads((base/"commands.json").read_text())
    original=source/f"q8k_{a.mode}_soc.cpp"
    text=original.read_text();include='#include "ggml_q8k_m4_prepare_candidate.h"';namespace="qbs_q8k_m4_prepare_candidate::"
    if text.count(include)!=1 or text.count(namespace)!=1:raise ValueError("ABBA harness changed")
    variant=out/"candidate.cpp"
    variant.write_text(text.replace(include,f'#include "{header}"').replace(namespace,"qbs_q8k_m4_prepare_vla_candidate::"))
    compile_command=replace_one(commands[0],original,variant)
    compile_command=replace_one(compile_command,base/"0.o",out/"candidate.o")
    elf=out/f"qbs_q8k_{a.mode}_soc"
    link_command=replace_one(commands[-1],base/"0.o",out/"candidate.o")
    link_command=replace_one(link_command,base/elf.name,elf)
    link_command=replace_one(link_command,"-Wl,-Map="+str(base/"link.map"),"-Wl,-Map="+str(out/"link.map"))
    atomic_json(out/"variant-commands.json",[compile_command,link_command])
    for label,cmd in (("compile",compile_command),("link",link_command)):
        with (out/(label+".log")).open("x") as f:
            subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    helper=ROOT/"apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py"
    spec=importlib.util.spec_from_file_location("pair",helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sections=module.allocated_sections(elf)
    if min(s["address"] for s in sections)<0x80000000 or max(s["address"]+s["bytes"] for s in sections)>0x81000000-65536:
        raise ValueError("ELF address range")
    if hashes(map(Path,pins))!=pins or hashes(map(Path,base_pins))!=base_pins:raise ValueError("Source drift")
    pins.update(base_pins)
    pins.update(hashes([Path(__file__),source/"build_q8k_vla_native.py",header,source/"q8k_m4_domain_vla.h",
        native/"status.json",native/"manifest.json",builder,helper,
        *[path for path in base.rglob("*") if path.is_file()],
        *[path for path in out.iterdir() if path.is_file()]]))
    atomic_json(out/"manifest.json",pins)
    atomic_json(out/"build.json",dict(state="BUILT_NOT_EXECUTED",elf_sha256=digest(elf),sections=sections,
        manifest_sha256=digest(out/"manifest.json"),baseline_elf_sha256=base_report["elf_sha256"],
        scope=f"Original {a.mode} ABBA harness; only candidate preflight differs"))


if __name__=="__main__":main()
