#!/usr/bin/env python3
"""Qwen3 Register-PV OFF/ON model pair with grouped Prefill unchanged."""
import argparse
import json
from pathlib import Path
import subprocess
from run_replay import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def check(text):
    lines=text.replace('\r','').splitlines()
    expected=[f'REGISTER_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
              for k in range(2) for s in range(3)]
    assert [l for l in lines if l.startswith('REGISTER_MODEL_COMPARE ')]==expected
    assert lines.count('REGISTER_MODEL_SUITE_PASS comparisons=6 performance=not_measured')==1
    assert lines.count('GUEST_TEST_EXIT=0')==1 and 'REGISTER_MODEL_FAIL' not in text
    mode=None;prefill={0:[],1:[]};decode={0:[],1:[]};register={0:[],1:[]}
    for line in lines:
        if line.startswith('REGISTER_MODEL_BEGIN '):mode=int(line.split('enabled=')[1])
        elif line.startswith('REGISTER_MODEL_END '):mode=None
        elif line.startswith('GGML_RISCV_QUANT_KV_REGISTER_PV '):
            assert mode in (0,1)
            fields={k:int(v) for k,v in (x.split('=',1) for x in line.split()[1:])}
            assert fields['enabled']==mode and fields['status']==0 and fields['completed_groups']>0
            register[mode].append(fields)
        elif line.startswith(('GGML_RISCV_QUANT_PREFILL ','GGML_RISCV_QUANT_KV ')):
            assert mode in (0,1)
            fields={k:int(v) for k,v in (x.split('=',1) for x in line.split()[1:])}
            if line.startswith('GGML_RISCV_QUANT_PREFILL '):prefill[mode].append(fields)
            elif fields['status']==0:decode[mode].append(fields)
    assert len(prefill[0])==len(prefill[1])==56 and prefill[0]==prefill[1]
    assert all(x['status']==0 and x['mapping']==0 and x['selection']==0 and
               x['commands']>0 and x['groups']>0 for x in prefill[1])
    assert len(decode[0])==len(decode[1])==112
    assert decode[0]==decode[1]
    assert len(register[0])==len(register[1])==112
    assert [x['completed_groups'] for x in register[0]]==[x['completed_groups'] for x in register[1]]
    return dict(comparisons=6,logits_compared=911616,prefill_completed_per_mode=56,register_completed_per_mode=112,
                decode_completed_per_mode=112,decode_activity_equal=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--library-build',type=Path,default=ROOT/'verification/out/register-pv-ggml-build-20261028-01')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    build=args.library_build.resolve(strict=True)
    report=json.loads((build/'result.json').read_text());assert report['state']=='PASS'
    assert report['configurations']['ON']['register_pv_compiled'] is True
    pins=json.loads((build/'source-pins.json').read_text())
    assert digest(build/'source-pins.json')==report['source_pins_sha256']
    pins.update(report['configurations']['ON']['libraries'])
    prior=ROOT/'verification/out/m4-packed-normal-model-20261028-01'
    compile_cmd=json.loads((prior/'compile-test.command.json').read_text())
    link=json.loads((prior/'link.command.json').read_text())
    qemu=json.loads((prior/'qemu.command.json').read_text())
    qemu[qemu.index('-drive')+1]='file=/home/wangwy/llama/platforms/cva6-qemu/images/model-generality/qwen3_1p7b_q4km.ext4,if=virtio,format=raw,readonly=on'
    init=ROOT/'verification/out/q8k-signed-max-model-20261026-01/init'
    old=json.loads((prior/'manifest.json').read_text());assert old[str(init)]==digest(init)
    cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
    disk=Path(qemu[qemu.index('-drive')+1].split(',')[0].removeprefix('file='))
    for p in (Path(__file__),HERE/'run_replay.py',HERE/'register_model_test.cpp',init,cpio,disk,
              Path(qemu[0]),Path(qemu[qemu.index('-bios')+1]),Path(qemu[qemu.index('-kernel')+1]),Path(compile_cmd[0])):
        pins[str(p)]=digest(p)
    def save(name,value):
        p=out/name;tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
    def verify():
        for p,h in pins.items():assert digest(p)==h,p
    def run(argv,label,bound=180):
        verify();save('status.json',dict(state=label));save(label+'.command.json',argv)
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=bound)
        verify()
    result=dict(state='FAIL',performance_measured=False)
    try:
        compile_cmd[compile_cmd.index('-c')+1]=str(HERE/'register_model_test.cpp')
        compile_cmd[compile_cmd.index('-o')+1]=str(out/'test.o');run(compile_cmd,'compile')
        old_build=str(ROOT/'verification/out/m4-packed-normal-build-20261028-01/build')
        link=[str(out/'test.o') if x.endswith('/test.o') else x.replace(old_build,str(build/'on')) for x in link]
        link=['-Wl,-Map='+str(out/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
        link[link.index('-o')+1]=str(out/'test');run(link,'link')
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
                           'dir /model 755 0 0\ndir /tmp 1777 0 0\n'
                           f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        image=out/'initramfs.cpio'
        with image.open('wb') as stream:subprocess.run([cpio,listing],stdout=stream,check=True,timeout=60)
        for p in (out/'test',listing,image):pins[str(p)]=digest(p)
        save('source-pins.json',pins)
        qemu[qemu.index('-initrd')+1]=str(image);run(qemu,'qemu',7200)
        measured=check((out/'qemu.log').read_text());result.update(state='PASS',measured=measured,
            post_pins_match=True,source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:
        save('result.json',result);save('status.json',dict(state=result['state']))


if __name__=='__main__':main()
