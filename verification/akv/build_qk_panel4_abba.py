#!/usr/bin/env python3
"""Fresh real captured Attention ABBA; rebuild shared runtime, never old objects."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"verification/qbs"))
from run_half_scale_soc import atomic_json,digest,hashes
from refill_overlap_probe.build import alloc_sections,check_libc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture",type=Path,required=True)
    p.add_argument("--object-gate",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();capture=args.capture.resolve(strict=True)
    gate=args.object_gate.resolve(strict=True);proof=json.loads((gate/"result.json").read_text())
    if proof["status"]!="PASS" or proof["selection_cases"]!=40 or proof["unchanged_symbols"]!=15:
        raise ValueError("PANEL4 object/selector gate not accepted")
    for group in ("sources","artifacts","tools"):
        if hashes(map(Path,proof[group]))!=proof[group]:raise ValueError("PANEL4 gate drift")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    generator=ROOT/"apps/llama_q4km_operator/script/gen_data.py"
    spec=importlib.util.spec_from_file_location("qk_panel4_data",generator)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.CAPTURE_ROOT=capture
    kind,feature,shape,_,blobs=module.make_spec("operator/decode/attention_core","akv_v2")
    if kind!="attention_core" or feature!=8 or shape[:5]!=[128,1,12,256,2]:
        raise ValueError("Wrong real captured attention shape")
    active=[i for i,(v,) in enumerate(struct.iter_unpack("<e",blobs["input_d"]["data"].read_bytes())) if v!=float("-inf")]
    if active!=list(range(128)):raise ValueError("Wrong live causal prefix")
    gcc=Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc").resolve(strict=True)
    objdump=gcc.with_name(gcc.name.removesuffix("gcc")+"objdump").resolve(strict=True)
    common=ROOT/"apps/common"
    sources=[ROOT/"verification/akv/qk_panel4_abba_soc.c",
        ROOT/"apps/llama_q4km_operator/akv_runtime.c",ROOT/"apps/llama_q4km_operator/akv_prefill_reference.c",
        ROOT/"apps/llama_q4km_operator/akv_attention.S",ROOT/"apps/llama_q4km_operator/akv_v2_attention.S",
        *(common/n for n in ("crt0.S","printf.c","string.c","serial.c","util.c","print_trap_cause.c"))]
    flags=["-march=rv64gcv_zfh_zvfh","-mabi=lp64d","-mcmodel=medany","-mno-relax","-O3",
        "-std=gnu11","-fno-fast-math","-ffp-contract=off","-fno-tree-vectorize","-fno-common",
        "-ffunction-sections","-fdata-sections","-ffreestanding","-fno-builtin",
        "-fno-tree-loop-distribute-patterns","-DNR_LANES=4","-DVLEN=1024","-DAKV_REFILL_OVERLAP=0",
        "-Wno-unknown-pragmas","-I"+str(common),"-I"+str(ROOT/"apps/include")]
    commands=[]
    def run(command,name,env=None):
        command=list(map(str,command));commands.append(command);atomic_json(out/"commands.json",commands)
        with (out/(name+".log")).open("x") as stream:
            subprocess.run(command,cwd=out,stdout=stream,stderr=subprocess.STDOUT,env=env,check=True,timeout=120)
        return (out/(name+".log")).read_text()
    inputs={Path(__file__).resolve(),generator,gate/"result.json",gcc,objdump,
        ROOT/"verification/qbs/run_half_scale_soc.py",ROOT/"verification/akv/refill_overlap_probe/build.py",
        common/"arch.link.ld",capture/"replay/manifest.json",
        capture/"replay/cases/operator/decode/attention_core/case.json"}
    for b in blobs.values():
        if b:inputs.update((b["meta"],b["data"]))
    for i,source in enumerate(sources):
        dep=out/f"{i}.d";run([gcc,*flags,"-M","-MF",dep,"-MT","bench",source],f"deps-{i}")
        inputs.update(Path(s).resolve(strict=True) for s in shlex.split(dep.read_text().replace("\\\n"," ").split(":",1)[1]))
    for name in ("libm.a","libgcc.a"):
        inputs.add(Path(subprocess.check_output([gcc,"-print-file-name="+name],text=True).strip()).resolve(strict=True))
    pins=hashes(inputs);atomic_json(out/"manifest.json",pins)
    env=dict(os.environ,Q4KM_CAPTURE_ROOT=str(capture))
    text=subprocess.check_output([sys.executable,generator,"operator/decode/attention_core","akv_v2"],cwd=out,env=env,text=True)
    start="llama_attention_output_start:\n";end="llama_attention_output_end:\n"
    if text.count(start)!=1 or text.count(end)!=1:raise ValueError("Output guard insertion boundary drift")
    text=text.replace(start,".global qk_panel4_guard_before\nqk_panel4_guard_before:\n.zero 64\n"+start)
    text=text.replace(end,end+".global qk_panel4_guard_after\nqk_panel4_guard_after:\n.zero 64\n")
    data=out/"data.S";data.write_text(text)
    script=out/"link.ld";template=(common/"arch.link.ld").read_text()
    if template.count("LENGTH = 0x00100000")!=1:raise ValueError("Linker template changed")
    script.write_text(template.replace("ALIGNMENT","16").replace("LENGTH = 0x00100000","LENGTH = 0x01000000"))
    objects=[]
    for i,source in enumerate([*sources,data]):
        obj=out/f"{i}.o";run([gcc,*flags,"-c",source,"-o",obj],f"compile-{i}")
        if source.name=="string.c":check_libc(run([objdump,"-dr",obj],"libc-disassembly"))
        objects.append(obj)
    elf=out/"akv_qk_panel4_abba.elf"
    run([gcc,*flags,"-static","-nostdlib","-nostartfiles",*objects,"-Wl,--gc-sections",
         "-Wl,-Map="+str(out/"link.map"),"-T",script,"-lm","-lgcc","-o",elf],"link")
    disasm=run([objdump,"-d",elf],"disassembly")
    for name in ("akv_v2_compute_scores_f16_d128_gqa6","akv_v2_compute_scores_f16_d128_gqa6_panel4","getenv"):
        if "<"+name+">:" not in disasm:raise ValueError("Missing actual runtime/helper/provider")
    sections=alloc_sections(elf)
    if min(s["address"] for s in sections)<0x80000000 or max(s["address"]+s["bytes"] for s in sections)>0x81000000-65536:
        raise ValueError("ELF exceeds simulation L2/stack reserve")
    if hashes(inputs)!=pins:raise ValueError("Build input drift")
    artifacts=hashes([elf,data,script,*objects,out/"disassembly.log",out/"commands.json"])
    atomic_json(out/"artifacts.json",artifacts)
    atomic_json(out/"build.json",dict(state="BUILT_NOT_EXECUTED",elf=str(elf),elf_sha256=digest(elf),
        manifest_sha256=digest(out/"manifest.json"),artifacts_sha256=digest(out/"artifacts.json"),
        effective_kv=128,outputs=1536,head_dim=128,q_heads=12,kv_heads=2,refill_overlap=False,
        scope="Actual shared native Decode Attention, one fixed-address ABBA ELF, QK singles versus PANEL4 only"))
    print(json.dumps(dict(state="BUILT_NOT_EXECUTED",elf=str(elf),elf_sha256=digest(elf))))


if __name__=="__main__":main()
