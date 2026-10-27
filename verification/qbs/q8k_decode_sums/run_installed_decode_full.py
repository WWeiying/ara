#!/usr/bin/env python3
"""Actual installed quantizer object versus separate pre-integration function."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,hashes,digest
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build=a.build.resolve(strict=True);out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    pins=json.loads((build/'manifest.json').read_text())
    if json.loads((build/'result.json').read_text())['state']!='INSTALLED_DECODE_COMPILE_EQUIVALENT' or hashes(map(Path,pins))!=pins:
        raise ValueError('Installed build drift')
    before=a.before.resolve(strict=True)
    text=before.read_text();start=text.index('void quantize_row_q8_K(')
    end=text.index('//===================================== Dot products',start)
    platform=Path('/home/wangwy/llama/platforms/cva6-qemu')
    qemu=ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
    cpio=platform/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
    source_cmd=json.loads((build/'command.json').read_text())
    base=ROOT/'verification/out/q8k-signed-max-model-20261026-01'
    link=json.loads((base/'link.command.json').read_text())
    artifacts=[Path(x) for x in link if x.endswith(('.a','.o')) and x!=str(base/'test.o')]
    archived=json.loads((base/'manifest.json').read_text())
    if any(archived.get(str(x))!=digest(x) for x in artifacts):raise ValueError('Compatible library drift')
    pins.update(hashes([before,Path(__file__),HERE/'full_test.c',qemu,cpio,init,
                       platform/'images/Image',platform/'images/fw_dynamic.bin',*artifacts]))
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,label,limit):
        cmd=list(map(str,cmd));state.update(state=label.upper(),child_pid=None);save()
        atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started):raise RuntimeError(label+' failed')
    try:
        prefix='#define GGML_COMMON_DECL_C\n#include "ggml-common.h"\n#include "ggml-quants.h"\n#include <riscv_vector.h>\n#include <math.h>\n#include <string.h>\n#include <assert.h>\n#define GGML_RESTRICT restrict\n'
        original=out/'original.c'
        original.write_text(prefix+text[start:end].replace('void quantize_row_q8_K(','void decode_original(',1))
        bridge=out/'bridge.c'
        bridge.write_text('#include "ggml-quants.h"\nvoid quantize_row_q8_K(const float *, void *, int64_t);\nvoid decode_candidate(const float *x,void *y,int64_t k){quantize_row_q8_K(x,y,k);}\n')
        header=out/'quantizers.h'
        header.write_text(prefix+'void decode_original(const float *,void *,int64_t);\nvoid decode_candidate(const float *,void *,int64_t);\n')
        objects=[]
        for name,src in (('original',original),('bridge',bridge),('test',HERE/'full_test.c')):
            cmd=list(source_cmd);cmd[cmd.index('-c')+1]=str(src)
            obj=out/(name+'.o');cmd[cmd.index('-o')+1]=str(obj)
            cmd+=['-I'+str(out)]
            if name=='test':cmd+=['-fno-tree-vectorize']
            run(cmd,'compile-'+name,180);objects.append(obj)
        # Actual installed full TU supplies decode_candidate's production callee.
        link[link.index(str(base/'test.o'))]=str(objects[-1])
        link[link.index('-o')+1]=str(out/'test')
        link=[('-Wl,-Map='+str(out/'link.map')) if x.startswith('-Wl,-Map=') else x for x in link]
        link[2:2]=list(map(str,objects[:-1]))+[str(build/'quants.c.o')]
        run(link,'link',180)
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
                           f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as f:
            subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([original,bridge,header,listing,out/'initramfs.cpio',out/'test',*objects]))
        atomic_json(out/'manifest.json',pins)
        for vlen in (128,256,512,1024):
            label='qemu-'+str(vlen)
            run([qemu,'-M','virt','-cpu',f'rv64,v=true,vlen={vlen},elen=64,zfh=true,zvfh=true,xaraqbs=true',
                 '-smp','1','-m','512M','-display','none','-monitor','none','-serial','stdio',
                 '-bios',platform/'images/fw_dynamic.bin','-kernel',platform/'images/Image',
                 '-initrd',out/'initramfs.cpio','-append','console=ttyS0 rdinit=/init'],label,600)
            lines=(out/(label+'.log')).read_text().splitlines()
            if lines.count('Q8K_DECODE_FULL_PASS checks=2880')!=1 or lines.count('GUEST_TEST_EXIT=0')!=1:
                raise ValueError('Missing complete installed-quantizer acceptance')
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',vlen=[128,256,512,1024],checks=11520,
                     scope='Actual installed quantizer object; 12 patterns, six K, all legal rounding/CSR settings')
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc));raise
    finally:
        state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
