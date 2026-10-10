"""Replay full766 substantive verification; bind real external stdout, no EDA/writes to capture."""
import argparse
import copy
import inspect
import json
import subprocess
from pathlib import Path
from types import FunctionType, SimpleNamespace

import report_native_batch766 as report
import audit_full766_pmp_annotations as pmp_audit

life,require=report.life,report.require
OUT=life.OUT/'native-batch-full766-agent-20261007-01'
SEAL=pmp_audit.CONFIG_SHA
STDOUT=life.OUT/'native-batch-full766-service-agent-20261007-01.log'
RECEIPT=life.OUT/'native-batch-full766-launch-agent-20261007-01.json'


def evidence(log,failure,live,receipt,body):
    require(failure==dict(reason='Foreground lifecycle stdout missing',no_retry=True),'Not exact stdout-path failure')
    require(receipt['config_seal']==SEAL and receipt['actual_dve_pid']==live['pid'] and
            receipt['actual_cwd']==str(OUT) and live['executable_verified'] is True,
            'Launch receipt/live identity differs')
    require(log.startswith('EXACT742_LIVE pid=%s launch=%s\n'%(live['pid'],live['launch_pid'])) and
            log.count('Traceback (most recent call last):')==1 and
            log.rstrip().endswith('ValueError: Foreground lifecycle stdout missing') and
            'report_fsm_observers742.py", line 37, in run' in log and
            'report_c910_combo742.py", line 214, in verify' in log and
            'snapshot_stdout' in log,'Real stdout does not establish failure boundary')
    require("require(code == 0, 'DVE nonzero exit')\n        verify(out, seal)" in body,
            'Sealed lifecycle zero-return guard differs')
    return dict(source='SEALED_LIFECYCLE_ZERO_RETURN_GUARD_AND_REAL_TRACEBACK',
        launch_process_returncode=0,standalone_DVE_OS_return_receipt_available=False,
        wrapper_failed_at_offline_result_save=True,real_stdout=str(STDOUT),
        copied_or_synthesized_stdout=False)


def verify(destination):
    require(destination.parent==life.OUT and destination!=OUT and not destination.exists(),
            'Fresh independent closure directory only')
    require(not (OUT/'qualification.json').exists(),'Original capture must remain unqualified/frozen')
    failure=json.loads((OUT/'failure.json').read_bytes())
    live=json.loads((OUT/'live-identity.json').read_bytes())
    receipt=json.loads(RECEIPT.read_bytes())
    base=report.old.frozen.prior.old.base
    proof=evidence(STDOUT.read_text(),failure,live,receipt,inspect.getsource(base.run))
    unit=receipt['unit']
    require(unit=='ara-native-batch-full766-agent-20261007-01.service','Wrong actual unit')
    unit_text=subprocess.run(['systemctl','--user','cat',unit],check=True,capture_output=True,text=True).stdout
    require('StandardOutput=append:'+str(STDOUT)+'\n' in unit_text and
            'StandardError=inherit\n' in unit_text and
            '"'+str(Path(report.__file__).resolve())+'" "run" "--output" "'+str(OUT)+'" "--seal" "'+SEAL+'"' in unit_text,
            'Actual systemd stdout/command binding differs')
    unit_status=subprocess.run(['systemctl','--user','show',unit,'--property=ActiveState',
        '--property=SubState','--property=ExecMainStatus','--property=ExecMainCode'],
        check=True,capture_output=True,text=True).stdout
    require('ExecMainStatus=1\n' in unit_status and 'ActiveState=failed\n' in unit_status,
            'Wrapper not terminal at recorded offline failure')
    proof.update(actual_systemd_unit=unit,systemd_cat=unit_text,systemd_show=unit_status,
                 wrapper_OS_exit_status=1)
    before={str(p):life.digest(p) for p in OUT.rglob('*') if p.is_file()}
    external={str(STDOUT):life.digest(STDOUT),str(RECEIPT):life.digest(RECEIPT),
        str(Path(__file__).resolve()):life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_verify_full766_stdout_offline.py')):
            life.digest(Path(__file__).with_name('test_verify_full766_stdout_offline.py')),
        str(Path(pmp_audit.__file__).resolve()):life.digest(Path(pmp_audit.__file__))}
    pmp=pmp_audit.audit(terminal=True)
    destination.mkdir()
    result={}
    def snapshot(data,out):
        require(out==OUT and str(STDOUT) not in data['output_pins'],'Wrong original output/stdout ownership')
        require(data['output_pins']==before,'Frozen output inventory differs before closure')
        data.update(population=766,qualified_fsm_union=173,formal766_manifest_seal=report.MANIFEST_SHA,
            exact765prefix=True,new_observer_objects=1245,pmp_internal_objects=770,
            observer788_capture_seal=report.observers.CAPTURE_SHA,
            cva6observer457_capture_seal=report.observers.CVA6_SHA,pmp_internal_capture_seal=report.PMP_SHA,
            pmp_initial_X_excluded=False,lifecycle_stdout=dict(path=str(STDOUT),sha256=external[str(STDOUT)],
                immutable_terminal_log=True,no_snapshot_copy=True),
            offline_closure='EXTERNAL_SYSTEMD_STDOUT_PATH_ONLY_FULL_SUBSTANTIVE_REPLAY',
            terminal_evidence=proof,main_root_toggle_hit_total=None,
            original_failure_preserved=True,EDA_replayed=False,pmp_strict_annotation_audit=pmp)
    def save(path,data):
        require(path==OUT/'qualification.json' and not result,'Unexpected substantive verifier write')
        result.update(copy.deepcopy(data))
        result['offline_adapter_pins']=external
        life.check(before);life.check(external)
        life.save(destination/'qualification.json',result)
    def digest(path):
        if Path(path)==OUT/'qualification.json':
            require(bool(result),'Unwritten redirected qualification')
            return life.digest(destination/'qualification.json')
        return life.digest(path)
    ns=report.namespace()
    ns.update(snapshot_stdout=snapshot,life=SimpleNamespace(**dict(vars(life),save=save,digest=digest)))
    worker=FunctionType(ns['verify'].__code__,ns)
    worker(OUT,SEAL)
    require(result and result['population']==766 and result['config_seal']==SEAL,
            'Substantive full766 verifier did not reach exact result')
    life.check(before);life.check(external)
    qsha=life.digest(destination/'qualification.json')
    life.save(destination/'closure.json',dict(status='FULL766_FROZEN_CAPTURE_OFFLINE_STDOUT_CLOSURE_PASS',
        source=str(OUT),config_seal=SEAL,qualification_sha256=qsha,
        input_pins=before,external_pins=external,original_failure_preserved=True,
        source_directory_unchanged=True,EDA_launched=False,main_root_toggle_hit_total=None))
    print(json.dumps(dict(status='FULL766_OFFLINE_CLOSURE_PASS',output=str(destination),
        qualification_seal=qsha,closure_seal=life.digest(destination/'closure.json'),system=result['system'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();verify(a.output.resolve())
