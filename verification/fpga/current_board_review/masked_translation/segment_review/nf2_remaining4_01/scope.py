"""Exact four archived failures per parent's latest explicit selection."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_segment_fault_handoff01')
RUNTIME_ID = 'nf2_remaining4_sv39'
CASES = [
    dict(id='u0_s0_b1_m2_f1', unmapped=0, store=0, boundary=1, mode=2, split=1, start=2),
    dict(id='u1_s1_b3_m2_f0', unmapped=1, store=1, boundary=3, mode=2, split=0, start=5),
    dict(id='u0_s1_b5_m3_f1', unmapped=0, store=1, boundary=5, mode=3, split=1, start=8),
    dict(id='u1_s0_b1_m3_f0', unmapped=1, store=0, boundary=1, mode=3, split=0, start=8),
]
CASE_HASHES = [
    'e0c5c5ed1c9de7c0819c360b45b479b1a649b9d7aff961dc4a88f044599fd856',
    '0f2dea227a1b9b88a82cccb27b43b04bffd44ba40e8c89f8f0cf9ee5c3233e75',
    '2233d79a84c62dcfcc7a6665de106bc560c20dfaa29905b651c5c335ee9b33e1',
    '614f55dad2783c16443099480b8b8c252a12fb394780662678172e65f844647e',
]
for c in CASES:
    c['historical_name'] = 'rvv_small_fault_segment_nf2_e16_m1_'+c['id']
    c['base'] = 4096-4*c['boundary']-2*c['split']
    c['mask'] = 0x24 if c['mode']==2 else 0
    c['fault'] = c['start']<8

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def require(ok, why):
    if not ok:
        raise ValueError(why)

def provenance():
    pins = {}
    def pin(p, want=None):
        got = sha(p)
        require(want is None or got==want, 'Original identity drift: '+str(p))
        pins[str(p)] = got
    ev = ARCHIVE/'evidence'
    pin(ev/'single_manifest.json', '97082460c49c616812562991c6a1fd1fee4e516c68538b869d221a2dd2249535')
    pin(ev/'single_board_report.json', '48469c93985bab5737ceacb20c04705b0f16e23183643103171e9eb3471e3706')
    manifest = json.loads((ev/'single_manifest.json').read_text())
    board = json.loads((ev/'single_board_report.json').read_text())
    selected = []
    for c,digest in zip(CASES,CASE_HASHES):
        path = ARCHIVE/'singles'/c['historical_name']
        pin(path/'case.json',digest)
        meta = json.loads((path/'case.json').read_text())
        require(next(x for x in manifest['cases'] if x['name']==c['historical_name'])==meta,
                'Single manifest metadata mismatch')
        for n,h in meta['scenario_sources'].items(): pin(path/n,h)
        pin(path/'scenario.elf',meta['sha256'])
        target = {k:c[k] for k in ('unmapped','store','boundary','mode','split')}
        require(meta['selected_trial']==target, 'Wrong single tuple')
        selector=' && '.join(f'{k if k!="store" else "store_case"}=={v}' for k,v in target.items())
        require('if(!('+selector+'))continue;' in (path/'scenario.c').read_text(), 'Actual C selector differs')
        b=next(x for x in board['results'] if x['name']==c['historical_name'])
        require(b['status']=='failed' and b['exit_code']==1, 'Missing original independent single failure')
        selected.append(dict(c, source_directory=str(path), metadata=meta, board_evidence=b))
    return dict(status='SOURCE_IDENTITIES_CHECKED_NOT_REFERENCE_OR_DUT', cases=selected, pins=pins,
                selection_authority='Latest parent coordination message overrides conflicting batch03 heading',
                runtime_id=RUNTIME_ID, single_current_oracle_not_original_parent_byte_identity=True,
                Linux_signal_frame_proven=False)

if __name__=='__main__':
    with (HERE/'source_manifest.json').open('x') as stream:
        json.dump(provenance(),stream,indent=2);stream.write('\n')
    print('SOURCE_IDENTITIES_CHECKED_NOT_REFERENCE_OR_DUT',sha(HERE/'source_manifest.json'))
