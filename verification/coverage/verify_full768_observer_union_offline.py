"""Exact retained whole-field ownership closure; no EDA or original-file writes."""
import argparse
import copy
import csv
import inspect
import json
import re
import subprocess
from pathlib import Path
from types import FunctionType, SimpleNamespace

import report_native_batch768_v3 as report
import report_native_increment769 as launch

life,require=report.life,report.require
OUT=launch.PREDECESSOR
SEAL=launch.PREDECESSOR_SHA
ERROR='Observer target/protected membership differs: accumulator_updates_o[31:0]'


def export_partition(text,c):
    """Bind annotations to sealed scope/owner templates, not DVE export order."""
    frozen=report.private_namespace()
    blocks=report.base.prior.old.blocks
    template=(OUT/'combined.el').read_text()
    approved={}
    for scope,block in blocks(template):
        approved.setdefault(scope,set()).update(l for l in block.splitlines() if l.startswith('ANNOTATION:'))
    actual={}
    for scope,block in blocks(text):
        actual.setdefault(scope,set()).update(l for l in block.splitlines() if l.startswith('ANNOTATION:'))
    require(actual==approved,'Exact sealed per-scope annotation union differs')
    templates={}
    for owner,part in frozen['partition'](template,c).items():
        for scope,block in blocks(part):
            header=tuple(l for l in block.splitlines() if l.startswith(('CHECKSUM:','INSTANCE:')))
            templates.setdefault((scope,owner,header),[]).extend(l for l in block.splitlines() if l.startswith('ANNOTATION:'))
    routes={(scope,name):key for key,item in c['new_families'].items()
            for scope,names in item['signals'].items() for name in names}
    require(len(routes)==sum(len(n) for i in c['new_families'].values() for n in i['signals'].values()),
            'New field ownership overlap')
    headers=set();directives={};retained=[]
    for scope,block in blocks(text):
        header=tuple(l for l in block.splitlines() if l.startswith(('CHECKSUM:','INSTANCE:')))
        headers.add((scope,header))
        oldlines=[]
        for line in block.splitlines():
            if not line or line.startswith(('//','CHECKSUM:','INSTANCE:')):continue
            if line.startswith('ANNOTATION:'):
                if line in templates.get((scope,'retained',header),[]):oldlines.append(line)
                continue
            m=re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?(\S+)',line)
            owner=routes.get((scope,m[1]),'retained') if m else 'retained'
            require((scope,owner,header) in templates,'Unknown scope/field owner/checksum')
            directives.setdefault((scope,owner,header),[]).append(line)
            if owner=='retained':oldlines.append(line)
        if oldlines:retained.append('\n'.join(list(header)+oldlines)+'\n')
    require(headers=={(s,h) for s,owner,h in templates},'Exact bidirectional scope/checksum inventory differs')
    parts={k:[] for k in frozen['partition'](template,c)}
    for (scope,owner,header),annotations in templates.items():
        require((scope,header) in headers,'Sealed owner scope/checksum missing')
        if owner=='retained':continue
        parts[owner].append('\n'.join(list(header)+annotations+directives.get((scope,owner,header),[]))+'\n')
    parts['retained']=retained
    return {k:''.join(v) for k,v in parts.items()}


def export_records(text,c):
    ns=report.private_namespace();ns['partition']=export_partition
    return FunctionType(ns['records'].__code__,ns)(text,c)


def corrected_groups(c):
    groups=report.private_namespace()['merged_observers'](c)
    byscope={i['scope']:i for i in groups.values()};proof=[]
    for key,refskey in (('child_config','child_references'),('diagnostic_config','diagnostic_references')):
        require(len(c[key]['instances'])==len(c[refskey]),'Complete old ownership inventories')
        for instance,reference in zip(c[key]['instances'],c[refskey]):
            scope=instance['scope']
            if scope not in byscope:continue
            group=byscope[scope]
            require(sorted(reference)==sorted(group['reference']),'Old/new full native identity differs')
            added=[]
            for signal in instance['signals']:
                bits=signal['bits']
                require(len(bits)==len(set(bits)),'Duplicate source bit')
                complete=set(range(signal['right'],signal['left']+1))
                if set(bits)!=complete:continue  # A partial vector never grants whole-object flag1.
                shape=signal['shape']
                require(shape['name']==signal['name'] and
                        (signal['scalar'] or (int(shape['left']),int(shape['right']))==
                         (signal['left'],signal['right'])),'Exact retained source declaration')
                label=signal['native_label']
                require(sum(row[2]==label for row in reference)==1,'Old typed native field not unique')
                if label not in group['targets']:added.append(label)
            group['targets']=sorted(set(group['targets'])|set(added))
            if added:proof.append(dict(scope=scope,owner=key,labels=added,
                authority='Existing sealed source-selected full range, both directions; not new accum66 membership'))
    return groups,proof


def audit_observers(out,c):
    ns=report.private_namespace()
    # Every paired coordinate, annotation, source signature and retained partial bit
    # remains enforced by the unmodified canonical parsers before flag reconciliation.
    for name in ('applied.el','reloaded.el'):
        require(export_records((out/name).read_text(),c)==c['expected_union'],'Exact global coordinate union differs')
    groups,proof=corrected_groups(c)
    report.base.prior.audit_observers(out,dict(c,observer_captures=groups))
    original=ns['merged_observers'](c);diff=[]
    for index,(key,item) in enumerate(original.items()):
        allowed=set(groups[key]['targets'])-set(item['targets'])
        for stage in report.base.prior.STAGES:
            path=out/('observer766_%s_%d.tsv'%(stage,index))
            with path.open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
            for row in rows:
                expected=str(int(stage in ('selected','reloaded') and row['name'] in item['targets']))
                if row['excluded']!=expected:
                    require(stage in ('selected','reloaded') and row['name'] in allowed and
                            expected=='0' and row['excluded']=='1','Not exact old whole-owner conflict')
                    diff.append(dict(index=index,scope=item['scope'],stage=stage,name=row['name'],
                                     original_expected=expected,actual=row['excluded']))
    require(len(diff)==168 and len({(d['scope'],d['name']) for d in diff})==84,
            'Exact actual retained owner mismatch set differs')
    return dict(whole_owner_proof=proof,exact_conflicts=diff,unique_fields=84,
                changed_EL_coordinates=0,partial_vector_membership_relaxed=False,
                full_five_stage_complement_passed=True)


def terminal_evidence(log,failure,live,receipt,body,fields):
    require(failure==dict(reason=ERROR,no_retry=True),'Not exact recorded observer failure')
    require(receipt['config_sha256']==SEAL and receipt['actual_dve_pid']==live['pid'] and
            receipt['actual_dve_cwd']==str(OUT) and live['executable_verified'] is True,
            'Actual original launch identity differs')
    require(log.startswith('EXACT742_LIVE pid=%s launch=%s\n'%(live['pid'],live['launch_pid'])) and
            log.count('Traceback (most recent call last):')==1 and
            log.rstrip().endswith('ValueError: '+ERROR) and 'in audit_observers' in log and
            'report_fsm_observers742.py", line 37, in run' in log,
            'Real traceback does not establish verifier-only failure boundary')
    require("require(code == 0, 'DVE nonzero exit')\n        verify(out, seal)" in body,
            'Pinned zero-return-before-verification lifecycle differs')
    require(fields.get('Id')==receipt['unit'] and fields.get('ActiveState')=='failed'
            and fields.get('ExecMainCode')=='1' and fields.get('ExecMainStatus')=='1'
            and fields.get('ExecMainPID')==str(receipt['runner_pid']),
            'Actual wrapper failed status1 must remain recorded')
    command=fields.get('ExecStart','')
    require(str(Path(report.__file__).resolve()) in command and str(OUT) in command and SEAL in command,
            'Original systemd command/config differs')
    return dict(source='SEALED_LIFECYCLE_ZERO_RETURN_GUARD_AND_REAL_VERIFIER_TRACEBACK',
                launch_process_returncode=0,standalone_DVE_OS_return_receipt_available=False,
                wrapper_OS_exit_status=1,wrapper_failed_at_native_observer_verification=True,
                systemd_properties=fields,actual_systemd_unit=receipt['unit'],
                real_stdout=str(OUT/'service.log'),copied_or_synthesized_stdout=False)


def verify(destination):
    require(destination.parent==life.OUT and not destination.exists() and destination!=OUT,'Fresh offline closure only')
    require(not (OUT/'qualification.json').exists(),'Do not overwrite original failure')
    receipt=life.read_bound(launch.UNIT_RECEIPT,launch.UNIT_RECEIPT_SHA)
    failure=json.loads((OUT/'failure.json').read_bytes());live=json.loads((OUT/'live-identity.json').read_bytes())
    names='Id,LoadState,ActiveState,SubState,ExecMainPID,ExecMainCode,ExecMainStatus,ExecStart'
    text=subprocess.check_output(['systemctl','--user','show',receipt['unit'],'--property='+names],text=True)
    fields=dict(line.split('=',1) for line in text.splitlines())
    body=inspect.getsource(report.base.prior.old.frozen.prior.old.base.run)
    terminal=terminal_evidence((OUT/'service.log').read_text(),failure,live,receipt,body,fields)
    before={str(p):life.digest(p) for p in OUT.rglob('*') if p.is_file()}
    external={str(launch.UNIT_RECEIPT):launch.UNIT_RECEIPT_SHA,
              str(Path(__file__).resolve()):life.digest(__file__),
              str(HERE/'test_verify_full768_observer_union_offline.py'):life.digest(HERE/'test_verify_full768_observer_union_offline.py')}
    c=report.namespace()['check'](OUT,SEAL)
    reconciled=audit_observers(OUT,c)
    destination.mkdir();result={}
    def snapshot(data,out):
        require(out==OUT and data['output_pins']==before,'Original output byte inventory differs')
        data.update(population=768,formal768_manifest_seal=report.base.MANIFEST_SHA,
            source_first_full_session_qualified=sorted(report.FIRST),
            source_first_local_qualification_inherited=False,
            fixed120_parent_offline_qualification_seal=report.FIXED_SHA,
            terminal_evidence=terminal,offline_closure='EXACT_RETAINED_WHOLE_OWNER_UNION_REPLAY',
            observer_owner_reconciliation=reconciled,original_failure_preserved=True,EDA_replayed=False,
            lifecycle_stdout=dict(path=str(OUT/'service.log'),sha256=before[str(OUT/'service.log')],
                                  immutable_terminal_log=True,no_snapshot_copy=True),
            main_root_toggle_hit_total=None)
    def save(path,data):
        require(path==OUT/'qualification.json' and not result,'Only redirect final qualification write')
        result.update(copy.deepcopy(data));result['offline_adapter_pins']=external
        life.check(before);life.check(external);life.save(destination/'qualification.json',result)
    def digest(path):
        if Path(path)==OUT/'qualification.json':
            require(result,'Final redirected result absent');return life.digest(destination/'qualification.json')
        return life.digest(path)
    ns=report.namespace();ns.update(audit_observers=audit_observers,snapshot_stdout=snapshot,records=export_records,
        life=SimpleNamespace(**dict(vars(life),save=save,digest=digest)))
    FunctionType(ns['verify'].__code__,ns)(OUT,SEAL)
    require(result and result['population']==768 and result['config_seal']==SEAL,'Substantive full replay incomplete')
    life.check(before);life.check(external)
    sha=life.digest(destination/'qualification.json')
    life.save(destination/'closure.json',dict(status='FULL768_RETAINED_OWNER_OFFLINE_CLOSURE_PASS',
        source=str(OUT),config_seal=SEAL,qualification_sha256=sha,input_pins=before,
        external_pins=external,terminal_evidence=terminal,original_failure_preserved=True,
        source_directory_unchanged=True,EDA_launched=False))
    print(json.dumps(dict(output=str(destination),qualification_seal=sha,
        closure_seal=life.digest(destination/'closure.json'),system=result['system'])),flush=True)


HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();verify(a.output.resolve())
