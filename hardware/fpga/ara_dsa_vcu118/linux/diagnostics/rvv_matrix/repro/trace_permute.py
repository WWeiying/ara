"""Trace the original zero-offset slidedown partition before reducing it."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from trace_masks import sha, TOOLS


def instrument(source):
    point='            if(functions[op](input,index_source,output+1,vl,cap,predicate,scalars[s],start))++errors;'
    if source.count(point)!=1:
        raise ValueError('Original permutation call changed')
    before='''            text("RVV_PERMUTE_BEGIN seed=");num(seed);text(" op=");num(op);
            text(" scalar=");num(scalars[s]);text(" vl=");num(vl);
            text(" mask=");num(mode);text(" vstart=");num(start);text(" cap=");num(cap);text("\\n");
            syscall3(29,1,0x5409,1);
'''
    after='''
            text("RVV_PERMUTE_RETURN seed=");num(seed);text(" op=");num(op);
            text(" scalar=");num(scalars[s]);text(" vl=");num(vl);
            text(" mask=");num(mode);text(" vstart=");num(start);text("\\n");'''
    return source.replace(point,before+point+after)


def isolate(source):
    point='            for(unsigned i=0;i<128;++i)predicate[i]=0;'
    if source.count(point)!=1:raise ValueError('Original trial selector changed')
    return source.replace(point,
        '            if(!(seed==0 && op==16 && s==0 && l==4 && mode==0 && trial==1))continue;\n'+point)


def main():
    p=argparse.ArgumentParser()
    for key in ('original','report','out'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cross',required=True)
    p.add_argument('--single-trial',action='store_true')
    p.add_argument('--trace-report',type=Path)
    a=p.parse_args()
    m=json.loads((a.original/'manifest.json').read_text())
    raw=json.loads(a.report.read_text())
    report=raw.get('report',raw)
    parent,=[c for c in m['cases'] if c['name']=='rvv_permute_restart_e16_m1_ops16']
    deployed,=[c for c in report['inputs']['cases'] if c['name']==parent['name']]
    result,=[r for r in report['results'] if r['name']==parent['name']]
    if parent['sha256']!=deployed['sha256'] or result['status']!='stalled':
        raise ValueError('Missing original stall evidence')
    if a.single_trial:
        if a.trace_report is None:raise ValueError('Single trial requires measured trace')
        trace=json.loads(a.trace_report.read_text());trace=trace.get('report',trace)
        measured,=[r for r in trace['results'] if r['name']=='rvv_trace_permute_restart_e16_m1_ops16']
        if measured['status']!='stalled' or measured['output'].strip().splitlines()[-1]!=('RVV_PERMUTE_BEGIN seed=0 op=16 scalar=0 vl=32 mask=0 vstart=16 cap=64'):
            raise ValueError('Wrong measured stalled trial')
    a.out.mkdir(exist_ok=False)
    name='rvv_trace_permute_'+('single_' if a.single_trial else '')+'restart_e16_m1_ops16'
    d=a.out/name
    d.mkdir()
    for f in ('operations.S','operations.h'):
        shutil.copy2(a.original/parent['name']/f,d/f)
    flags=[a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
        '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
        '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
        '-Wall','-Wextra','-Werror','-DSEW=16','-DRESTART_PERMUTATIONS=1',
        '-DPERMUTE_OP_MASK=65536','-I'+str(d)]
    source=TOOLS/'permutation_oracle.c'
    rebuilt=d/'original_rebuilt.elf'
    subprocess.run(flags+[str(source),str(d/'operations.S'),'-o',str(rebuilt)],check=True)
    if sha(rebuilt)!=parent['sha256']:
        raise ValueError('Original ELF could not be rebuilt byte-identically')
    code=isolate(source.read_text()) if a.single_trial else source.read_text()
    (d/'scenario.c').write_text(instrument(code))
    binaries=a.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    binary=binaries/name
    subprocess.run(flags+[str(d/'scenario.c'),str(d/'operations.S'),'-o',str(binary)],check=True)
    with (d/'scenario.dis').open('w') as stream:
        subprocess.run([a.cross+'objdump','-d',str(binary)],stdout=stream,check=True)
    manifest=dict(scope='Original zero-offset slidedown trial order with drained boundaries; timing may change',
        original_manifest_sha256=sha(a.original/'manifest.json'),original_report_sha256=sha(a.report),
        board_reproduction_confirmed=False,reducer_sha256=sha(Path(__file__)),
        cases=[dict(parent,name=name,sha256=sha(binary),original_name=parent['name'],
                    original_elf_sha256=parent['sha256'],original_rebuild_byte_identical=True,
                    scenario_role='original_sequence_trace',
                    scenario_sources={f:sha(d/f) for f in ('scenario.c','operations.S','operations.h')})])
    if a.single_trial:
        manifest['scope']='Single measured zero-offset slidedown restart trial; board equivalence unconfirmed'
        manifest['trace_report_sha256']=sha(a.trace_report)
        manifest['cases'][0].update(configurations=1,scenario_role='single_original_trial',
            selected_trial=dict(seed=0,op=16,scalar=0,vl='cap/2',vstart='vl/2',mask=0))
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('opt\nopt/ara-tests\nopt/ara-tests/'+name+'\n').encode(),stdout=stream,check=True)
    print('ORIGINAL_REBUILD_IDENTICAL; TRACE_READY')


if __name__=='__main__':
    main()
