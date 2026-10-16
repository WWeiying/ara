"""Extract measured missing-NV reduction stimuli using original SoftFloat fixtures."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import shutil
import subprocess
from trace_masks import sha, TOOLS


SELECTOR='                if(!(scenario==3 && l==4 && mode==3 && rm==0 && op==0 && sticky==0))continue;\n'


def reduce(source):
    point='                for(unsigned i=0;i<144;++i)output[i]=0x5b;'
    if source.count(point)!=1:raise ValueError('Original reduction loop changed')
    # Selection stays after index++ so the original fixture indexing is unchanged.
    return source.replace(point,SELECTOR+point)


def main():
    p=argparse.ArgumentParser()
    for key in ('full','half','report','out'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cross',required=True)
    a=p.parse_args()
    raw=json.loads(a.report.read_text());report=raw.get('report',raw)
    a.out.mkdir(exist_ok=False)
    binaries=a.out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    manifest=dict(scope='Single missing-NV ordered reduction per original failing shape',cases=[],
        board_reproduction_confirmed=False,original_report_sha256=sha(a.report),reducer_sha256=sha(Path(__file__)))
    for result in report['results']:
        if not result['name'].startswith('rvv_fp_redspecial_') or result['status']!='failed':continue
        line=next(x for x in result['output'].splitlines() if x.startswith('RVV_FP_REDSPECIAL_DETAIL '))
        fields={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
        if any(fields.get(k)!=v for k,v in dict(scenario=3,op=0,mask=3,frm=0,flags=0,expected_flags=16).items()):
            raise ValueError('Unexpected measured first-failure tuple')
        root=a.half if '_e16_' in result['name'] else a.full
        original=json.loads((root/'manifest.json').read_text())
        parent,=[c for c in original['cases'] if c['name']==result['name']]
        deployed,=[c for c in report['inputs']['cases'] if c['name']==parent['name']]
        if parent['sha256']!=deployed['sha256']:raise ValueError('Wrong original ELF')
        sew,lmul=parent['sew'],parent['lmul']
        factor=Fraction(1,int(lmul[2:])) if lmul.startswith('mf') else Fraction(int(lmul[1:]))
        caps=[int(v*factor/sew) for v in (512,1024)]
        if fields['vl']!=caps[1]//2:raise ValueError('Wrong selected vector length')
        name=parent['name'].replace('rvv_fp_','rvv_small_fp_',1)
        d=a.out/name;d.mkdir()
        for f in ('operations.S','operations.h','fixtures.h','fixtures.json'):
            shutil.copy2(root/f'e{sew}'/lmul/f,d/f)
        shutil.copy2(root/f'e{sew}'/'input_bits.h',d/'input_bits.h')
        source=TOOLS/'fp_reduction_oracle.c'
        helper=TOOLS/'fp_reduction_inputs.h'
        for f in (source,helper):
            if sha(f)!=original['source_sha256'][f.name]:raise ValueError('Original source changed')
        shutil.copy2(helper,d/helper.name)
        flags=[a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
            '-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DCAP512={caps[0]}',f'-DCAP1024={caps[1]}','-I'+str(d)]
        rebuilt=d/'original_rebuilt.elf'
        subprocess.run(flags+[str(source),str(d/'operations.S'),'-o',str(rebuilt)],check=True)
        if sha(rebuilt)!=parent['sha256']:raise ValueError('Original rebuild differs')
        (d/'scenario.c').write_text(reduce(source.read_text()))
        binary=binaries/name
        subprocess.run(flags+[str(d/'scenario.c'),str(d/'operations.S'),'-o',str(binary)],check=True)
        with (d/'scenario.dis').open('w') as stream:
            subprocess.run([a.cross+'objdump','-d',str(binary)],stdout=stream,check=True)
        manifest['cases'].append(dict(parent,name=name,sha256=sha(binary),configurations=1,timeout_seconds=30,
            original_name=parent['name'],original_elf_sha256=parent['sha256'],original_rebuild_byte_identical=True,
            scenario_role='single_original_trial',original_failure_detail=line,
            scenario_sources={f:sha(d/f) for f in ('scenario.c','operations.S','operations.h','fixtures.h','input_bits.h','fp_reduction_inputs.h')}))
    if not manifest['cases']:raise ValueError('No failed cases selected')
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('\n'.join(entries)+'\n').encode(),stdout=stream,check=True)
    print('ORIGINAL_REBUILD_IDENTICAL; SCENARIOS',len(manifest['cases']))


if __name__=='__main__':main()
