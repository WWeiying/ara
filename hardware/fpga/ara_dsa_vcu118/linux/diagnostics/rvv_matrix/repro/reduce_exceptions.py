"""One original protected-page child trial per measured failing scenario."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from trace_masks import sha, TOOLS


def reduce(source, scenario):
    old = 'for(unsigned round=0;round<16;++round)for(unsigned scenario=0;scenario<6;++scenario)'
    if source.count(old) != 1 or scenario not in (0, 1, 2, 3, 5):
        raise ValueError('Unsupported source or scenario')
    return source.replace(old, 'for(unsigned round=0;round<1;++round)'
                          f'for(unsigned scenario={scenario};scenario<{scenario+1};++scenario)')


def main():
    p = argparse.ArgumentParser()
    for arg in ('original', 'report', 'out'):
        p.add_argument('--'+arg, type=Path, required=True)
    p.add_argument('--cross', required=True)
    a = p.parse_args()
    original = json.loads((a.original/'manifest.json').read_text())
    report = json.loads(a.report.read_text())
    inputs = {c['name']:c for c in report['inputs']['cases']}
    results = {r['name']:r for r in report['results']}
    source = TOOLS/'exception_oracle.c'
    if sha(source) != original['source_sha256']['exception_oracle.c']:
        raise ValueError('Original oracle changed')
    a.out.mkdir(exist_ok=False)
    binaries = a.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    manifest = dict(scope='Original protected-page scenarios, one child each; board equivalence pending',
                    cases=[], original_manifest_sha256=sha(a.original/'manifest.json'),
                    original_report_sha256=sha(a.report), reducer_sha256=sha(Path(__file__)),
                    board_reproduction_confirmed=False)
    for parent in original['cases']:
        name = parent['name']
        if inputs[name]['sha256'] != parent['sha256'] or results[name]['exit_code'] != 1:
            raise ValueError('Original failure evidence changed')
        asm = a.original/(name+'.S')
        flags = [a.cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
                 '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
                 '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
                 '-Wall','-Wextra','-Werror',f'-DSEW={parent["sew"]}','-DDETAIL_SCENARIOS=1']
        rebuilt = a.out/(name+'.original.elf')
        subprocess.run(flags+[str(source),str(asm),'-o',str(rebuilt)],check=True)
        if sha(rebuilt) != parent['sha256']:
            raise ValueError('Original ELF rebuild differs')
        for scenario in (0,1,2,3,5):
            detail = f'RVV_EXCEPTION_SCENARIO id={scenario} unexpected_signals=16 nonzero_exits=0 wait_failures=0'
            if results[name]['output'].splitlines().count(detail) != 1:
                raise ValueError('Scenario not confirmed in original report')
            small = f'rvv_small_exceptions_e{parent["sew"]}_scenario{scenario}'
            d = a.out/small
            d.mkdir()
            shutil.copy2(asm,d/'scenario.S')
            (d/'scenario.c').write_text(reduce(source.read_text(),scenario))
            binary = binaries/small
            subprocess.run(flags+[str(d/'scenario.c'),str(d/'scenario.S'),'-o',str(binary)],check=True)
            manifest['cases'].append(dict(parent,name=small,sha256=sha(binary),timeout_seconds=30,
                original_name=name,original_elf_sha256=parent['sha256'],original_rebuild_byte_identical=True,
                original_failure_detail=detail,scenario_role='single_stimulus',
                measured_stimulus=dict(scenario=scenario,round=0,vl=8,sew=parent['sew']),
                scenario_sources={f:sha(d/f) for f in ('scenario.c','scenario.S')}))
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],cwd=a.out/'overlay',
            input=('opt\nopt/ara-tests\n'+''.join('opt/ara-tests/'+c['name']+'\n' for c in manifest['cases'])).encode(),
            stdout=stream,check=True)
    print('ORIGINAL_ELFS_BYTE_IDENTICAL; CANDIDATES',len(manifest['cases']))


if __name__ == '__main__':
    main()
