#!/usr/bin/env python3
"""Bind complete mapped smoke outputs to the checked RTL specimen."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(gate,rtl,numeric):
    if gate['state']!='GATE_SMOKE_PASS' or not gate['full_gate_task_pass']:
        raise ValueError('A completed mapped smoke is required')
    if rtl['state']!='PASS' or numeric['state']!='PASS' or not rtl['independent_protocol_checked']:
        raise ValueError('Independently checked RTL specimen required')
    if rtl['elf_sha256']!=gate['elf_sha256']:
        raise ValueError('RTL/gate ELF identity differs')
    a,b=gate['numerical']['benchmark'],numeric['benchmark']
    keys=['case','result','k','rows','inputs','outputs','checksum','mismatches',
          'max_abs_bits','max_rel_bits']
    if 'qbs_status' in a or 'qbs_status' in b:
        keys.append('qbs_status')
    for key in keys:
        if a.get(key)!=b.get(key) or key not in a:
            raise ValueError('RTL/gate output disagreement: '+key)
    if a['result']!='PASS' or a['mismatches']!='0':
        raise ValueError('Target numerical checks failed')
    return dict(state='PASS',same_elf=True,checksum=a['checksum'],
                compared_fields=keys,whole_gate_task_pass=True,
                scope='Mapped/RTL deterministic output signature plus target all-output numerical checks; not timing signoff')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--smoke',type=Path,required=True)
    p.add_argument('--rtl-run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise ValueError('New audit output required')
    numeric=a.rtl_run/'numerical.json'
    original=a.rtl_run/'result.json'
    gate=json.loads(a.smoke.read_text())
    result=compare(gate,json.loads(original.read_text()),json.loads(numeric.read_text()))
    result.update(inputs={str(path.resolve()):sha(path) for path in (a.smoke,original,numeric)},
                  gate_simv_sha256=gate['simv_sha256'],rtl_simulator_identity='recorded in RTL protocol proof')
    with a.output.open('x') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
