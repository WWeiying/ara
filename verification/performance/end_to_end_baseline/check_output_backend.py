#!/usr/bin/env python3
"""Target-compile all opt-in combinations against an isolated delivery tree."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from audit import digest,require,verify_pins
from prepare_output_backend import DELIVERY,ADAPTER

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CC=Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-g++')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--llama',type=Path,default=Path('/home/wangwy/llama/llama.cpp'))
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    r=json.loads((a.prepared/'result.json').read_text())
    require(r['delivery']==DELIVERY and r['state']=='ADAPTER_PREPARED_NOT_COMPILED_OR_EXECUTED','Prepared scope')
    pins={};commands=[]
    def pin(path):
        path=Path(path).resolve(strict=True);sha=digest(path)
        require(str(path) not in pins or pins[str(path)]==sha,'Input drift');pins[str(path)]=sha
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        t=subprocess.run(argv,cwd=out,capture_output=True,timeout=180)
        (out/(label+'.stdout')).write_bytes(t.stdout);(out/(label+'.stderr')).write_bytes(t.stderr)
        require(t.returncode==0,label+' failed');return t.stdout.decode()
    for path in (Path(__file__),HERE/'audit.py',HERE/'prepare_output_backend.py',a.prepared/'result.json',a.prepared/'output-tile.patch'):pin(path)
    require(digest(a.prepared/'output-tile.patch')==r['patch_sha256'],'Patch changed')
    run(['/usr/bin/git','-C',a.llama,'archive','--format=tar','--output='+str(out/'delivery.tar'),DELIVERY,'ggml'],'archive')
    pin(out/'delivery.tar');tree=out/'tree';tree.mkdir()
    run(['/usr/bin/tar','-xf',out/'delivery.tar','-C',tree],'extract')
    # Patch requires the exact delivery preimages and yields exact reviewed files.
    for name,hashes in r['files'].items():require(digest(tree/name)==hashes['before_sha256'],'Preimage mismatch')
    run(['/usr/bin/patch','--batch','--fuzz=0','-d',tree,'-p1','-i',(a.prepared/'output-tile.patch').resolve()],'patch')
    for name,hashes in r['files'].items():require(digest(tree/name)==hashes['after_sha256'],'Postimage mismatch')
    base=[CC,'-O3','-std=c++17','-march=rv64gcv_zfh_zvfh','-mabi=lp64d',
          '-fno-fast-math','-ffp-contract=fast','-Wall','-Wextra','-Werror',
          '-Wno-unused-function','-Wno-error=strict-aliasing','-DGGML_USE_RISCV_QUANT_KV']
    for path in (ROOT,ROOT/'software/qbs/include',ROOT/'software/akv/experimental/quantized_kv',
                 tree/'ggml/include',tree/'ggml/src',tree/'ggml/src/ggml-cpu'):
        base.append('-I'+str(path))
    for name in ('cc1plus','as'):
        pin(run([CC,'-print-prog-name='+name],'locate-'+name).strip())
    checks=[]
    for mode,defines in {'off':[], 'register':['GGML_USE_RISCV_REGISTER_PV'],
                         'output':['GGML_USE_RISCV_OUTPUT_TILE'],
                         'both':['GGML_USE_RISCV_REGISTER_PV','GGML_USE_RISCV_OUTPUT_TILE']}.items():
        flags=[*base,*['-D'+name for name in defines]]
        deps=run([*flags,'-M','-MT','object',tree/ADAPTER],mode+'-deps')
        for dep in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):pin(dep)
        run([*flags,'-c',tree/ADAPTER,'-o',out/(mode+'.o')],mode+'-compile')
        symbols=run([CC.with_name('riscv64-linux-nm'),'-u',out/(mode+'.o')],mode+'-symbols')
        require(('quant_output_tile_execute' in symbols)==('GGML_USE_RISCV_OUTPUT_TILE' in defines),'Output route linkage')
        require(('quant_register_execute' in symbols)==('GGML_USE_RISCV_REGISTER_PV' in defines),'Register route linkage')
        checks.append(dict(mode=mode,state='TARGET_OBJECT_COMPILED',object_sha256=digest(out/(mode+'.o'))))
    verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='TARGET_ADAPTER_COMPILE_PASS_NOT_GRAPH_ACCEPTANCE',checks=checks,
                checkout_changed=False,production_enabled=False,source_pins_sha256=digest(out/'source-pins.json'))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['state'])


if __name__=='__main__':main()
