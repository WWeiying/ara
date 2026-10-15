#!/usr/bin/env python3
"""Read frozen preparation and write one owned readiness/budget artifact; no simulator."""
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('arithmetic_preparation',HERE/'prepare.py')
prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)
sha,require=prep.sha,prep.require


def main():
    out=HERE/'prepared02';result=HERE/'readiness01.json'
    require(not result.exists(),'Do not overwrite readiness evidence')
    pins=json.loads((out/'input_pins.json').read_text())
    for path,digest in pins.items():require(sha(Path(path))==digest,'Input pin mismatch: '+path)
    prep.helper.prepare.check(out/'prepared')
    soc=json.loads((out/'soc/programs.json').read_text())
    spike=json.loads((out/'spike/programs.json').read_text())
    status=json.loads((out/'status.json').read_text())
    host=json.loads((out/'host/status.json').read_text())
    identity=json.loads((out/'original_identity.json').read_text())
    require(status['status']=='READY_5_ORIGINAL_PREFIXES_HOST_SPIKE_NOT_DUT','Preparation incomplete')
    require(len(host['positive'])==10 and len(host['negative'])==40,'Host coverage incomplete')
    require(all(x['status']=='PASS' for x in host['positive']) and all(x['rejected'] for x in host['negative']),
            'Host check failure')
    expected_names={p['id'] for p in prep.parts()}
    require(set(soc['programs'])==set(spike['programs'])==expected_names,'Wrong five programs')
    # Check every drained tuple, not only the terminal trial number.
    inputs=json.loads((out/'host/arithmetic_e8_m4_prefix56.inputs.json').read_text())
    require([[str(x[k]) for k in ('seed','vl','mode','vstart','trial')] for x in inputs]==identity['trace_trials'],
            'Original drained trace and full prefix disagree')
    alias=HERE.parent/'mask_alias_original'
    completed=json.loads((alias/'vcs_candidate02_01/complete.json').read_text())
    refs=json.loads((alias/'bounded01/reference/status.json').read_text())['results']
    measured=[]
    for case in completed['stages'][1]['results']:
        ref=next(r for r in refs if r['name']==case['name'])
        require(case['status']=='PASS' and case['returncode']==0,'Budget anchor not accepted')
        measured.append(dict(name=case['name'],elapsed_s=case['elapsed_s'],
                             spike_instructions=ref['instructions_to_replay_exit'],
                             seconds_per_instruction=case['elapsed_s']/ref['instructions_to_replay_exit']))
    rates=[r['seconds_per_instruction'] for r in measured];records=[]
    for p in prep.parts():
        name=p['id'];r=next(r for r in status['results'] if r['name']==name)
        require(r['status']=='PASS','Missing Spike PASS')
        for ledger in (soc,spike):
            entry=ledger['programs'][name]
            require(sha(Path(entry['path']))==entry['sha256'],'ELF mismatch')
        require(r['elf_sha256']==spike['programs'][name]['sha256'],'Reference ELF mismatch')
        require(sha(out/'reference'/(name+'.log'))==r['log_sha256'],'Reference log mismatch')
        original=next(c for c in identity['original22'] if c['name']==p['original'])
        dis=(prep.RECOVERY/(p['original']+'_decode/original.dis')).read_text()
        target=re.search(r'^\s*([0-9a-f]+):\s+00880c57\s+vadd.vv\s+v24,v8,v16,v0.t',dis,re.M)
        require(target is not None,'Archived target missing')
        require((out/'prepared'/name/'original/scenario.S').read_bytes()==Path(original['assembly']).read_bytes(),
                'Assembly changed')
        instructions=r['instructions_to_replay_exit']
        records.append(dict(**p,original_elf_sha256=original['sha256'],original_target_pc='0x'+target[1],
                            soc_elf_sha256=soc['programs'][name]['sha256'],
                            soc_target_pc=hex(soc['programs'][name]['target_pc']),
                            spike_instructions=instructions,
                            estimated_vcs_seconds=[round(instructions*min(rates),1),round(instructions*max(rates),1)],
                            proposed_inner_timeout_s=4000 if p['cap']>=512 else 1800))
    evidence={str(p):sha(p) for p in [Path(__file__),out/'status.json',out/'input_pins.json',out/'original_identity.json',
              out/'prepared/provenance.json',out/'host/status.json',out/'reference/status.json',
              out/'reference/vstart_probe/spike_probe.json',out/'soc/programs.json',out/'spike/programs.json',
              prep.RECOVERY/'report.json',alias/'vcs_candidate02_01/complete.json',alias/'bounded01/reference/status.json']}
    report=dict(status='READY_REFERENCE_ONLY_NO_DUT',records=records,input_pins_checked=len(pins),
                unique_original_trials=sum(p['configurations'] for p in prep.parts()),
                trace_all56_tuples_equal=True,host_positive_runs=10,host_negative_rejections=40,spike_pass=5,
                exact_reconstructed_original_linux_elf_count=22,original_C_bytes_recovered=False,
                original_matrices_executed=False,RTL_modified=False,VCS_launched=False,
                budget_anchors=measured,budget_limitation='Cross-suite host-wall extrapolation, not measured RTL cycles or guarantee',
                proposed_jobs=1,proposed_outer_timeout_s=16800,
                future_acceptance='Fresh image/source/ELF pins; exact five COMPLETE/PASS results and exit0; exact marker counts; firmware SUCCESS; raw failure veto even if PASS also appears',
                required_raw_veto=['RVV_MATRIX_FAIL','RVV_MATRIX_FAILED','RVV_MATRIX_UNSUPPORTED_CAPACITY',
                                   'BOARD_CASE_FAIL','BOARD_REPLAY_TRAP','BOARD_REPLAY_MISMATCH',
                                   'BOARD_REPLAY_SERVICE_FAIL','BOARD_REPLAY_VLEN_FAIL','Core Test *** FAILED',
                                   'Error-[','Fatal','FATAL','UVM_FATAL'],
                evidence=evidence)
    result.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],input_pins=report['input_pins_checked'],
                         records=[{k:r[k] for k in ('id','spike_instructions','estimated_vcs_seconds','proposed_inner_timeout_s')}
                                  for r in records]),indent=2))


if __name__=='__main__':
    main()
