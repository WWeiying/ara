#!/usr/bin/env python3
"""GNU bare-metal equal-work Q6_K panel benchmark, matrix phase only."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from run_half_scale_soc import ROOT, atomic_json, digest, hashes

HELPER=ROOT/"verification/akv/refill_overlap_probe/build.py"
sys.path.insert(0,str(HELPER.parent))
from build import alloc_sections, check_libc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--panel-build",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();data=args.data.resolve(strict=True)
    manifest_path=data/"manifest.json";manifest=json.loads(manifest_path.read_text())
    status=json.loads((data/"status.json").read_text())
    if (manifest["state"]!="PASS" or status["state"]!="PASS" or
        status["manifest_sha256"]!=digest(manifest_path) or
        manifest["shape"]!=dict(m=4,n=64,k=8960,k_blocks=35) or
        manifest["numerical_comparison"]["llama_mismatches"]!=0):
        raise ValueError("Real data generation/geometry not accepted")
    if hashes(map(Path,manifest["inputs"]))!=manifest["inputs"]:
        raise ValueError("Data source provenance drift")
    for name,info in manifest["artifacts"].items():
        if digest(data/name)!=info["sha256"] or (data/name).stat().st_size!=info["bytes"]:
            raise ValueError("Generated data/artifact drift: "+name)
    panel=args.panel_build.resolve(strict=True);panel_result=json.loads((panel/"result.json").read_text())
    if panel_result["status"]!="PASS":raise ValueError("Experimental driver object gate missing")
    for group in ("sources","artifacts","tools"):
        if hashes(map(Path,panel_result[group]))!=panel_result[group]:
            raise ValueError("Panel driver "+group+" drift")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    gcc=Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc").resolve(strict=True)
    objdump=gcc.with_name(gcc.name.removesuffix("gcc")+"objdump").resolve(strict=True)
    common=ROOT/"apps/common"
    sources=[ROOT/"verification/qbs/vrf_panel_bench/main.c",data/"panel_data.S",
             *(common/n for n in ("crt0.S","printf.c","string.c","serial.c","util.c","print_trap_cause.c"))]
    flags=["-march=rv64gcv","-mabi=lp64d","-mcmodel=medany","-mno-relax","-O2","-std=gnu11",
           "-fno-tree-vectorize","-ffreestanding","-fno-builtin","-fno-tree-loop-distribute-patterns",
           "-fno-fast-math","-ffp-contract=off","-fno-common","-ffunction-sections","-fdata-sections",
           "-DNR_LANES=4","-DVLEN=1024","-I"+str(common),"-I"+str(ROOT/"apps/include"),
           "-I"+str(ROOT/"software/qbs/include"),"-I"+str(ROOT/"software/qbs/experimental/vrf_panel"),
           "-I"+str(data)]
    commands=[]
    def run(command,name):
        command=list(map(str,command));commands.append(command);atomic_json(out/"commands.json",commands)
        with (out/(name+".log")).open("x") as log:
            subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        return (out/(name+".log")).read_text()
    inputs={*map(Path,manifest["inputs"]),*map(Path,panel_result["sources"]),
        *map(Path,panel_result["artifacts"]),*map(Path,panel_result["tools"]),
        *(data/name for name in manifest["artifacts"]),manifest_path,data/"status.json",panel/"result.json",
        Path(__file__).resolve(),ROOT/"verification/qbs/run_half_scale_soc.py",HELPER,
        common/"arch.link.ld",gcc,objdump}
    for i,source in enumerate(sources):
        dep=out/f"{i}.d";run([gcc,*flags,"-M","-MF",dep,"-MT","bench",source],f"deps-{i}")
        inputs.update(Path(p).resolve(strict=True) for p in shlex.split(
            dep.read_text().replace("\\\n"," ").split(":",1)[1]))
    pins=hashes(inputs);atomic_json(out/"manifest.json",pins)
    script=out/"link.ld";template=(common/"arch.link.ld").read_text()
    if template.count("LENGTH = 0x00100000")!=1:raise ValueError("Linker template changed")
    script.write_text(template.replace("ALIGNMENT","16").replace("LENGTH = 0x00100000","LENGTH = 0x01000000"))
    objects=[]
    for i,source in enumerate(sources):
        obj=out/f"{i}.o";extra=["-Wall","-Wextra","-Werror"] if i==0 else []
        run([gcc,*flags,*extra,"-c",source,"-o",obj],f"compile-{i}")
        if source.name=="string.c":check_libc(run([objdump,"-dr",obj],"libc-disassembly"))
        objects.append(obj)
    elf=out/"qbs_vrf_panel_bench.elf"
    run([gcc,*flags,"-static","-nostartfiles","-nostdlib",*objects,panel/"vrf_panel.o",
         "-Wl,--gc-sections","-Wl,-Map="+str(out/"link.map"),"-T",script,"-lm","-lgcc","-o",elf],"link")
    disasm=run([objdump,"-d",elf],"disassembly")
    expected={0x06b5045b,0x06b5085b,0x16b5045b,0x16b5085b,0x0005155b}
    custom=[]
    for line in disasm.splitlines():
        match=re.match(r"\s*[0-9a-f]+:\s+([0-9a-f]{8})\s+",line)
        if match and int(match[1],16)&0x7f==0x5b:custom.append(int(match[1],16))
    if len(custom)!=5 or set(custom)!=expected:raise ValueError("Linked QBEXEC/QBACC encoding drift")
    sections=alloc_sections(elf);high=max(s["address"]+s["bytes"] for s in sections)
    if min(s["address"] for s in sections)<0x80000000 or high>0x81000000-65536:
        raise ValueError("ELF violates simulation L2/stack bound")
    if hashes(inputs)!=pins:raise ValueError("Benchmark input drift")
    atomic_json(out/"build.json",dict(state="BUILT_NOT_EXECUTED",elf=str(elf),elf_sha256=digest(elf),
        manifest_sha256=digest(out/"manifest.json"),data_manifest_sha256=digest(manifest_path),
        panel_result_sha256=digest(panel/"result.json"),simulation_l2_mb=16,
        shape=manifest["shape"],expected_fflags=manifest["numerical_comparison"]["fflags"],
        expected_calls=4,expected_commands=40,allocated_bytes=sum(s["bytes"] for s in sections),
        scope="Real Q6_K M4/N64/K8960 matrix-only ABBA; descriptor/capability/dispatch/seed/commit/store included, activation and offline weight preparation excluded"))
    print(json.dumps(dict(state="BUILT_NOT_EXECUTED",elf=str(elf),elf_sha256=digest(elf))))


if __name__=="__main__":main()
