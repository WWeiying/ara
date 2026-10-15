"""Ten-job NF2 scope/artifact adapter; reuse both immutable observer generations."""
import math
from pathlib import Path
import re
import subprocess
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REF=HERE.parent/'nf2_remaining34_prepare01'
J4=HERE.parent/'sv39'
sys.path.insert(0,str(ROOT/'gather_repair05'))
import regression as common
read,sha,require=common.read,common.sha,common.require
READY_SHA='47d7e85317fdd848ce1cfb7094920019588cde0f92183667602e6dd7b54ed3ca'
IMAGE_SHA='a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
J4_SHA='2ddce29de6d035fb02616f7924235b03e8863a74dfad161c3b2a4219ced61a67'
SHAPES=[f'group{i:02d}' for i in range(1,10)]+['J4']
VALIDATION_RESERVE=600
VETO=re.compile(common.BAD.pattern+r'|NF2_REMAINING34_SV39_FAIL|SEGMENT_SV39_FAIL|BOARD_REPLAY_MISMATCH|\b(?:FAIL|FAILED|ABORT|MISMATCH)\b',re.I)

def budget(records):return math.ceil(records*1.2/273/300)*300

def scope():
    require(sha(REF/'READY.json')==READY_SHA,'Sealed reference READY drift')
    ready=read(REF/'READY.json');manifest=read(REF/'source_manifest.json');cases=[]
    require(ready['status']=='REFERENCE9_PASS_34_SOURCE_SINGLES_PENDING_INDEPENDENT_REVIEW_NOT_DUT' and
            ready['group_dimensions']==[4]*8+[2],'Exact reference scope')
    for g,cfg in zip(ready['groups'],manifest['groups']):
        require(g['id']==cfg['id'] and g['cases']==[c['id'] for c in cfg['cases']],'Group membership/order')
        e=g['soc_elf'];require(sha(Path(e['path']))==e['sha256'],'Exact source ELF drift')
        cases.append(dict(id=cfg['runtime_id'],original_name='rvv_fault_replay_segment_nf2_e16_m1',
            historical_names=[c['historical_name'] for c in cfg['cases']],group=g['id'],kind='remaining34',
            source_cases=g['cases'],original_case_sha256=[c['case_sha256'] for c in cfg['cases']],
            elf=e['path'],sha256=e['sha256'],timeout_s=budget(g['parsed_spike_records']),
            reference_records=g['parsed_spike_records'],MX_N=g['MX_N'],checks=g['checks'],
            fault_cases=sum(c['fault'] for c in cfg['cases']),
            pass_markers=['NF2_REMAINING34_SV39_PASS']))
    old=read(J4/'reference01/status.json')
    require(old['status']=='HOST_SPIKE_PASS_NOT_DUT' and old['elf_sha256']['soc']==J4_SHA and
            sha(J4/'reference01/soc.elf')==J4_SHA and old['commits']==1189205 and old['checks']==4133,
            'Exact original J4 ELF/golden contract')
    cases.append(dict(id='nf2_j4_m6',original_name='nf2_segment4',historical_names=old['cases'],
        group='J4',kind='old_J4_M6_replay',source_cases=manifest['excluded_J2'],
        positive_controls=['u0_s0_b5_m2_f1','u0_s1_b5_m2_f1'],
        elf=str(J4/'reference01/soc.elf'),sha256=J4_SHA,timeout_s=budget(old['commits']),
        reference_records=old['commits'],MX_N=4,checks=4133,fault_cases=2,
        pass_markers=['SEGMENT_SV39_PASS'],old_acceptance_image='M2_NOT_M6'))
    all_ids=[s for c in cases for s in c['source_cases']]+manifest['excluded_pilot4']
    require(len(all_ids)==len(set(all_ids))==40 and set(all_ids)=={c['id'] for c in manifest['all_cases']},
            'Exact40 closure identity, excluding both positive controls')
    require(len(cases)==10 and [c['MX_N'] for c in cases[:9]]==[4]*8+[2] and
            all(c['timeout_s']<=10800 for c in cases),'Ten jobs / per-ELF bound')
    return cases

def source_pins():
    ready=read(REF/'READY.json');pins={**ready['pins'],str(REF/'READY.json'):READY_SHA}
    pins.update(read(J4/'reference01/input_pins.json'))
    for p in (J4/'reference01').rglob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    for n in ('csv_check.py','reference.py','fixture.c','fixture.h','fixture.S','DUT_REPORT.md','REFERENCE_REPORT.md'):
        pins[str(J4/n)]=sha(J4/n)
    common.base.verify_pins(pins)
    return pins

def runtime_case(case):
    require(case['kind'] in ('remaining34','old_J4_M6_replay') and case['id']!=case['original_name'],
            'Explicit distinct runtime/provenance identities required')
    return dict(case,original_name=case['id'])

def artifacts(result,case,ledger):
    common.check_artifacts(result,runtime_case(case),ledger)
    root=result.artifact_dir
    for p in (root/'console.log',root/'work/run.vcs.log'):
        require(not VETO.search(p.read_text()),'Raw failure veto: '+str(p))
    require((root/'console.log').read_text().count(case['pass_markers'][0])==1,'Exact firmware PASS marker')
    child=read(root/'child_outcome.unvalidated.json')
    require(child['schema']=='UNVALIDATED_CHILD_OUTCOME_V1' and child['status']=='PASS' and not child['reason'] and
            type(child['returncode']) is int and child['returncode']==result.returncode==0 and
            child['name']==result.name==case['id'] and child['elapsed_s']==result.elapsed_s and
            child['architectural_acceptance'] is False and not child.get('command_read_error') and
            child['command']==read(root/'command.json') and child['command_sha256']==sha(root/'command.json'),
            'Direct persisted child outcome mismatch')
    if case['kind']=='remaining34':
        command=[sys.executable,'-B',str(REF/'observer_cli.py'),'--group',case['group'],
                 '--csv',str(root/'commit_trace.csv'),'--out',str(root/'observer.json')]
    else:
        command=[sys.executable,'-B',str(J4/'csv_check.py'),str(root/'commit_trace.csv'),
                 '--symbols',str(J4/'reference01/soc.symbols.json')]
    common.save(root/'observer.command.json',dict(command=command,cwd=str(HERE),timeout_s=VALIDATION_RESERVE))
    with (root/'observer.stdout').open('x') as stdout,(root/'observer.stderr').open('x') as stderr:
        process=subprocess.run(command,cwd=HERE,stdout=stdout,stderr=stderr,timeout=VALIDATION_RESERVE)
    require(process.returncode==0,'Original observer failed')
    report=read(root/'observer.json') if case['kind']=='remaining34' else read(root/'observer.stdout')
    require(report['status']=='NF2_CSV_ORACLE_PASS' and report['cases']==list(range(case['MX_N'])) and
            len(report['checkpoints'])==2*case['MX_N'],'Observer exact case/checkpoint scope')
    require(report['checks']==case['checks']-sum(report['alternate_protected_field']),
            'Exact firmware check count with original field-address allowance')
    return dict(status='STRICT_NF2_ORIGINAL_SCOPE_PASS',case_id=case['id'],observer=report,
        source_cases=case['source_cases'],positive_controls=case.get('positive_controls',[]),
        observer_generation=case['kind'],current_image='M6',Linux_signalframe_proved=False,
        child_outcome_sha256=sha(root/'child_outcome.unvalidated.json'))
