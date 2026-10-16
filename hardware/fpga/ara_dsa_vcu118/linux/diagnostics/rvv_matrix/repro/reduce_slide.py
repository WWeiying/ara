"""Reduce measured large-offset slide failures without replacing their fixtures."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from trace_masks import sha, TOOLS


def legacy_source(source):
    signature='typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,unsigned long);'
    call='functions[op](input,index_source,output+1,vl,cap,predicate,scalars[s],start)'
    if source.count(signature)!=1 or source.count(call)!=1:
        raise ValueError('Original nonrestart interface cannot be reconstructed')
    source=source.replace(signature,signature.replace(',unsigned long,unsigned long);',',unsigned long);')).replace(
        call,call.replace(',start)',')'))
    source=source.replace('            if(!(PERMUTE_OP_MASK & (1U << op)))continue;\n','')
    first=source.index('    unsigned long max_start=0;')
    last=source.index('    const uint64_t scalars[]=',first)
    source=source[:first]+source[last:]
    source=source.replace('for(unsigned mode=0;mode<4;++mode)\n        for(unsigned trial=0;trial<(RESTART_PERMUTATIONS ? 4U:1U);++trial){',
                          'for(unsigned mode=0;mode<4;++mode){')
    first=source.index('            if(RESTART_PERMUTATIONS)\n')
    last=source.index('            for(unsigned i=0;i<128;',first)
    source=source[:first]+source[last:]
    first=source.index('            if(RESTART_PERMUTATIONS &&')
    last=source.index('            if(functions[op]',first)
    source=source[:first]+source[last:]
    source=source.replace('            unsigned vl=lengths[l],start=0;','            unsigned vl=lengths[l];')
    source=source.replace('i>=start && i<vl','i<vl')
    source=source.replace('                        if(RESTART_PERMUTATIONS){text(" vstart=");num(start);}\n','')
    return source


def reduce(source, seed, mode, prefix=False, mask_sequence=False):
    point=('            unsigned vl=lengths[l],start=0;' if ',start=0;' in source
           else '            unsigned vl=lengths[l];')
    end='            ++cases;'
    report='    text(errors ? "RVV_PERMUTE_FAIL'
    if any(source.count(x)!=1 for x in (point,end,report)):
        raise ValueError('Original loop structure changed')
    condition=f'seed=={seed} && op==12 && s==2 && l==6 && mode=={mode}'
    if prefix and mask_sequence:
        raise ValueError('Prefix and short sequence are different experiments')
    if mask_sequence:
        condition=f'seed=={seed} && op==12 && s==2 && l==6 && mode<={mode}'
    if prefix:
        return source.replace(end,end+f'\n            if({condition})goto selected_done;').replace(
            report,'selected_done:\n'+report)
    return source.replace(point,f'            if(!({condition}))continue;\n'+point)


def main():
    p=argparse.ArgumentParser()
    for key in ('original','report','out'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cross',required=True)
    p.add_argument('--mask-sequence',action='store_true')
    a=p.parse_args()
    original=json.loads((a.original/'manifest.json').read_text())
    raw=json.loads(a.report.read_text())
    report=raw.get('report',raw)
    a.out.mkdir(exist_ok=False)
    binaries=a.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    manifest=dict(scope='Original large-offset slide fixtures, single calls and original prefix',
        original_manifest_sha256=sha(a.original/'manifest.json'),
        original_report_sha256=sha(a.report),reducer_sha256=sha(Path(__file__)),
        board_reproduction_confirmed=False,cases=[])
    for shape in ('e8_m4','e8_m8','e16_m8'):
        parent,=[c for c in original['cases'] if c['name']=='rvv_permute_'+shape]
        deployed,=[c for c in report['inputs']['cases'] if c['name']==parent['name']]
        result,=[r for r in report['results'] if r['name']==parent['name']]
        if deployed['sha256']!=parent['sha256'] or result['status']!='failed':
            raise ValueError('Missing original numerical failure')
        flags=[a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
            '-Wall','-Wextra','-Werror',f'-DSEW={parent["sew"]}','-DRESTART_PERMUTATIONS=0']
        src=a.original/parent['name']
        rebuilt=a.out/(parent['name']+'.original.elf')
        source=a.out/'original_nonrestart.c'
        source.write_text(legacy_source((TOOLS/'permutation_oracle.c').read_text()))
        subprocess.run(flags+['-I'+str(src),str(source),str(src/'operations.S'),'-o',str(rebuilt)],check=True)
        if sha(rebuilt)!=parent['sha256']:
            raise ValueError('Current source is not byte-identical to original ELF')
        variants=([(seed,mode,False) for seed in range(3) for mode in (2,3)] if a.mask_sequence
                  else [(seed,mode,False) for seed in range(3) for mode in (0,2,3)]+[(0,3,True)])
        for seed,mode,prefix in variants:
            # Every selected single trial must already have a recorded discrepancy.
            marker=f'RVV_PERMUTE_DETAIL op=12 seed={seed} '
            details=[line.strip() for line in result['output'].splitlines()
                     if line.startswith(marker) and f' mask={mode} ' in line]
            if len(details)!=1:
                raise ValueError('Missing unique selected original failure detail')
            label='seq_' if a.mask_sequence else ''
            name=f'rvv_{"prefix" if prefix else "small"}_slide_{label}{shape}_s{seed}_m{mode}'
            d=a.out/name
            d.mkdir()
            for f in ('operations.S','operations.h'):
                shutil.copy2(src/f,d/f)
            (d/'scenario.c').write_text(reduce(source.read_text(),seed,mode,prefix,a.mask_sequence))
            binary=binaries/name
            subprocess.run(flags+['-I'+str(d),str(d/'scenario.c'),str(d/'operations.S'),'-o',str(binary)],check=True)
            with (d/'scenario.dis').open('w') as stream:
                subprocess.run([a.cross+'objdump','-d',str(binary)],stdout=stream,check=True)
            case=dict(parent,name=name,sha256=sha(binary),original_name=parent['name'],
                original_elf_sha256=parent['sha256'],original_rebuild_byte_identical=True,
                original_failure_detail=details[0],scenario_role='original_prefix' if prefix else 'single_original_trial',
                selected_trial=dict(seed=seed,op=12,scalar='cap-1',vl='cap',mask=mode),
                timeout_seconds=180 if prefix else 30,
                scenario_sources={f:sha(d/f) for f in ('scenario.c','operations.S','operations.h')})
            case['configurations']=12*8*7*4+2*7*4+6*4+mode+1 if prefix else 1
            if a.mask_sequence:
                case.update(configurations=mode+1,scenario_role='short_original_mask_sequence',
                            preceding_masks=list(range(mode)))
            manifest['cases'].append(case)
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('\n'.join(entries)+'\n').encode(),stdout=stream,check=True)
    print('ORIGINAL_REBUILD_IDENTICAL; SCENARIOS',len(manifest['cases']))


if __name__=='__main__':
    main()
