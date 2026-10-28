#!/usr/bin/env python3
"""Execute normal OFF/ON GGML graph binaries in QBS-capable QEMU."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from run_replay import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PLATFORM=Path('/home/wangwy/llama/platforms/cva6-qemu')


def check_log(text, enabled_build):
    lines=text.replace('\r','').splitlines()
    assert lines.count('GUEST_TEST_EXIT=0')==1
    assert lines.count('PREFILL_GRAPH_SUITE_PASS profiles=2 calls=8 performance=not_measured')==1
    seen=[];pending=None;traces=[]
    for line in lines:
        if line.startswith('PREFILL_GRAPH_BEGIN '):
            assert pending is None
            m=re.fullmatch(r'PREFILL_GRAPH_BEGIN kind=(q8_0|q4_0) hole=([01]) enabled=([01])',line);assert m
            pending=(m[1],int(m[2]),int(m[3]));traces=[]
        elif line.startswith('GGML_RISCV_QUANT_PREFILL '):
            assert pending is not None
            fields=dict(item.split('=',1) for item in line.split()[1:])
            traces.append({k:int(v) for k,v in fields.items()})
        elif line.startswith('PREFILL_GRAPH_END '):
            m=re.fullmatch(r'PREFILL_GRAPH_END kind=(q8_0|q4_0) hole=([01]) enabled=([01]) outputs=40960 max_abs=([^ ]+) fcsr=(\d+) vcsr=(\d+)',line);assert m
            assert pending==(m[1],int(m[2]),int(m[3]))
            assert int(m[5])<=31 and int(m[5])&8 and int(m[6])==5
            if enabled_build and pending[2]:
                assert len(traces)==1; t=traces[0]
                assert t['mapping']==0 and t['memory']==1 and t['runtime_called']==1
                if pending[1]:
                    assert t['status']==1 and t['commands']==t['groups']==t['queries_quantized']==0
                    assert t['selection']!=0
                else:
                    assert t['status']==t['selection']==0 and t['commands']==160
                    assert t['groups']==40 and t['value_decodes']==480 and t['queries_quantized']==320
            else: assert not traces
            seen.append(pending);pending=None
    assert pending is None
    assert seen==[(k,h,e) for k in ('q8_0','q4_0') for h in (0,1) for e in (0,1)]
    return dict(calls=8,native_completed=2 if enabled_build else 0,
                rejected_mask=2 if enabled_build else 0)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    build=ROOT/'verification/out/prefill-graph-build-20261028-01'
    report=json.loads((build/'result.json').read_text());assert report['state']=='BUILT_NOT_EXECUTED'
    pins=json.loads((build/'source-pins.json').read_text())
    assert digest(build/'source-pins.json')==report['source_pins_sha256']
    audit=ROOT/'verification/out/quant-prefill-capture-audit-20261028-01'
    for p,h in json.loads((audit/'manifest.json').read_text()).items():
        assert p not in pins or pins[p]==h;pins[p]=h
    qemu=ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
    cpio=PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    init_source=HERE.parent/'ggml_live/init.c'
    for p in (Path(__file__),HERE/'run_replay.py',qemu,cpio,init_source,
              PLATFORM/'images/Image',PLATFORM/'images/fw_dynamic.bin'):
        pins[str(p)]=digest(p)
    def save(name,value):
        p=out/name;tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
    def verify():
        for p,h in pins.items():assert digest(p)==h,p
    def run(argv,label,timeout=120):
        verify();save('status.json',dict(state=label));save(label+'.command.json',list(map(str,argv)))
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout)
        verify()
    result=dict(state='FAIL',performance_measured=False)
    try:
        run([PLATFORM/'tools/bin/riscv64-linux-gcc','-march=rv64gc','-mabi=lp64d','-O2','-static',init_source,'-o',out/'init'],'init-build')
        pins[str(out/'init')]=digest(out/'init');results={}
        for mode in ('off','on'):
            elf=Path(report['executables'][mode]['path'])
            assert digest(elf)==report['executables'][mode]['sha256'];pins[str(elf)]=digest(elf)
            listing=['dir /dev 755 0 0','nod /dev/console 600 0 0 c 5 1',
                     f'file /init {out / "init"} 755 0 0',f'file /test {elf} 755 0 0']
            for kind in ('q4_0','q8_0'):
                listing.append(f'dir /{kind} 755 0 0')
                data=ROOT/'verification/out/quant-prefill-capture-20261028-01'/kind/'prefill/block'
                for name in ('attn_q_input-0.bin','attn_k_input-0.bin','attn_v_input-0.bin','attn_mask_input-0.bin','kqv_out-0.bin'):
                    listing.append(f'file /{kind}/{name} {data/name} 644 0 0')
            spec=out/(mode+'.list');spec.write_text('\n'.join(listing)+'\n');image=out/(mode+'.cpio')
            with image.open('wb') as target:
                subprocess.run([cpio,spec],stdout=target,check=True,timeout=60)
            pins[str(spec)]=digest(spec);pins[str(image)]=digest(image);save('source-pins.json',pins)
            run([qemu,'-M','virt','-cpu','rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
                 '-smp','1','-m','512M','-display','none','-monitor','none','-serial','stdio',
                 '-bios',PLATFORM/'images/fw_dynamic.bin','-kernel',PLATFORM/'images/Image',
                 '-initrd',image,'-append','console=ttyS0 rdinit=/init'],'qemu-'+mode,1800)
            results[mode]=check_log((out/('qemu-'+mode+'.log')).read_text(),mode=='on')
        result.update(state='PASS',results=results,post_pins_match=True,
                      source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:
        save('result.json',result);save('status.json',dict(state=result['state']))


if __name__=='__main__':main()
