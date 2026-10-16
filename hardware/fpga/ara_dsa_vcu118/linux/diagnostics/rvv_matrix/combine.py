"""Combine only reference-validated releases without changing their ELFs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile

def numerical_pass(result, case):
    lines = [line for line in result.get('output', '').splitlines()
             if line.startswith(case['pass_marker'])]
    if not result.get('passed') or result.get('exit_code') != 0 or len(lines) != 1:
        return False
    match = re.search(r'\bcases=(\d+)\b', lines[0])
    if match is None or int(match[1]) == 0:
        return False
    expected = case.get('configurations')
    return expected is None or int(match[1]) == expected

def combine(out,roots):
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'binaries';binaries.mkdir()
    manifest=dict(scope='Reference-validated RVV coverage additions; not a board pass',
                  cases=[],sources=[],reference_passed=True,reference_vlens=[512,1024])
    names=set()
    for root in roots:
        source=root/'transfer_manifest.json'
        data=json.loads(source.read_text())
        if not data.get('reference_passed') or set(data['reference_vlens'])!={512,1024}:
            raise ValueError('Both reference VLENs must pass: '+str(root))
        original=json.loads((root/'manifest.json').read_text())
        if data['cases'] != original['cases']:
            raise ValueError('Transfer case metadata differs from reference manifest')
        for vlen in (512,1024):
            report=json.loads((root/f'reference_{vlen}.json').read_text())
            if not report.get('passed') or len(report['results'])!=len(data['cases']):
                raise ValueError('Incomplete reference report')
            if report['manifest_sha256'] != hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest():
                raise ValueError('Reference manifest changed')
            if report.get('cpu_features',[]) != data.get('reference_cpu_features',[]):
                raise ValueError('Reference CPU capabilities differ')
            if [x['name'] for x in report['results']] != [x['name'] for x in data['cases']]:
                raise ValueError('Reference case identities differ')
            if not all(numerical_pass(x,case)
                       for x,case in zip(report['results'],data['cases'])):
                raise ValueError('Reference case lacks numerical pass')
        manifest['sources'].append(dict(path=str(root),
            manifest_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            reference_cpu_features=data.get('reference_cpu_features',[]),
            coverage={k:data.get(k) for k in ('scope','operations','restart_tested','agnostic_policy','rounding_modes')}))
        for case in data['cases']:
            if case['name'] in names:raise ValueError('Duplicate case name')
            names.add(case['name'])
            binary=root/'overlay/opt/ara-tests'/case['name']
            if hashlib.sha256(binary.read_bytes()).hexdigest()!=case['sha256']:
                raise ValueError('Reference ELF changed')
            if not binary.stat().st_mode & 0o111:
                raise ValueError('Reference ELF is not executable')
            shutil.copy2(binary,binaries/case['name'])
            manifest['cases'].append(case)
    archive=out/'width_tests.tgz'
    with tarfile.open(archive,'w:gz') as tar:
        for case in manifest['cases']:tar.add(binaries/case['name'],arcname=case['name'])
    manifest.update(archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                    archive_bytes=archive.stat().st_size)
    (out/'transfer_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('COMBINED',len(names),'ELFs',manifest['archive_bytes'],'bytes')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('roots',nargs='+',type=Path);a=p.parse_args();combine(a.out,a.roots)
