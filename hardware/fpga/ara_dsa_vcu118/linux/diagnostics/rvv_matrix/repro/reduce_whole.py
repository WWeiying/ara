"""Preserve exact whole-move input bytes for the measured first failure."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
import whole


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reduce(source, prefix=False):
    loop='    for(unsigned seed=0;seed<3;++seed)for(unsigned op=0;op<20;++op)for(unsigned mode=0;mode<5;++mode){'
    assert source.count(loop)==1
    if prefix:
        source=source.replace('            ++cases;',
            '            ++cases;\n            if(seed==0 && op==16 && mode==1 && st==1)goto selected_done;')
        source=source.replace('    text(errors ? "RVV_WHOLE_FAIL',
                              'selected_done:\n    text(errors ? "RVV_WHOLE_FAIL')
    else:
        source=source.replace(loop,'    { unsigned seed=0,op=16,mode=1;')
        source=source.replace('for(unsigned st=0;st<5;++st)', 'for(unsigned st=1;st<2;++st)')
    return source


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--original-build',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--cross',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    original=json.loads((a.original_build/'manifest.json').read_text())
    for name,digest in original['source_sha256'].items():
        assert sha(TOOLS/name)==digest
    parent,=original['cases']
    raw=json.loads(a.report.read_text())
    report=raw.get('report',raw)
    case,=[c for c in report['inputs']['cases'] if c['name']==parent['name']]
    assert case['sha256']==parent['sha256']
    result,=[r for r in report['results'] if r['name']==parent['name']]
    detail='RVV_WHOLE_BYTE op=16 mode=1 vstart=1 byte=33 expected=91 actual=40'
    assert result['status']=='failed' and result['exit_code']==1 and detail in result['output'].splitlines()
    asm=a.original_build/'whole.S'
    assert asm.read_text()==whole.assembly()
    a.out.mkdir(exist_ok=False)
    binaries=a.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    manifest=dict(scope='Exact whole-register first-failure stimulus and original prefix',cases=[],
        original_report_sha256=sha(a.report), original_manifest_sha256=sha(a.original_build/'manifest.json'),
        board_reproduction_confirmed=False, source_sha256={p.name:sha(p) for p in
            (TOOLS/'whole_oracle.c',TOOLS/'whole.py',Path(__file__))})
    for prefix in (False,True):
        name='rvv_'+('prefix' if prefix else 'small')+'_whole_restart_first'
        directory=a.out/name
        directory.mkdir()
        c=directory/'scenario.c'
        c.write_text(reduce((TOOLS/'whole_oracle.c').read_text(),prefix))
        for f in ('whole.S','operations.h'):
            shutil.copy2(a.original_build/f,directory/f)
        binary=binaries/name
        subprocess.run([a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none',
            '-Wall','-Wextra','-Werror','-DDETAIL_BYTES=1','-I'+str(directory),str(c),
            str(directory/'whole.S'),'-o',str(binary)],check=True)
        with (directory/'scenario.dis').open('w') as output:
            subprocess.run([a.cross+'objdump','-d',str(binary)],stdout=output,check=True)
        manifest['cases'].append(dict(name=name,sha256=sha(binary),pass_marker='RVV_WHOLE_PASS',
            timeout_seconds=30,original_name=parent['name'],original_elf_sha256=parent['sha256'],
            original_failure_detail=detail,scenario_role='original_prefix' if prefix else 'single_stimulus',
            measured_stimulus=dict(seed=0,op=16,mode=1,vstart=1),
            scenario_sources={f:sha(directory/f) for f in ('scenario.c','whole.S','operations.h')}))
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (a.out/'overlay.cpio').open('wb') as output:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('opt\nopt/ara-tests\n'+''.join('opt/ara-tests/'+c['name']+'\n' for c in manifest['cases'])).encode(),
            stdout=output,check=True)
    print(a.out)


if __name__=='__main__':
    main()
