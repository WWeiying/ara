#!/usr/bin/env python3
"""Build a successor against the unchanged full Q8_K acceptance harness."""
import argparse
import json
from pathlib import Path
import subprocess

from run_half_scale_soc import ROOT,atomic_json,digest,hashes


def check_core(old,new):
    start="template <size_t MaxAVL = 16>"
    def core(text):
        if text.count(start)!=1 or text.count("} // namespace ")!=1:raise ValueError("Candidate boundaries changed")
        return text[text.index(start):text.index("} // namespace ")]
    if core(old)!=core(new):raise ValueError("Quantizer drift beyond preflight")


def adapt_harness(text,header):
    include='#include "../ggml_q8k_m4_prepare_candidate.h"'
    namespace="qbs_q8k_m4_prepare_candidate::"
    if text.count(include)!=1 or text.count(namespace)!=3:raise ValueError("Harness call contract changed")
    return text.replace(include,f'#include "{header}"').replace(namespace,"qbs_q8k_m4_prepare_vla_candidate::")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("native-build","native-run","production-build","output"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();previous=a.native_build.resolve(strict=True);run=a.native_run.resolve(strict=True)
    prod=a.production_build.resolve(strict=True)
    status=json.loads((run/"status.json").read_text());pins=json.loads((run/"manifest.json").read_text())
    if (status["state"]!="PASS" or status["checks"]!=12000 or digest(run/"manifest.json")!=status["manifest_sha256"]
        or hashes(map(Path,pins))!=pins or str(previous/"manifest.json") not in pins or str(prod/"manifest.json") not in pins):
        raise ValueError("Require unchanged original native numerical gate")
    source=ROOT/"verification/qbs";suite=source/"ggml_q8k_m4_prepare_native"
    header=source/"ggml_q8k_m4_prepare_vla_candidate.h"
    check_core((source/"ggml_q8k_m4_prepare_candidate.h").read_text(),header.read_text())
    platform=Path("/home/wangwy/llama/platforms/cva6-qemu");tools=platform/"tools/bin"
    cxx,cc,objdump=[tools/("riscv64-linux-"+n) for n in ("g++","gcc","objdump")]
    cpio=platform/"sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    ggml=Path("/home/wangwy/llama/llama.cpp/ggml")
    libdir=prod/"build/tile-support/ggml/src"
    libs=[libdir/("lib"+n+".a") for n in ("ggml","ggml-cpu","ggml-base")]
    if any(str(lib) not in pins for lib in libs):raise ValueError("Unsealed production archives")
    pins.update(hashes([Path(__file__),header,source/"q8k_m4_domain_vla.h",suite/"native.cpp",suite/"init.c",
        suite/"check.py",run/"manifest.json",run/"status.json",cxx.resolve(),cc.resolve(),objdump.resolve(),cpio]))
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    native=out/"native.cpp";native.write_text(adapt_harness((suite/"native.cpp").read_text(),header))
    for name in ("captures.txt","captures.json",*(n+".bin" for n in
        ("real_attn_first","real_attn_last","real_gate_first","real_gate_last","real_down_first","real_down_last"))):
        if str(previous/name) not in pins:raise ValueError("Unpinned capture")
        (out/name).write_bytes((previous/name).read_bytes())
    atomic_json(out/"sources-before.json",pins)
    commands=[]
    def invoke(command,label):
        command=list(map(str,command));commands.append(command);atomic_json(out/"commands.json",commands)
        with (out/(label+".log")).open("x") as stream:
            subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=120)
    includes=[s for d in (ggml/"include",ggml/"src",ggml/"src/ggml-cpu") for s in ("-isystem",str(d))]
    invoke([cxx,"-std=c++17","-march=rv64gcv","-mabi=lp64d","-O3","-UNDEBUG","-fno-fast-math",
        "-ffp-contract=off","-fno-tree-vectorize","-Wall","-Wextra","-Werror",*includes,"-c",native,"-o",out/"native.o"],"compile")
    invoke([cxx,"-march=rv64gcv","-mabi=lp64d","-static",out/"native.o",*libs,"-lm","-ldl","-o",out/"native"],"link")
    invoke([cc,"-march=rv64gcv","-mabi=lp64d","-O2","-static",suite/"init.c","-o",out/"init"],"init")
    disasm=subprocess.check_output([objdump,"-d","--disassemble=ggml_quantize_mat_q8_K_4x1_ara_generic",out/"native"],text=True)
    (out/"oracle.disasm").write_text(disasm)
    if "fmadd.s" not in disasm:raise ValueError("Production contraction changed")
    listing=["dir /dev 755 0 0","nod /dev/console 600 0 0 c 5 1",
        f"file /init {out/'init'} 755 0 0",f"file /native {out/'native'} 755 0 0",f"file /captures.txt {out/'captures.txt'} 444 0 0"]
    listing += [f"file /{p.name} {p} 444 0 0" for p in sorted(out.glob("real_*.bin"))]
    (out/"initramfs.list").write_text("\n".join(listing)+"\n")
    with (out/"initramfs.cpio").open("xb") as f:subprocess.run([cpio,out/"initramfs.list"],stdout=f,check=True,timeout=60)
    if hashes(map(Path,pins))!=pins:raise ValueError("Source drift")
    pins.update(hashes(p for p in out.iterdir() if p.is_file()))
    atomic_json(out/"manifest.json",pins)
    atomic_json(out/"build.json",dict(state="READY",execution="NOT_RUN",binary_sha256=digest(out/"native"),
        manifest_sha256=digest(out/"manifest.json"),scope="Full original 50-case Q8_K harness; only preflight changes"))


if __name__=="__main__":main()
