#!/usr/bin/env python3
"""Recheck current candidate input identities and raw functional-test evidence."""
import argparse
import json
from pathlib import Path

from audit import digest, require, verify_pins

EXPECTED = {
    'leaf': ('LEAF_FUNCTIONAL_PASS_NOT_ONLINE_OR_RTL_ACCEPTED', 'OUTPUT_TILE_', {
        1024:'OUTPUT_TILE_PASS cases=1472 real=32 rejected=15 unaligned=3 exact=1 flags=1 scalar_oracle=1',
        256:'OUTPUT_TILE_UNSUPPORTED_PASS no_effects=1'}),
    'online': ('SCHEDULE_FUNCTIONAL_PASS_NOT_QK_OR_RTL_ACCEPTED', 'OUTPUT_ONLINE_', {
        1024:'OUTPUT_ONLINE_PASS cases=752 real=32 rejected=17 callback_failures=6 exact=1 flags=1',
        256:'OUTPUT_ONLINE_UNSUPPORTED_PASS no_effects=1'}),
    'runtime': ('RUNTIME_REFERENCE_PASS_NOT_NATIVE_OR_MODEL_ACCEPTED', 'REGISTER_RUNTIME_', {
        1024:'REGISTER_RUNTIME_PASS cases=288 exact=1 flags=1 panels=1 failure_no_retry=1',
        256:'REGISTER_RUNTIME_UNSUPPORTED_VLEN_PASS no_effects=1'}),
    'entry': ('RUNTIME_REFERENCE_PASS_NOT_NATIVE_OR_MODEL_ACCEPTED', 'REGISTER_GUARD_', {
        1024:'REGISTER_GUARD_PASS vlen=1024 cases=28 no_effects=1 csr_preserved=1',
        256:'REGISTER_GUARD_PASS vlen=256 cases=30 no_effects=1 csr_preserved=1'}),
}


def check(root, suite):
    root=Path(root).resolve(strict=True)
    result=json.loads((root/'result.json').read_text())
    state,prefix,markers=EXPECTED[suite]
    require(result.get('state')==state and result.get('suite')==suite, 'Wrong suite/state')
    require(result.get('rtl_performance') is False and result.get('production_enabled') is False,
            'Unexpected acceptance scope')
    require(digest(root/'test')==result['elf_sha256'], 'ELF drift')
    require(digest(root/'source-pins.json')==result['source_pins_sha256'], 'Manifest drift')
    pins=json.loads((root/'source-pins.json').read_text())
    verify_pins(pins)
    require(len(result['trials'])==2 and {t['vlen'] for t in result['trials']}==set(markers),
            'Missing or duplicated machine configuration')
    artifacts={str(root/name):digest(root/name) for name in
               ('result.json','source-pins.json','commands.json','disassembly.log','test')}
    for trial in result['trials']:
        vlen=trial['vlen']; log=root/f'qemu-{vlen}.log'
        require(digest(log)==trial['log_sha256'], 'Guest log drift')
        text=log.read_text().replace('\r',''); lines=text.splitlines()
        require(trial['marker']==markers[vlen] and
                [line for line in lines if line.startswith(prefix)]==[markers[vlen]] and
                lines.count('GUEST_TEST_EXIT=0')==1 and 'Kernel panic' not in text,
                'Raw guest verdict mismatch')
        artifacts[str(log)]=digest(log)
    return dict(suite=suite,root=str(root),state=state,trials=result['trials'],
                source_pins_checked=len(pins),artifacts=artifacts)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in EXPECTED: p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    require(not args.output.exists(),'Refuse to overwrite evidence')
    reports=[check(getattr(args,name),name) for name in EXPECTED]
    result=dict(state='OUTPUT_TILE_FUNCTIONAL_ACCEPTED_ONLY',trials=reports,
        rtl_measured=False,model_integrated=False,new_hardware=False,
        limitations=['QK is synthetic in schedule tests and a reference executor in runtime tests',
                     'Real captured V is checked; real full Attention/model performance is not',
                     'Report value_decodes counts logical rows, not pairwise physical decodes'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(result['state'])


if __name__=='__main__': main()
