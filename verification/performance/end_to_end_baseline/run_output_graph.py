#!/usr/bin/env python3
"""Isolated real-GGML native-QBS graph test; QEMU is functional only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from audit import digest,require,verify_pins
from prepare_output_backend import DELIVERY

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
VERIFY=Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
PLATFORM=Path('/home/wangwy/llama/platforms/cva6-qemu')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--llama',type=Path,default=Path('/home/wangwy/llama/llama.cpp'))
    a=p.parse_args();out=a.output.resolve()
    require(out.is_relative_to(VERIFY/'verification/out'),'Use verification output area')
    out.mkdir(parents=True,exist_ok=False)
    pins={};commands=[];state=dict(state='PREPARING',functional_only=True,performance_measured=False)
    def save(): (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def pin(path):
        path=Path(path).resolve(strict=True);sha=digest(path)
        require(str(path) not in pins or pins[str(path)]==sha,'Input drift: '+str(path));pins[str(path)]=sha
    def run(argv,label,bound=180):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv,timeout=bound));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        state.update(state=label.upper());save()
        with (out/(label+'.log')).open('wb') as log:
            child=subprocess.Popen(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT)
            state['child_pid']=child.pid;save()
            try:rc=child.wait(timeout=bound)
            except BaseException:child.kill();child.wait();raise
            finally:state['child_pid']=None;save()
        require(rc==0,label+' failed');return (out/(label+'.log')).read_text(errors='replace')
    try:
        for path in (Path(__file__),HERE/'audit.py',HERE/'prepare_output_backend.py',
                     HERE/'ggml/CMakeLists.txt',HERE/'ggml/test.cpp',a.prepared/'result.json',a.prepared/'output-tile.patch'):pin(path)
        prepared=json.loads((a.prepared/'result.json').read_text())
        require(prepared['delivery']==DELIVERY and prepared['patch_sha256']==digest(a.prepared/'output-tile.patch'),'Patch identity')
        sdk_commit=subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        for name,repo,commit,paths in (('llama',a.llama,DELIVERY,[]),('sdk',ROOT,sdk_commit,['software/qbs','software/akv'])):
            run(['/usr/bin/git','-C',repo,'archive','--format=tar','--output='+str(out/(name+'.tar')),commit,*paths],name+'-archive')
            pin(out/(name+'.tar'));(out/name).mkdir()
            run(['/usr/bin/tar','-xf',out/(name+'.tar'),'-C',out/name],name+'-extract')
        run(['/usr/bin/patch','--batch','--fuzz=0','-d',out/'llama','-p1','-i',a.prepared.resolve()/'output-tile.patch'],'apply-patch')
        for name,hashes in prepared['files'].items():require(digest(out/'llama'/name)==hashes['after_sha256'],'Patched source mismatch')
        asm='software/akv/src/akv_v2_attention_rvv.S'
        delivered=subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'show','1e48e205df5cec34183222c36d22eb4858466810:'+asm])
        require(digest(out/'sdk'/asm)==hashlib.sha256(delivered).hexdigest(),'Non-delivery AKV assembly')
        for tree in (out/'llama',out/'sdk'):
            for path in tree.rglob('*'):
                if path.is_file():pin(path)
        cc=PLATFORM/'tools/bin/riscv64-linux-gcc';cxx=cc.with_name('riscv64-linux-g++')
        for compiler,name in ((cc,'cc1'),(cxx,'cc1plus'),(cc,'as'),(cc,'ld')):
            pin(run([compiler,'-print-prog-name='+name],'locate-'+name).strip())
        cmake=shutil.which('cmake');require(cmake is not None,'CMake unavailable')
        run([cmake,'-S',HERE/'ggml','-B',out/'build','-DCMAKE_SYSTEM_NAME=Linux',
             '-DCMAKE_SYSTEM_PROCESSOR=riscv64','-DCMAKE_C_COMPILER='+str(cc),'-DCMAKE_CXX_COMPILER='+str(cxx),
             '-DCMAKE_C_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d',
             '-DCMAKE_CXX_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d',
             '-DCMAKE_BUILD_TYPE=Release','-DGGML_CCACHE=OFF',
             '-DLLAMA_SOURCE_DIR='+str(out/'llama'),'-DSDK_ROOT='+str(out/'sdk')],'configure')
        run([cmake,'--build',out/'build','--target','output-graph','-j','16'],'build',900)
        compile_commands=json.loads((out/'build/compile_commands.json').read_text());pin(out/'build/compile_commands.json')
        front=[r for r in compile_commands if r['file'].endswith('/arch/riscv/quant-kv.cpp')]
        candidates=[r for r in compile_commands if r['file'].endswith('/output_tile/runtime.c')]
        require(len(front)==len(candidates)==1 and 'GGML_USE_RISCV_OUTPUT_TILE' in front[0]['command'],'CMake dispatch/source identity')
        program=out/'build/output-graph';pin(program)
        init=ROOT/'verification/akv/quantized_kv/ggml_live/init.c';pin(init)
        run([cc,'-O2','-static',init,'-o',out/'init'],'build-init');pin(out/'init')
        listing='dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
        listing+=f'file /init {out/"init"} 755 0 0\nfile /test {program} 755 0 0\n'
        for q3 in (False,True):
            archive=VERIFY/'verification/out'/('quant-prefill-capture-20261028-01' if q3 else 'akv-quantkv-host-capture-20261024-01')
            receipt=archive/('manifest.json' if q3 else 'result.json');pin(receipt)
            info=json.loads(receipt.read_text())
            for kind in ('q4_0','q8_0'):
                capture=archive/(kind+'/prefill/block' if q3 else 'capture-k-'+kind+'-v-q8_0/decode/block')
                known=info if q3 else info['captures'][kind]['file_sha256']
                guest=('qwen3' if q3 else 'qwen25')+('_q4' if kind=='q4_0' else '_q8')
                listing+='dir /'+guest+' 755 0 0\n'
                for name in ('attn_q_input-0.bin','attn_k_input-0.bin','attn_v_input-0.bin','attn_mask_input-0.bin','kqv_out-0.bin'):
                    source=capture/name;require(known.get(str(source))==digest(source),'Captured data drift');pin(source)
                    listing+=f'file /{guest}/{name} {source} 644 0 0\n'
        (out/'initramfs.list').write_text(listing);pin(out/'initramfs.list')
        cpio=PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio';pin(cpio)
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([cpio,out/'initramfs.list'],stdout=f,check=True,timeout=60)
        pin(out/'initramfs.cpio')
        qemu=VERIFY/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
        kernel=PLATFORM/'images/Image';fw=PLATFORM/'images/fw_dynamic.bin'
        for path in (qemu,kernel,fw):pin(path)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        text=run([qemu,'-M','virt','-cpu','rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true',
            '-smp','1','-m','512M','-display','none','-monitor','none','-serial','stdio',
            '-bios',fw,'-kernel',kernel,'-initrd',out/'initramfs.cpio','-append','console=ttyS0 rdinit=/init'],'qemu',600).replace('\r','')
        require(text.splitlines().count('OUTPUT_GRAPH_SUITE_PASS profiles=4 native_calls=12 fallback_calls=8')==1 and
                text.splitlines().count('GUEST_TEST_EXIT=0')==1 and 'Kernel panic' not in text,'Guest graph check failed')
        verify_pins(pins)
        state.update(state='GRAPH_FUNCTIONAL_PASS_PENDING_INDEPENDENT_TRACE_AUDIT',sdk_commit=sdk_commit,
                     elf_sha256=digest(program),log_sha256=digest(out/'qemu.log'),production_changed=False)
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save();(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':main()
