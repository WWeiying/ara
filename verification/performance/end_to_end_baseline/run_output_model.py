#!/usr/bin/env python3
"""Build complete llama.cpp and compare Qwen3 Register-PV/output-tile logits."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from audit import digest,require,verify_pins

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
VERIFY=Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_ggml_segmented import verify_native_build


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--graph-build',type=Path,required=True);p.add_argument('--graph-replay',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();require(out.is_relative_to(VERIFY/'verification/out'),'Verification output required')
    out.mkdir(parents=True,exist_ok=False);pins={};commands=[]
    state=dict(state='PREPARING',functional_only=True,performance_measured=False)
    def save(): (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def pin(path):
        path=Path(path).resolve(strict=True);sha=digest(path)
        require(str(path) not in pins or pins[str(path)]==sha,'Source drift');pins[str(path)]=sha
    def run(argv,label,bound=180):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv,timeout=bound));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        state['state']=label.upper();save()
        with (out/(label+'.log')).open('wb') as log:
            child=subprocess.Popen(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT)
            state['child_pid']=child.pid;save()
            try:code=child.wait(timeout=bound)
            except BaseException:child.kill();child.wait();raise
            finally:state['child_pid']=None;save()
        require(code==0,label+' failed')
    try:
        accepted=json.loads((a.graph_replay/'result.json').read_text())
        require(accepted['state']=='GRAPH_FUNCTIONAL_AND_DISPATCH_PASS','Graph gate incomplete')
        require(digest(a.graph_replay/'source-pins.json')==accepted['source_pins_sha256'],'Graph pin map drift')
        pins.update(json.loads((a.graph_replay/'source-pins.json').read_text()));verify_pins(pins)
        for path in (Path(__file__),HERE/'audit.py',a.graph_replay/'result.json'):pin(path)
        recipe=VERIFY/'verification/out/register-pv-final-models-20261028-01'
        config=json.loads((recipe/'libraries/configure-on.command.json').read_text())
        for path in (recipe/'libraries/configure-on.command.json',recipe/'qwen3/compile.command.json',
                     recipe/'qwen3/qemu.command.json',recipe/'qwen3/source-pins.json'):pin(path)
        config[0]=shutil.which('cmake');require(config[0] is not None,'CMake missing')
        config[config.index('-S')+1]=str(a.graph_build/'llama');config[config.index('-B')+1]=str(out/'build')
        for i,v in enumerate(config):
            if v.startswith('-DGGML_RISCV_QBS_RUNTIME_DIR='):config[i]='-DGGML_RISCV_QBS_RUNTIME_DIR='+str(a.graph_build/'sdk/software/qbs')
            elif v.startswith('-DGGML_RISCV_AKV_RUNTIME_DIR='):config[i]='-DGGML_RISCV_AKV_RUNTIME_DIR='+str(a.graph_build/'sdk/software/akv')
        pin(config[config.index(next(v for v in config if v.startswith('-DCMAKE_TOOLCHAIN_FILE=')))].split('=',1)[1])
        config.append('-DGGML_RISCV_AKV_OUTPUT_TILE=ON');config.append('-DGGML_CCACHE=OFF')
        run(config,'configure')
        run([config[0],'--build',out/'build','--target','llama','-j','16'],'build',1200)
        # Exact mechanical successor of the accepted model fixture. Change only
        # the comparison's two choices, labels and high-volume debug logging.
        fixture='verification/akv/quantized_kv/prefill/register_model_test.cpp'
        source=subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'show','HEAD:'+fixture],text=True)
        anchor='env("GGML_RISCV_AKV_REGISTER_PV", mode ? "1" : "0");'
        require(source.count(anchor)==1,'Model fixture anchor')
        source=source.replace(anchor,'env("GGML_RISCV_AKV_REGISTER_PV", mode ? "0" : "1");\n    env("GGML_RISCV_AKV_OUTPUT_TILE", mode ? "1" : "0");',1)
        source=source.replace('REGISTER_MODEL','OUTPUT_MODEL').replace('/tmp/register-','/tmp/output-')
        for key in ('GGML_RISCV_QBS_TRACE','GGML_RISCV_QBS_TRACE_LIFETIME','GGML_RISCV_QBS_TRACE_M4_PREPARE'):
            source=source.replace('env("'+key+'", "1")','env("'+key+'", "0")')
        (out/'model.cpp').write_text(source);pin(out/'model.cpp')
        cc=json.loads((recipe/'qwen3/compile.command.json').read_text())
        cc=[('-I'+str(a.graph_build/'llama/include')) if v=='-I/home/wangwy/llama/llama.cpp/include' else
            ('-I'+str(a.graph_build/'llama/ggml/include')) if v=='-I/home/wangwy/llama/llama.cpp/ggml/include' else v for v in cc]
        cc[cc.index('-c')+1]=str(out/'model.cpp');cc[cc.index('-o')+1]=str(out/'model.o')
        run(cc,'compile')
        libs=[out/'build/src/libllama.a',*[out/'build/ggml/src'/name for name in ('libggml.a','libggml-cpu.a','libggml-base.a')]]
        for path in libs:pin(path)
        run([cc[0],'-static',out/'model.o',*libs,'-ldl','-lm','-pthread','-o',out/'test'],'link');pin(out/'test')
        init=VERIFY/'verification/out/q8k-signed-max-model-20261026-01/init'
        old=json.loads((recipe/'qwen3/source-pins.json').read_text());require(old.get(str(init))==digest(init),'Init identity')
        pin(init)
        listing='dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\ndir /tmp 1777 0 0\n'
        listing+=f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n'
        (out/'initramfs.list').write_text(listing);pin(out/'initramfs.list')
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio');pin(cpio)
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([cpio,out/'initramfs.list'],stdout=f,check=True,timeout=60)
        pin(out/'initramfs.cpio')
        qemu=json.loads((recipe/'qwen3/qemu.command.json').read_text());qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio')
        require('xaraqbs=true' in qemu[qemu.index('-cpu')+1],'Native CPU flag missing')
        for path in verify_native_build(Path(qemu[0])):pin(path)
        disk=Path(qemu[qemu.index('-drive')+1].split(',',1)[0].removeprefix('file='))
        for path in (Path(qemu[0]),Path(qemu[qemu.index('-kernel')+1]),Path(qemu[qemu.index('-bios')+1]),disk):pin(path)
        require(old.get(str(disk))==digest(disk),'Model disk identity')
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        run(qemu,'qemu',7200)
        state.update(state='MODEL_EXECUTED_PENDING_INDEPENDENT_AUDIT',elf_sha256=digest(out/'test'),
                     log_sha256=digest(out/'qemu.log'),source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save();(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':main()
