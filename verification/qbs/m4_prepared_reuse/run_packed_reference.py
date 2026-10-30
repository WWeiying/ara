#!/usr/bin/env python3
"""Keep the exact 808-case suite; replace only the candidate symbol/labels."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes
from run_tile_context_engine import run_command


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out') or out.exists():raise ValueError('Fresh independent output required')
    prior=ROOT/'verification/out/m4-tiled-reference-20261027-02'
    pins=json.loads((prior/'manifest.json').read_text())
    if json.loads((prior/'result.json').read_text())['state']!='PASS' or hashes(map(Path,pins))!=pins:
        raise ValueError('Original comparison/source drift')
    source=(HERE/'tiled_test.cpp').read_text()
    if source.count('m4_tiled_produce')!=2 or source.count('TILED_M4_')!=2:raise ValueError('Unreviewed test adaptation')
    source=source.replace('m4_tiled_produce','m4_packed_produce').replace('TILED_M4_','PACKED_M4_')
    pins.update(hashes([Path(__file__),HERE/'packed_producer.cpp',HERE/'packed_candidate.h',prior/'result.json']))
    out.mkdir(parents=True);state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,performance_measured=False)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,name,limit=180):
        cmd=list(map(str,cmd));atomic_json(out/(name+'.command.json'),cmd);state['state']=name.upper();save()
        if run_command(cmd,out/(name+'.log'),limit,os.environ.copy(),started):raise RuntimeError(name+' failed')
    try:
        test=out/'test.cpp';test.write_text(source)
        objects=[prior/'0.o']
        for index,path in enumerate((HERE/'packed_producer.cpp',test),1):
            command=json.loads((prior/f'compile-{index}.command.json').read_text())
            command[command.index('-c')+1]=str(path);obj=out/f'{index}.o';command[command.index('-o')+1]=str(obj)
            run(command,'compile-'+str(index));objects.append(obj)
        objects.append(prior/'3.o')
        old_link=json.loads((prior/'link.command.json').read_text())
        libraries=[Path(arg) for arg in old_link if arg.endswith('.a')]
        run([old_link[0],'-static',*objects,*libraries,'-ldl','-lm','-pthread','-o',out/'test'],'link')
        listing=subprocess.check_output([str(Path(old_link[0]).with_name('riscv64-linux-objdump')),'-d',out/'test'],text=True)
        # No segment instruction may be present in the reachable candidate body.
        body='';current=''
        for line in listing.splitlines():
            if line.endswith('>:'):current=line
            if 'm4_packed_candidate' in current:body+=line+'\n'
        if not body or 'vse32.v' not in body or 'vsseg' in body or 'vsse8.v' in body:raise ValueError('Packed store codegen')
        (out/'candidate-disassembly.log').write_text(body)
        qemu=json.loads((prior/'qemu-1024.command.json').read_text())
        init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        recipe=out/'initramfs.list';recipe.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as stream:subprocess.run([str(cpio),str(recipe)],stdout=stream,check=True,timeout=60)
        pins.update(hashes([test,out/'test',out/'candidate-disassembly.log',recipe,out/'initramfs.cpio',*objects]))
        atomic_json(out/'manifest.json',pins);qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio')
        configurations=[]
        for vlen in (128,256,512,1024):
            cmd=list(qemu);cmd[cmd.index('-cpu')+1]=f'rv64,v=true,vlen={vlen},elen=64,zfh=true,zvfh=true,xaraqbs=false'
            run(cmd,'qemu-'+str(vlen),600);log=out/f'qemu-{vlen}.log';lines=log.read_text().splitlines()
            if lines.count('PACKED_M4_PASS checks=808 real_groups=3 generated_cases=4 bytes=7008')!=1 or \
               lines.count('GUEST_TEST_EXIT=0')!=1:raise ValueError('Missing full packed comparison')
            configurations.append(dict(vlen=vlen,checks=808,log_sha256=digest(log)))
        if hashes(map(Path,pins))!=pins:raise ValueError('Source drift')
        state.update(state='PASS',configurations=configurations,
            scope='Exact bytes/CSR/fallback at four VLENs; no graph integration or hardware performance')
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
