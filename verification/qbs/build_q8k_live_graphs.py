#!/usr/bin/env python3
"""Compile the live GGML TU with canonical Q8_K, reuse sealed graph stimuli."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from check_q8k_graphs import check_output
from run_half_scale_soc import ROOT, atomic_json, digest, hashes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("accepted-run","graph-build","production-build","output"):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args()
    previous=args.accepted_run.resolve(strict=True)
    graph=args.graph_build.resolve(strict=True)
    production=args.production_build.resolve(strict=True)
    old=json.loads((previous/"result.json").read_text())
    if json.loads((previous/"status.json").read_text())["state"]!="PASS":
        raise ValueError("Require accepted graph stimuli")
    checked=check_output((previous/"qemu.log").read_text())
    if any(old[k]!=v for k,v in checked.items()) or digest(previous/"qemu.log")!=old["log_sha256"]:
        raise ValueError("Graph oracle evidence drift")
    sealed=json.loads((graph/"manifest.json").read_text())
    record_path=production/"production-compile.json"
    record=json.loads(record_path.read_text())
    command=shlex.split(record["command"])
    repack=Path("/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp")
    canonical=ROOT/"software/qbs/ggml/q8_K-m4.h"
    installed=repack.parent/"arch/riscv/q8_K-m4.h"
    if canonical.read_bytes()!=installed.read_bytes(): raise ValueError("Canonical header not installed")
    if Path(record["file"]).resolve()!=repack or Path(command[command.index("-c")+1]).resolve()!=repack:
        raise ValueError("Production compile record source changed")
    if (not all(x in command for x in ("-O3","-DNDEBUG","-DGGML_USE_RISCV_QBS")) or
        any(x.startswith(("-flto","-ffast-math","-ffinite-math-only","-march=rv64gcv_z")) for x in command)):
        raise ValueError("Production ISA/FP optimization policy changed")
    compiler=Path(command[0]); gcc=compiler.with_name("riscv64-linux-gcc")
    libdir=production/"build/tile-support/ggml/src"
    libs=[libdir/("lib"+name+".a") for name in ("ggml","ggml-cpu","ggml-base")]
    consumed=[*libs,graph/"graph.o",graph/"init",record_path]
    # Old manifests also reference the intentionally changed live source. Only
    # immutable artifacts actually reused here are inherited; fresh source and
    # headers below are hashed independently rather than relabeling old runs.
    if any(sealed.get(str(path))!=digest(path) for path in consumed):
        raise ValueError("Reused stimulus/library identity drift")
    cpio=Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
    ggml=repack.parents[2]
    headers=[p for base in (ggml/"src",ggml/"include") for p in base.rglob("*")
             if p.is_file() and p.suffix in (".h",".hpp",".inl",".inc")]
    pins=hashes([*consumed,*headers,canonical,repack,compiler.resolve(),gcc.resolve(),cpio,Path(__file__),
        previous/"status.json",previous/"result.json",previous/"qemu.log",graph/"manifest.json",
        ROOT/"verification/qbs/check_q8k_graphs.py",ROOT/"verification/qbs/check_ggml_tile_context.py",
        ROOT/"verification/qbs/ggml_m4_prepare_production/check.py"])
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    commands=[]
    def invoke(argv,label,cwd=ROOT):
        commands.append(dict(argv=list(map(str,argv)),cwd=str(cwd)))
        atomic_json(out/"commands.json",commands)
        with (out/(label+".log")).open("x") as stream:
            subprocess.run(argv,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=300)
    command[command.index("-o")+1]=str(out/"production.o")
    # Compile the actual live source, not a privately rewritten selector.
    invoke(command,"production-compile",Path(record["directory"]))
    invoke([str(compiler),"-march=rv64gcv","-mabi=lp64d","-static",str(graph/"graph.o"),
        str(out/"production.o"),*map(str,libs),"-lm","-ldl","-pthread",
        "-Wl,-Map="+str(out/"graph.map"),"-o",str(out/"graph")],"link")
    listing=out/"initramfs.list"
    listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"+
        f"file /init {graph/'init'} 755 0 0\nfile /graph {out/'graph'} 755 0 0\n")
    with (out/"initramfs.cpio").open("xb") as stream:
        subprocess.run([cpio,listing],stdout=stream,check=True,timeout=60)
    if hashes(map(Path,pins))!=pins: raise ValueError("Build input drift")
    pins.update(hashes(path for path in out.iterdir() if path.is_file()))
    atomic_json(out/"manifest.json",pins)
    atomic_json(out/"build.json",dict(state="READY",execution="NOT_RUN",
        manifest_sha256=digest(out/"manifest.json"),live_repack_sha256=digest(repack),
        canonical_sha256=digest(canonical),
        scope="Actual live GGML translation unit and canonical helper; sealed independent graph inputs/oracle"))
    print(json.dumps(dict(state="READY",output=str(out))))


if __name__=="__main__": main()
