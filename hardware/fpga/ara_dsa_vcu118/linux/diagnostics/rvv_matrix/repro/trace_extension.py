"""Locate the exact failing original extension trial without changing its order."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from trace_masks import sha, TOOLS


def instrument(source):
    point='            if(functions[op](input,output+1,mask,vl,cap))++errors;'
    if source.count(point)!=1:
        raise ValueError('Original target call changed')
    before='''            text("RVV_EXTENSION_BEGIN seed=");num(seed);text(" op=");num(op);
            text(" vl=");num(vl);text(" mask=");num(mode);text(" cap=");num(cap);text("\\n");
            syscall3(29,1,0x5409,1);
'''
    after='''
            text("RVV_EXTENSION_RETURN seed=");num(seed);text(" op=");num(op);
            text(" vl=");num(vl);text(" mask=");num(mode);text("\\n");'''
    return source.replace(point,before+point+after)


def isolate(source):
    """Keep the first stalled configuration observed in the original trace."""
    point='            unsigned vl=lengths[l];'
    if source.count(point)!=1:
        raise ValueError('Original trial selector changed')
    return source.replace(point,
        '            if(seed!=0 || op!=2 || l!=5 || mode!=0)continue;\n'+point)


def main():
    p=argparse.ArgumentParser()
    for arg in ('original','report','out'):
        p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--cross',required=True)
    p.add_argument('--single-trial',action='store_true')
    p.add_argument('--trace-report',type=Path)
    a=p.parse_args()
    m=json.loads((a.original/'manifest.json').read_text())
    report=json.loads(a.report.read_text())
    name='rvv_extension_e16_m2_vf2'
    parent,=[c for c in m['cases'] if c['name']==name]
    deployed,=[c for c in report['inputs']['cases'] if c['name']==name]
    result,=[r for r in report['results'] if r['name']==name]
    if parent['sha256']!=deployed['sha256'] or result['status']!='stalled':
        raise ValueError('Missing original stall evidence')
    if a.single_trial:
        if a.trace_report is None:
            raise ValueError('Single trial requires board trace evidence')
        trace=json.loads(a.trace_report.read_text())
        trace=trace.get('report',trace)
        observed,=[r for r in trace['results']
                   if r['name']=='rvv_trace_extension_e16_m2_vf2']
        last=observed['output'].strip().splitlines()[-1]
        if observed['status']!='stalled' or last!=('RVV_EXTENSION_BEGIN seed=0 op=2 vl=127 mask=0 cap=128'):
            raise ValueError('Trace does not establish the selected stalled trial')
    a.out.mkdir(exist_ok=False)
    small=('rvv_trace_extension_single_e16_m2_vf2' if a.single_trial
           else 'rvv_trace_extension_e16_m2_vf2')
    d=a.out/small
    d.mkdir()
    shutil.copy2(a.original/(name+'.S'),d/'scenario.S')
    shutil.copy2(a.original/'operations.h',d/'operations.h')
    flags=[a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
           '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
           '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
           '-Wall','-Wextra','-Werror','-DSEW=16','-DFACTOR=2','-DDEST_REGS=2',
           '-DSOURCE_REGS=1','-DOP_COUNT=4','-I'+str(d)]
    source=TOOLS/'extension_oracle.c'
    rebuilt=d/'original_rebuilt.elf'
    subprocess.run(flags+[str(source),str(d/'scenario.S'),'-o',str(rebuilt)],check=True)
    if sha(rebuilt)!=parent['sha256']:
        raise ValueError('Current source does not recreate original ELF')
    code=source.read_text()
    if a.single_trial:
        code=isolate(code)
    (d/'scenario.c').write_text(instrument(code))
    binaries=a.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    binary=binaries/small
    subprocess.run(flags+[str(d/'scenario.c'),str(d/'scenario.S'),'-o',str(binary)],check=True)
    with (d/'scenario.dis').open('w') as stream:
        subprocess.run([a.cross+'objdump','-d',str(binary)],stdout=stream,check=True)
    manifest=dict(scope='Original extension sequence with before/after markers; instrumentation may affect timing',
        board_reproduction_confirmed=False,original_report_sha256=sha(a.report),
        original_manifest_sha256=sha(a.original/'manifest.json'),reducer_sha256=sha(Path(__file__)),
        cases=[dict(parent,name=small,sha256=sha(binary),original_name=name,
                    original_elf_sha256=parent['sha256'],original_rebuild_byte_identical=True,
                    scenario_role='original_sequence_trace',
                    scenario_sources={f:sha(d/f) for f in ('scenario.c','scenario.S','operations.h')})])
    if a.single_trial:
        manifest['scope']='Single original extension trial; board equivalence not yet established'
        manifest['trace_report_sha256']=sha(a.trace_report)
        manifest['cases'][0].update(configurations=1,scenario_role='single_original_trial',
            selected_trial=dict(seed=0,op=2,length='cap-1',mask=0))
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('opt\nopt/ara-tests\nopt/ara-tests/'+small+'\n').encode(),stdout=stream,check=True)
    print('ORIGINAL_REBUILD_IDENTICAL; TRACE_READY')


if __name__=='__main__':
    main()
