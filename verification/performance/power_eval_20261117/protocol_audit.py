#!/usr/bin/env python3
"""Independent completion audit; preserve original worker failures, no RTL rerun."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
REV = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def require(ok, text):
    if not ok:
        raise ValueError(text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True)
    a = p.parse_args()
    work,output,image = a.run.resolve(),a.output.resolve(),a.image.resolve()
    require(output.parent == OUT and not output.exists(),'Fresh audit output required')
    original = json.loads((work/'result.json').read_text())
    require(original['state'] == 'FAIL' and original.get('error') == "ValueError('PROTOCOL exit 1')",
            'Only explicit original protocol-tool failure may be audited here')
    require('ModuleNotFoundError: No module named' in (work/'PROTOCOL.log').read_text(),
            'Failure is not the missing-checker-package condition')
    numeric = json.loads((work/'numerical.json').read_text())
    require(numeric['state'] == 'PASS','Numerical precheck has not passed')
    campaign = work.parent.parent
    plan = json.loads((campaign/'plan.json').read_text())
    cases = [c for c in plan['cases'] if c['id'] == work.name]
    require(len(cases) == 1,'Case identity')
    case = cases[0]
    require(str(image) == plan['image'],'Image identity')
    image_build = json.loads((image/'build.json').read_text())
    require(image_build['state'] == 'DC_MATCHED_RTL_BUILT_NOT_EXECUTED','Wrong image')
    pins = json.loads((campaign/'source-pins.json').read_text())
    pins.update(json.loads((image/'source-pins.json').read_text()))
    pins.update(image_build['image_pins'])
    pins.update({str(path):sha(path) for path in (
        work/'result.json',work/'numerical.json',work/'PROTOCOL.log',
        work/'run.vcs.log',work/'vector.csv',work/'commit.csv',Path(__file__).resolve())})
    for name,digest in pins.items():
        require(sha(name)==digest,'Pinned source/evidence drift: '+name)
    output.mkdir()
    archive = subprocess.check_output(['git','-C',str(ROOT),'archive',REV,'verification/ara_verify'])
    (output/'checker.tar').write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            require((member.isfile() or member.isdir()) and not Path(member.name).is_absolute() and
                    '..' not in Path(member.name).parts,'Unsafe checker archive')
        tar.extractall(output/'inputs')
    shutil.copyfile(__file__,output/'audit.py')
    for path in (output/'inputs').rglob('*'):
        if path.is_file():
            pins[str(path)]=sha(path)
    argv=['/usr/bin/python3','-B','-m','ara_verify.uvm_dut','--require-events',
          '--require-backend','--require-axi','--require-axi-write',
          '--vector-trace',str(work/'vector.csv'),'--log',str(work/'run.vcs.log'),
          '--simv',str(image/'sim/simv'),'--elf',case['elf'],'--output',str(output/'protocol.json')]
    env=dict(os.environ,PYTHONPATH=str(output/'inputs/verification'),PYTHONDONTWRITEBYTECODE='1')
    with (output/'protocol.log').open('x') as stream:
        proc=subprocess.run(argv,cwd=output,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1200)
    proof=json.loads((output/'protocol.json').read_text()) if (output/'protocol.json').exists() else {}
    checks = dict(returncode_zero=proc.returncode==0,protocol_pass=proof.get('status')=='PASS',
        no_issues=proof.get('issues')==[],elf_identity=proof.get('elf_sha256')==case['elf_sha256'],
        image_identity=proof.get('simv_sha256')==image_build['image_pins'][str(image/'sim/simv')],
        log_identity=proof.get('log_sha256')==sha(work/'run.vcs.log'),
        trace_identity=proof.get('vector_trace_sha256')==sha(work/'vector.csv'),
        drained=all(proof.get('contract_counts',{}).get(k)==0 for k in
                    ('exceptions','protocol_errors','outstanding')))
    for name,digest in pins.items():
        require(sha(name)==digest,'Post-audit drift: '+name)
    (output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='PASS' if all(checks.values()) else 'FAIL',checks=checks,
        original_worker_state=original['state'],original_worker_reclassified=False,
        numerical_evidence=str(work/'numerical.json'),protocol_evidence=str(output/'protocol.json'),
        original_failure='Missing ara_verify Python package in frozen image support tree',
        checker_commit=REV,rtl_rerun=False,power_measured=False)
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return int(result['state']!='PASS')


if __name__=='__main__':
    raise SystemExit(main())
