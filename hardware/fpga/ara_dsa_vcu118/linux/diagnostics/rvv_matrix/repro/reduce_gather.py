"""Extract each measured gather-restart failure with original PRNG and assembly."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from trace_masks import sha, TOOLS


def reduce(source, op):
    point='            for(unsigned i=0;i<128;++i)predicate[i]=0;'
    if source.count(point)!=1 or not 0<=op<=20:
        raise ValueError('Original gather loop changed')
    selector=f'            if(!(seed==0 && op=={op} && s==0 && l==2 && mode==0 && trial==0))continue;\n'
    return source.replace(point,selector+point)


def main():
    p=argparse.ArgumentParser()
    for key in ('partitions','full','report','out'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cross',required=True)
    a=p.parse_args()
    raw=json.loads(a.report.read_text())
    report=raw.get('report',raw)
    manifests={root:json.loads((root/'manifest.json').read_text()) for root in (a.partitions,a.full)}
    a.out.mkdir(exist_ok=False)
    binaries=a.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    manifest=dict(scope='One exact first measured gather restart stimulus per failed original ELF',
        original_report_sha256=sha(a.report),board_reproduction_confirmed=False,
        reducer_sha256=sha(Path(__file__)),cases=[])
    for result in report['results']:
        name=result['name']
        if not name.startswith('rvv_permute_restart_') or result['status']!='failed':continue
        line=next(x for x in result['output'].splitlines() if x.startswith('RVV_PERMUTE_DETAIL '))
        fields={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
        require={'seed':0,'scalar':0,'vl':2,'mask':0,'vstart':1}
        if any(fields.get(k)!=v for k,v in require.items()) or fields['op'] not in (0,1,2,3,20):
            raise ValueError('Unrecognized first-failure stimulus: '+name)
        root=a.partitions if '_ops' in name else a.full
        parent,=[c for c in manifests[root]['cases'] if c['name']==name]
        deployed,=[c for c in report['inputs']['cases'] if c['name']==name]
        if parent['sha256']!=deployed['sha256']:raise ValueError('Deployed identity differs')
        small=name.replace('rvv_permute_','rvv_small_gather_',1)
        d=a.out/small
        d.mkdir()
        for f in ('operations.S','operations.h'):shutil.copy2(root/name/f,d/f)
        flags=[a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
            '-Wall','-Wextra','-Werror',f'-DSEW={parent["sew"]}','-DRESTART_PERMUTATIONS=1','-I'+str(d)]
        if '_ops' in name:flags+=[f'-DPERMUTE_OP_MASK={sum(1<<i for i in parent["operation_ids"])}']
        code=(TOOLS/'permutation_oracle.c').read_text()
        if '_ops' not in name:
            code=code.replace('            if(!(PERMUTE_OP_MASK & (1U << op)))continue;\n','')
        source=d/'original.c'
        source.write_text(code)
        rebuilt=d/'original_rebuilt.elf'
        subprocess.run(flags+[str(source),str(d/'operations.S'),'-o',str(rebuilt)],check=True)
        if sha(rebuilt)!=parent['sha256']:raise ValueError('Original ELF reconstruction differs: '+name)
        (d/'scenario.c').write_text(reduce(source.read_text(),fields['op']))
        binary=binaries/small
        subprocess.run(flags+[str(d/'scenario.c'),str(d/'operations.S'),'-o',str(binary)],check=True)
        with (d/'scenario.dis').open('w') as stream:
            subprocess.run([a.cross+'objdump','-d',str(binary)],stdout=stream,check=True)
        manifest['cases'].append(dict(parent,name=small,sha256=sha(binary),original_name=name,
            original_elf_sha256=parent['sha256'],original_rebuild_byte_identical=True,
            original_failure_detail=line,selected_trial=fields,configurations=1,timeout_seconds=30,
            scenario_role='single_original_trial',
            scenario_sources={f:sha(d/f) for f in ('scenario.c','operations.S','operations.h')}))
    if not manifest['cases']:raise ValueError('No measured failures selected')
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('\n'.join(entries)+'\n').encode(),stdout=stream,check=True)
    print('ORIGINAL_REBUILD_IDENTICAL; SCENARIOS',len(manifest['cases']))


if __name__=='__main__':main()
