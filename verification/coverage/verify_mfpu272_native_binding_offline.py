"""Offline typed display aliases only; preserve failed readonly run, no EDA."""
import argparse
import copy
import inspect
import json
from pathlib import Path
import subprocess

import mfpu_constants272_native_bind as frozen

life,require=frozen.life,frozen.require
HERE=Path(__file__).resolve().parent
RUN=life.OUT/'mfpu-constants272-readonly-native-binding-prepared-agent-20261007-02'
SEAL='01b938fe098477b772226aa4e376f8253d0cccf9fa87533425733e36c45553b1'
FROZEN_SHA='bb072fabd3cc858c1a8fdcb4d7ae57ef0dd6d17f3f0e4a1ffce833dcf311e9b3'
UNIT='ara-mfpu272-readonly-parent-20261007-01.service'
ERROR='Unknown/ambiguous native source object: gen_parallel_slices[1].active_format.mask_slice'


def match_label(n,label,row_type):
    result=frozen.match_label(n,label,row_type)
    if result is not None:return result
    if (n['kind']=='vectornode' and n['left']==n['right']=='0' and n['portnode']=='0' and
            row_type=='signal' and label==n['name']):return ('aggregate',None)
    return None


def native_role(n,row):
    if n['kind']=='arrays':
        # MDA is a dimensional display class, not a new source port direction.
        # The exact original source role and ordered dimensions remain pinned.
        return row['type']=='MDA' and row['path']==row['meta']
    return row['type'] in ('signal','port') and (n['portnode'] in ('2','3'))==(row['type']=='port')


def binder():
    require(life.digest(frozen.__file__)==FROZEN_SHA,'Frozen binder source drift')
    body=inspect.getsource(frozen.bind_inventory)
    anchor="row['type'] and (n['portnode'] in ('2','3'))==(row['type']=='port')"
    require(body.count(anchor)==1,'Exact role-expression adapter anchor differs')
    environment=dict(vars(frozen),match_label=match_label,native_role=native_role)
    exec(compile(body.replace(anchor,'native_role(n,row)'),__file__,'exec'),environment)
    return environment['bind_inventory']


def alias_proof(instance,text):
    rows=frozen.pack.native.native_rows(text);changes=[]
    for label,row in rows.items():
        matches=[n for n in instance['typed_objects'] if match_label(n,label,row['type']) is not None]
        require(len(matches)==1,'Alias proof identity ambiguous: '+label)
        n=matches[0]
        collapsed=(frozen.match_label(n,label,row['type']) is None)
        mda=n['kind']=='arrays' and row['type']=='MDA'
        if collapsed or mda:
            require(n['name'] not in {t['name'] for t in instance['targets']},'Aliases must never promote target scope')
            changes.append(dict(scope=instance['scope'],name=n['name'],native_label=label,
                native_row=row,compiled_attributes=n,
                reason='EXACT_INTERNAL_VECTOR0_0_BARE_SIGNAL' if collapsed else 'EXACT_ORDERED_ARRAY_MDA_DISPLAY',
                source_role_authority='Pinned compiled portnode; MDA display has no direction column',
                protected=True))
    return changes


def terminal_gate(c,terminal,execution,live,log,properties):
    require(terminal['returncode']==0 and terminal['timeout'] is False and len(terminal['actual_dve'])==1 and
            terminal['actual_dve']==live,'Actual complete readonly native terminal0')
    require(execution['config_seal']==SEAL and execution['cwd']==str(RUN) and execution['timeout_seconds']==5400,
            'Original execution/config identity differs')
    identity=live[0]
    require(identity['exe']==c['identity']['executable'] and identity['cwd']==str(RUN),'Actual executable/cwd differs')
    require(properties.get('Id')==UNIT and properties.get('LoadState')=='loaded' and
            properties.get('ActiveState')==properties.get('SubState')=='failed' and
            properties.get('ExecMainCode')=='1' and properties.get('ExecMainStatus')=='1',
            'Preserve true wrapper failure1; do not substitute unit0')
    require(str(Path(frozen.__file__).resolve()) in properties.get('ExecStart','') and
            str(RUN) in properties['ExecStart'] and SEAL in properties['ExecStart'],'Actual unit command binding')
    require(log.count('Traceback (most recent call last):')==1 and
            log.rstrip().endswith('ValueError: '+ERROR) and 'in bind_inventory' in log and 'in verify' in log,
            'Not the precise readonly binder-only failure')
    return dict(native_launch_returncode=0,wrapper_OS_exit_status=1,systemd_properties=properties,
                original_failure=ERROR,original_failure_preserved=True,EDA_replayed=False)


def verify(out):
    require(out.parent==life.OUT and not out.exists() and out!=RUN,'Fresh independent offline closure only')
    require(not (RUN/'native-binding.json').exists() and not (RUN/'candidate.el').exists(),
            'Original failed binder artifacts must stay absent')
    original={str(p):life.digest(p) for p in RUN.rglob('*') if p.is_file()}
    c=frozen.check(RUN,SEAL)
    fields=subprocess.check_output(['systemctl','--user','show',UNIT,
        '--property=Id,LoadState,ActiveState,SubState,ExecMainCode,ExecMainStatus,ExecMainPID,ExecStart'],text=True)
    properties=dict(line.split('=',1) for line in fields.splitlines())
    terminal=terminal_gate(c,json.loads((RUN/'terminal.json').read_bytes()),
        json.loads((RUN/'execution.json').read_bytes()),json.loads((RUN/'live-identity.json').read_bytes()),
        (RUN/'service.log').read_text(),properties)
    # Replay the original verifier in a private namespace: only the narrow
    # typed matcher and its final output destination change, never old files.
    bound={};alias=[];active_binder=binder()
    def bind(instance,text):
        value=active_binder(instance,text);bound[instance['scope']]=value
        alias.extend(alias_proof(instance,text));return value
    writes={}
    class EvidencePath:
        def __truediv__(self,name):
            return out/name if name in ('candidate.el','native-binding.json') else RUN/name
        def __str__(self):return str(RUN)
    evidence=EvidencePath()
    def checked(path,seal):
        require(path is evidence and seal==SEAL,'Original config binding');return c
    common=frozen.pack.native.primitive.common.common
    def text_save(path,text):
        require(path==out/'candidate.el' and not writes,'Only redirect proposed EL')
        writes['candidate']=text;out.mkdir();common.save(path,text)
    def json_save(path,data):
        require(path==out/'native-binding.json' and 'result' not in writes,'Only redirect completed binding')
        result=copy.deepcopy(data)
        result.update(status='MFPU272_COMPLETE_FRESH_BEFORE_OFFLINE_TYPED_BOUND_NOT_EXCLUSION_QUALIFICATION',
            original_run=str(RUN),typed_aliases=alias,terminal_evidence=terminal,
            original_wrapper_failure_preserved=True,EDA_replayed=False,
            offline_adapter_pins={str(p):life.digest(p) for p in
                (Path(__file__).resolve(),HERE/'test_verify_mfpu272_native_binding_offline.py')})
        result['pins']=life.merge_pins(result['pins'],original)
        life.check(result['pins']);life.check(result['offline_adapter_pins'])
        life.save(path,result);writes['result']=result
    from types import FunctionType,SimpleNamespace
    # Isolated proxies reach the text writer without changing shared modules.
    common_proxy=SimpleNamespace(**dict(vars(common),save=text_save))
    common_parent=SimpleNamespace(**dict(vars(frozen.pack.native.primitive.common),common=common_proxy))
    primitive=SimpleNamespace(**dict(vars(frozen.pack.native.primitive),common=common_parent))
    native=SimpleNamespace(**dict(vars(frozen.pack.native),primitive=primitive))
    pack_proxy=SimpleNamespace(**dict(vars(frozen.pack),native=native))
    namespace=dict(vars(frozen),check=checked,bind_inventory=bind,pack=pack_proxy,
        life=SimpleNamespace(**dict(vars(life),save=json_save)))
    result=FunctionType(frozen.verify.__code__,namespace)(evidence,SEAL)
    expected=copy.deepcopy(result)
    extra_keys={'original_run','typed_aliases','terminal_evidence','original_wrapper_failure_preserved',
                'EDA_replayed','offline_adapter_pins'}
    replay=copy.deepcopy(writes['result'])
    for key in extra_keys:replay.pop(key)
    replay['status']=expected['status'];replay['pins']=expected['pins']
    require(replay==expected and set(writes['result']['pins'])==set(expected['pins'])|set(original),
            'Substantive replay differs outside explicit offline evidence')
    require(len(bound)==788 and sum(len(v['signals']) for v in bound.values())==272,
            'Complete original target/protected binding required')
    life.check(original)
    life.save(out/'closure.json',dict(status='MFPU272_READONLY_CAPTURE_TYPED_ALIAS_OFFLINE_CLOSURE_PASS',
        original_run=str(RUN),original_directory_unchanged=True,original_pins=original,
        binding_sha256=life.digest(out/'native-binding.json'),candidate_sha256=life.digest(out/'candidate.el'),
        targets=272,protected_child_scopes=744,aliases=len(alias),terminal_evidence=terminal,
        local_qualified=False,population_application=False,EDA_launched=False))
    print(json.dumps(dict(output=str(out),binding_seal=life.digest(out/'native-binding.json'),
        closure_seal=life.digest(out/'closure.json'),aliases=len(alias),native_qualification=False,EDA_launched=False)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();verify(a.output.resolve())
