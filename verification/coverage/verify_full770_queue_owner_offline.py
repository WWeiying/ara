"""Offline-only full770 closure: reconcile exact retained scalar queue owners."""
import argparse
import copy
import csv
import inspect
import json
from pathlib import Path
import subprocess
from types import FunctionType, SimpleNamespace
import report_native_increment770_offline768 as frozen

life,require=frozen.life,frozen.require
HERE=Path(__file__).resolve().parent
OUT=life.OUT/'native-increment770-offline768-prepared-agent-20261007-02'
SEAL='6135d75162beef44ceb14fcd49e60d52026c57016d344c5aedc053d9577a0bd3'
UNIT='ara-native-increment770-offline-parent-20261007-02.service'
ERROR='Observer target/protected membership differs: cmd_pop_o'
STAGES=('before','selected','reset','reloaded','final')


def corrected_groups(c, original=None):
    groups=copy.deepcopy(original if original is not None else frozen.context()['private_namespace']()['merged_observers'](c))
    authority={tuple(row) for row in c['expected_union']['retained']['retained']['prior']['queue']}
    require(len(c['queue_config']['instances'])==len(c['queue_references']),'Complete retained queue inventories')
    proof=[]
    for instance,reference in zip(c['queue_config']['instances'],c['queue_references']):
        matches=[(key,g) for key,g in groups.items() if g['scope']==instance['scope']]
        if not matches:continue
        require(len(matches)==1,'Ambiguous observer owner')
        key,group=matches[0]
        if not key.startswith('queue312'):continue
        require(sorted(reference)==sorted(group['reference']),'Retained/new full native identity differs')
        labels=[]
        for signal in instance['signals']:
            name=signal['name']
            if name not in ('cmd_pop_o','flush_i'):continue
            require(signal['scalar'] is True and signal['left']==signal['right']==0 and signal['bits']==[0],
                    'Only complete retained scalar owners allowed')
            shape=signal['shape'];label=signal['native_label']
            require(shape['name']==name==label and shape['type']=='1' and
                    shape['portnode']==('3' if name=='cmd_pop_o' else '2'), 'Exact retained declaration/port role')
            require(sum(row[2]==label for row in reference)==1,'Unique native source label')
            require(all((instance['scope'],name,0,d) in authority for d in ('0to1','1to0')),
                    'Both exact old EL directions required')
            require(label not in group['targets'],'Retained scalar unexpectedly already owned')
            labels.append(label)
        require(sorted(labels)==['cmd_pop_o','flush_i'],'Exact two retained owners per queue')
        group['targets']=sorted(set(group['targets'])|set(labels))
        proof.append(dict(index=list(groups).index(key),key=key,scope=instance['scope'],labels=sorted(labels),
            design_module_checksum=instance['design_module_checksum'],toggle_checksum=instance['toggle_checksum'],
            source_shapes={s['name']:s['shape'] for s in instance['signals'] if s['name'] in labels},
            authority='Sealed retained queue_config complete scalar plus exact prior canonical both directions'))
    require(len(proof)==20 and sum(len(p['labels']) for p in proof)==40,'Exact retained 20scope/40scalar closure')
    return groups,proof


def audit_observers(out,c):
    ns=frozen.context()['private_namespace']()
    for name in ('applied.el','reloaded.el'):
        require(ns['records']((out/name).read_text(),c)==c['expected_union'],'Exact full canonical EL union differs')
    original=ns['merged_observers'](c);groups,proof=corrected_groups(c,original)
    # Keep the original complete five-stage identity/schema/flag auditor.
    frozen.closure.report.base.prior.audit_observers(out,dict(c,observer_captures=groups))
    differences=[]
    for index,(key,item) in enumerate(original.items()):
        allowed=set(groups[key]['targets'])-set(item['targets'])
        for stage in STAGES:
            with (out/('observer766_%s_%d.tsv'%(stage,index))).open() as stream:
                for row in csv.DictReader(stream,delimiter='\t'):
                    wanted=str(int(stage in ('selected','reloaded') and row['name'] in item['targets']))
                    if row['excluded']!=wanted:
                        require(key.startswith('queue312') and row['name'] in allowed and
                                stage in ('selected','reloaded') and wanted=='0' and row['excluded']=='1',
                                'Not the exact retained scalar owner conflict')
                        differences.append(dict(index=index,scope=item['scope'],stage=stage,name=row['name'],
                                                prior_expected=wanted,actual=row['excluded']))
    require(len(differences)==80 and len({(d['scope'],d['name']) for d in differences})==40,'Exact actual conflict set differs')
    return dict(proof=proof,conflicts=differences,unique_retained_scalars=40,changed_EL_coordinates=0,
                partial_bit_membership_relaxed=False,full_five_stage_complement_passed=True)


def terminal_evidence(log,failure,live,body,fields):
    require(failure==dict(reason=ERROR,no_retry=True),'Exact original verifier failure required')
    require(log.startswith('EXACT742_LIVE pid=%s launch=%s\n'%(live['pid'],live['launch_pid'])) and
            log.count('Traceback (most recent call last):')==1 and log.rstrip().endswith('ValueError: '+ERROR) and
            'in audit' in log and 'in audit_observers' in log and live['executable_verified'] is True,
            'Original verifier-only traceback/live identity differs')
    require("require(code == 0, 'DVE nonzero exit')\n        verify(out, seal)" in body,'Pinned zero-return-before-verify guard differs')
    require(fields.get('Id')==UNIT and fields.get('LoadState')=='loaded' and
            fields.get('ActiveState')=='failed' and fields.get('SubState')=='failed' and
            fields.get('ExecMainCode')=='1' and fields.get('ExecMainStatus')=='1' and
            fields.get('ExecMainPID')=='252774','Preserve actual wrapper failure1; active/unknown/zero rejected')
    command=fields.get('ExecStart','')
    require(str(Path(frozen.__file__).resolve()) in command and str(OUT) in command and SEAL in command,
            'Actual foreground command/config binding differs')
    return dict(source='PINNED_ZERO_RETURN_GUARD_AND_REAL_VERIFIER_ONLY_TRACEBACK',
                launch_process_returncode=0,standalone_DVE_OS_return_receipt_available=False,
                wrapper_OS_exit_status=1,actual_systemd_unit=UNIT,systemd_properties=fields,
                actual_live_identity=live,real_stdout=str(OUT/'service.log'),copied_or_synthesized_stdout=False)


def verify(destination):
    require(destination.parent==life.OUT and not destination.exists() and destination!=OUT,'Fresh independent offline closure')
    require(not (OUT/'qualification.json').exists(),'Do not overwrite original failure')
    names='Id,LoadState,ActiveState,SubState,ExecMainPID,ExecMainCode,ExecMainStatus,ExecStart,StandardOutput'
    text=subprocess.check_output(['systemctl','--user','show',UNIT,'--property='+names],text=True)
    fields=dict(line.split('=',1) for line in text.splitlines())
    live=json.loads((OUT/'live-identity.json').read_bytes());failure=json.loads((OUT/'failure.json').read_bytes())
    body=inspect.getsource(frozen.closure.report.base.prior.old.frozen.prior.old.base.run)
    terminal=terminal_evidence((OUT/'service.log').read_text(),failure,live,body,fields)
    before={str(p):life.digest(p) for p in OUT.rglob('*') if p.is_file()}
    external={str(Path(__file__).resolve()):life.digest(__file__),
              str(HERE/'test_verify_full770_queue_owner_offline.py'):life.digest(HERE/'test_verify_full770_queue_owner_offline.py')}
    ns=frozen.context()['namespace']();c=ns['check'](OUT,SEAL)
    reconciled=audit_observers(OUT,c)
    destination.mkdir();result={}
    def snapshot(data,out):
        require(out==OUT and data['output_pins']==before,'Complete immutable original output inventory differs')
        data.update(population=770,formal770_manifest_seal=frozen.MANIFEST_SHA,
                    queue312_first_full_session_qualified=True,
                    source_first_full_session_qualified=sorted(set(frozen.frozen.frozen.inherited.FIRST)|{'queue312'}),
                    source_first_local_qualification_inherited=False,lzc_assigned_bits=23132,
                    LZC_initial_X_excluded=False,LZC_spare_bits_retained=212,
                    terminal_evidence=terminal,observer_owner_reconciliation=reconciled,
                    offline_closure='EXACT_RETAINED_QUEUE_SCALAR_OWNER_REPLAY',
                    original_failure_preserved=True,EDA_replayed=False,main_root_toggle_hit_total=None,
                    lifecycle_stdout=dict(path=str(OUT/'service.log'),sha256=before[str(OUT/'service.log')],
                                          immutable_terminal_log=True,no_snapshot_copy=True))
    def save(path,data):
        require(path==OUT/'qualification.json' and not result,'Only redirect the final qualification write')
        result.update(copy.deepcopy(data));result['offline_adapter_pins']=external
        life.check(before);life.check(external);life.save(destination/'qualification.json',result)
    def digest(path):
        if Path(path)==OUT/'qualification.json':
            require(result,'Final qualification missing');return life.digest(destination/'qualification.json')
        return life.digest(path)
    ns.update(audit_observers=lambda out,c:audit_observers(out,c),snapshot_stdout=snapshot,
              life=SimpleNamespace(**dict(vars(life),save=save,digest=digest)))
    FunctionType(ns['verify'].__code__,ns)(OUT,SEAL)
    require(result and result['population']==770 and result['config_seal']==SEAL,'Substantive full replay incomplete')
    life.check(before);life.check(external)
    sha=life.digest(destination/'qualification.json')
    life.save(destination/'closure.json',dict(status='FULL770_RETAINED_QUEUE_OWNER_OFFLINE_CLOSURE_PASS',
        source=str(OUT),config_seal=SEAL,qualification_sha256=sha,input_pins=before,external_pins=external,
        terminal_evidence=terminal,source_directory_unchanged=True,original_failure_preserved=True,EDA_launched=False))
    print(json.dumps(dict(output=str(destination),qualification_seal=sha,
                          closure_seal=life.digest(destination/'closure.json'),system=result['system'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();verify(a.output.resolve())
