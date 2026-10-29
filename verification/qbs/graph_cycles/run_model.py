#!/usr/bin/env python3
"""Isolated Qwen3 probe ON/OFF run; no hardware performance claim."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE.parent/'tile_boundary'))
from run_ordinary import runtime
sys.path.insert(0,str(HERE))
from model_check import check


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    s=runtime.s
    s.require(out.is_relative_to(ROOT/'verification/out') and not out.exists(),'Fresh output required')
    out.mkdir();owner=runtime.Execution(out)
    old=ROOT/'verification/out/m4-sums-models-20261029-01/qwen3'
    compile_dir=ROOT/'verification/out/graph-cycles-compile-20261029-01'
    prepared=ROOT/'verification/out/graph-cycles-source-20261029-01'
    result=dict(state='FAIL',performance_measured=False)
    pins={}
    try:
        receipt=s.read_json(old/'result.json')
        s.require(receipt['state']=='PASS' and receipt['post_pins_match'],'Original run unaccepted')
        s.require(s.digest(old/'source-pins.json')==receipt['source_pins_sha256'],'Original pins')
        s.merge_pins(pins,s.read_json(old/'source-pins.json'));s.verify_pins(pins)
        compiled=s.read_json(compile_dir/'result.json')
        s.require(compiled['state']=='COMPILE_PASS_NOT_RUNTIME_ACCEPTED' and
                  compiled['off_preprocessed_equal'] and compiled['original_off_objects_equal'],'Probe compile')
        source=ROOT/'verification/akv/quantized_kv/prefill/sums_model_test.cpp'
        text=source.read_text().replace('M4_SUMS_MODEL','GRAPH_CYCLES_MODEL')
        text,n=re.subn(r'env\("GGML_RISCV_QBS_M4_PARALLEL_SUMS", mode \? "1" : "0"\);',
            'env("GGML_RISCV_QBS_M4_PARALLEL_SUMS", "1");\n    env("GGML_RISCV_NODE_CYCLES", mode ? "1" : "0");',text)
        s.require(n==1,'Selection anchor')
        text,n=re.subn(r'env\("(GGML_RISCV_[A-Z0-9_]*TRACE[A-Z0-9_]*)", "1"\);',
                       r'env("\1", "0");',text)
        s.require(n==5,'Trace switches changed')
        (out/'test.cpp').write_text(text)
        link=s.read_json(old/'link.command.json');cc=s.read_json(old/'compile.command.json')
        archive=next(Path(x) for x in link if x.endswith('/libggml-cpu.a'))
        isolated=out/'libggml-cpu.a';shutil.copyfile(archive,isolated)
        preparation=s.read_json(prepared/'preparation.json')
        s.verify_pins(preparation['artifacts'])
        s.require(s.digest(Path(preparation['source']))==preparation['source_sha256'], 'CPU source drift')
        probe_compile=s.read_json(compile_dir/'commands.json')[-1]
        s.require('-DGGML_RISCV_NODE_CYCLES=1' in probe_compile,'Missing probe compile option')
        probe_compile[probe_compile.index('-o')+1]=str(out/'ggml-cpu.c.o')
        owner.execute(probe_compile,out/'probe-compile.log',180,'PROBE_COMPILE')
        s.require(s.digest(out/'ggml-cpu.c.o')==s.digest(compile_dir/'on.o'),'Probe rebuild mismatch')
        ar=Path('/usr/bin/ar')
        owner.execute([ar,'r',isolated,out/'ggml-cpu.c.o'],out/'archive.log',120,'ARCHIVE')
        # Remove only the replaced member from copies, then compare all other members/index.
        for name,original in [('old-rest.a',archive),('new-rest.a',isolated)]:
            shutil.copyfile(original,out/name)
            owner.execute([ar,'d',out/name,'ggml-cpu.c.o'],out/(name+'.log'),120,'ARCHIVE_VERIFY')
        s.require(s.digest(out/'old-rest.a')==s.digest(out/'new-rest.a'),'Other library members changed')
        cc[cc.index('-c')+1]=str(out/'test.cpp');cc[cc.index('-o')+1]=str(out/'test.o')
        owner.execute(cc,out/'compile.log',180,'COMPILE')
        link=[str(isolated) if x==str(archive) else str(out/'test.o') if x.endswith('/test.o') else x for x in link]
        link=[('-Wl,-Map='+str(out/'link.map')) if x.startswith('-Wl,-Map=') else x for x in link]
        link[link.index('-o')+1]=str(out/'test');owner.execute(link,out/'link.log',180,'LINK')
        listing=(old/'initramfs.list').read_text().replace(str(old/'test'),str(out/'test'))
        (out/'initramfs.list').write_text(listing)
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        import subprocess
        with (out/'initramfs.cpio').open('wb') as f:
            subprocess.run([cpio,out/'initramfs.list'],stdout=f,check=True,timeout=60)
        qemu=s.read_json(old/'qemu.command.json');qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio')
        files=[Path(__file__),HERE/'model_check.py',prepared/'ggml-cpu.c',prepared/'records.h',
               compile_dir/'on.o',compile_dir/'result.json',out/'test.cpp',out/'test',isolated,
               out/'initramfs.cpio',out/'initramfs.list',cpio,ar,source,archive,old/'result.json']
        s.merge_pins(pins,s.hashes(files));s.verify_pins(pins);s.atomic_json(out/'source-pins.json',pins)
        owner.execute(qemu,out/'qemu.log',7200,'QEMU_FUNCTIONAL')
        measured=check((out/'qemu.log').read_text());s.verify_pins(pins)
        result.update(state='PASS',measured=measured,post_pins_match=True,
                      source_pins_sha256=s.digest(out/'source-pins.json'))
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:
        s.atomic_json(out/'result.json',result);owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    def interrupted(sig, _frame): raise InterruptedError(str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    main()
