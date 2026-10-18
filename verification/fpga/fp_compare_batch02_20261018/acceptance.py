#!/usr/bin/env python3
"""Read-only terminal acceptance from actual DUT logs and sealed input hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
IMAGE=Path('/home/wangwy/fpga_runs/fp_compare_alias_fix_20261018_01/image')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def accepts(text,markers):
    veto=re.search(r'RVV_FP_COMPARE_(?:FAIL|DETAIL|CAPACITY_FAIL)|FP_BIT |'
                   r'BOARD_REPLAY_(?:TRAP|MISMATCH|SERVICE_FAIL|VLEN_FAIL)|'
                   r'SYSTEM_FAIL|FP_EDGES_FAIL|'
                   r'Fatal:|Error-\[|Core Test \*\*\* (?:FAIL|ERROR)',text)
    return bool(markers) and all(m in text for m in markers) and not veto and 'Core Test *** SUCCESS ***' in text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extra',action='append',default=[],help='Additional prepared:measured directory pair')
    args=parser.parse_args()
    ledger=json.loads((IMAGE/'image.json').read_text())
    for path,digest in ledger['files'].items():assert sha(path)==digest,path
    snapshot=Path(ledger['snapshot'])
    assert sha(snapshot/'snapshot.json')==ledger['snapshot_sha256']
    root=HERE.parents[2]
    frozen=json.loads((snapshot/'snapshot.json').read_text())
    for path,digest in frozen['live_source_sha256'].items():
        if Path(path).is_relative_to(root/'hardware/src') or Path(path).is_relative_to(root/'hardware/deps'):
            assert sha(path)==digest,path
    groups=[]
    pairs=[('scenarios_prepared03','scenarios_fixed01'),
           ('packed319_admitted01','packed319_fixed01'),
           ('neighbors_admitted01','neighbors_fixed01')]
    for extra in args.extra:
        pair=extra.split(':')
        assert len(pair)==2 and all((HERE/x).resolve().is_relative_to(HERE) for x in pair)
        pairs.append(pair)
    for prepared,measured in pairs:
        plan=json.loads((HERE/prepared/'prepared.json').read_text())
        for key in ('files','pins'):
            for path,digest in plan[key].items():assert sha(path)==digest,path
        results=json.loads((HERE/measured/'results.json').read_text())['results']
        assert len(results)==len(plan['programs'])
        assert {r['name'] for r in results}==set(plan['programs'])
        cases=[]
        for r in results:
            entry=plan['programs'][r['name']]
            elf=Path(entry['directory'])/'soc.elf'
            assert sha(elf)==entry['elf_sha256']
            log=HERE/measured/r['name']/'vcs.log'
            text=log.read_text(errors='replace')
            assert r['returncode']==0 and r['status']=='PASS' and accepts(text,entry['pass_markers']),r['name']
            assert not accepts(text+'\nBOARD_REPLAY_MISMATCH\n',entry['pass_markers'])
            assert not accepts(text+'\nRVV_FP_COMPARE_DETAIL\n',entry['pass_markers'])
            assert not accepts(text.replace(entry['pass_markers'][0],''),entry['pass_markers'])
            command=json.loads((log.parent/'vcs.command.json').read_text())
            assert command[0]==ledger['simv'] and '+PRELOAD='+str(elf) in command
            cases.append(dict(name=r['name'],elf_sha256=sha(elf),log_sha256=sha(log),elapsed_s=r['elapsed_s']))
        groups.append(dict(name=measured,programs_passed=len(cases),cases=cases))
    controls=[]
    for name in ('unboxed_unmasked_alias_v16_e32_m1_t0_ctx0',
                 'unmasked_alias_v8_e32_m4_t0_ctx0','unmasked_alias_v16_e32_m8_t0_ctx0'):
        old=HERE/'scenarios_vcs02'/name/'trace_hart_0.log'
        new=HERE/'scenarios_fixed01'/name/'trace_hart_0.log'
        assert old.read_bytes()==new.read_bytes()
        controls.append(dict(name=name,trace_sha256=sha(new),cycle_and_instruction_trace_identical=True))
    baseline=json.loads((HERE/'remaining_baseline01/results.json').read_text())['results']
    assert len(baseline)==4 and all(r['original_board_signature_reproduced'] for r in baseline)
    cause=json.loads((HERE/'cycle_cause.json').read_text())
    assert cause['status']=='PASS_CAUSE_AND_CORRECTED_SOURCE_STREAM'
    for path,digest in cause['source_sha256'].items():assert sha(path)==digest,path
    result=dict(status='PASS_TERMINAL_AUDIT',groups=groups,ordinary_path_controls=controls,
                cycle_cause_sha256=sha(HERE/'cycle_cause.json'),
                programs_passed=sum(g['programs_passed'] for g in groups),
                scope='Exactly the named terminal groups and their sealed test scopes; not new-bitstream FPGA or complete original Linux ELF acceptance')
    (HERE/'acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],groups=[dict(name=g['name'],programs_passed=g['programs_passed']) for g in groups],ordinary_traces_identical=len(controls)),indent=2))


if __name__=='__main__':main()
