#!/usr/bin/env python3
"""Rebuild a captured-context successor without changing the sealed first pair."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipe-build',type=Path,required=True)
    p.add_argument('--query-index',type=int,choices=range(20),required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prior=a.recipe_build.resolve(strict=True);out=a.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Fresh output required')
    report=json.loads((prior/'build.json').read_text())
    if (report.get('register_pv') is not True or report['state']!='BUILT_NOT_EXECUTED' or
        report['rebuilt_objects']!=17 or report['capture_inputs_checked']!=10):
        raise ValueError('Expected audited real-data register-PV recipe')
    if digest(prior/'source-pins.json')!=report['source_pins_sha256']:raise ValueError('Recipe pins')
    pins=json.loads((prior/'source-pins.json').read_text())
    for path,h in report['artifacts'].items():
        if path in pins and pins[path]!=h:raise ValueError('Conflicting pin')
        pins[path]=h
    def verify():
        for path,h in pins.items():
            if digest(path)!=h:raise ValueError('Input drift: '+path)
    def pin(path):
        path=str(Path(path).resolve(strict=True));h=digest(path)
        if path in pins and pins[path]!=h:raise ValueError('Input drift: '+path)
        pins[path]=h
    verify();pin(prior/'build.json');pin(__file__);pin(HERE/'native_main.c')
    records=json.loads((prior/'commands.json').read_text())
    compiles=[list(r['argv']) for r in records if r['label'].startswith('compile-')]
    if len(compiles)!=17:raise ValueError('Incomplete object recipe')
    if Path(compiles[1][compiles[1].index('-c')+1]).name!='native_main.c':raise ValueError('Unexpected main')
    compiles[1][compiles[1].index('-c')+1]=str(HERE/'native_main.c')
    compiles[1].insert(1,'-DREGISTER_QUERY='+str(a.query_index))
    out.mkdir(parents=True);commands=[]
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify()
        commands.append(dict(label=label,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        with (out/(label+'.log')).open('w') as f:
            subprocess.run(argv,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
        verify();return (out/(label+'.log')).read_text()
    objects=[]
    for i,cmd in enumerate(compiles):
        obj=out/f'{i}.o';objects.append(str(obj));cmd[cmd.index('-o')+1]=str(obj)
        dep=[v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
        deps=run([*dep,'-M','-MT','object'],'deps-'+str(i))
        for path in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):pin(path)
        run(cmd,'compile-'+str(i))
    link=list(next(r['argv'] for r in records if r['label']=='link'))
    link=[v for v in link if not v.endswith('.o')]
    link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=objects
    elf=out/'register_pv.elf';link[link.index('-o')+1]=str(elf)
    link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
    run(link,'link')
    dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
    for symbol in ('qbs_native_execute_command','akv_quant_strided_execute','quant_register_execute','main'):
        if '<'+symbol+'>:' not in dis:raise ValueError('Missing native path '+symbol)
    if '<qbs_ref_execute>:' in dis or '<dequantize_row_q8_0>:' in dis:raise ValueError('Reference/scalar drift')
    verify();(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='BUILT_NOT_EXECUTED',kind=report['kind'],elf=str(elf),elf_sha256=digest(elf),
        source_pins_sha256=digest(out/'source-pins.json'),whole_call=True,register_pv=True,
        context_pair=True,query_index=a.query_index,visible_tokens=a.query_index+1,
        value_binding='shared_rvv_q8_0',outputs_per_trial=256,commands_per_trial=1,
        rebuilt_objects=17,reused_objects=0,performance_measured=False,
        artifacts={str(path):digest(path) for path in out.iterdir() if path.is_file()})
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print('CONTEXT_PAIR_BUILT_NOT_EXECUTED '+str(elf))


if __name__=='__main__':main()
