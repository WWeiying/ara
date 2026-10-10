"""Prepare one parent-authorized frozen VALU run; no automatic admission/retry."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import FunctionType

import preflight_valu_restart783 as gold
import run_dtlb_ppn_swap1200 as worker
import run_pure_war_simulation as frozen

life, require = gold.life, gold.require
PRE = gold.OUT/'preflight.json'
PRE_SHA = '30490ac0a6805d6609282162a675bce9557a4a00dfdd997efe59c0f88c6723d9'
CASE = 'valu_restart783_e8m8_12'
OUT = life.OUT/'valu-restart783-old-image-agent-20261008-01'
SERVICE = 'ara-valu-restart783-agent-20261008-01.service'
BUDGET = 900


def command(output):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD='+str(gold.OUT/'input.elf'), '+TESTCASE='+CASE, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'), '+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '+ARA_UVM_TRACE_LIMIT=100000', '+ARA_CONTRACT_TRACE_LIMIT=100000',
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(output/'code.vdb'), '-cm_name', CASE]


def environment():
    env = dict(os.environ)
    # Empty LD entries resolve to the run cwd; pin absolute entries instead.
    env['LD_LIBRARY_PATH'] = ':'.join(dict.fromkeys(str(Path(p).resolve())
        for p in env.get('LD_LIBRARY_PATH', '').split(':') if p))
    require(Path(env.get('VCS_HOME', '')).is_absolute(), 'Absolute existing VCS_HOME required')
    return {k:env[k] for k in ('VCS_HOME','LD_LIBRARY_PATH','SNPSLMD_LICENSE_FILE','LM_LICENSE_FILE') if k in env}


def validate(r):
    out = Path(r['output'])
    require(r['case']==CASE and type(r['timeout_s']) is int and r['timeout_s']==900 and
        r['systemd_runtime_max_s']==960 and r['command']==command(out) and
        r['preflight_seal']==PRE_SHA and r['baseline_seal']==gold.BASE_SHA and
        r['coverage_admitted'] is False and r['automatic_retry'] is False and
        out.parent==life.OUT and out.resolve()==out, 'Exact frozen VALU900 contract')
    import re
    require(re.fullmatch(r'ara-[A-Za-z0-9_.-]+\.service',r['service']), 'Owning service required')
    require(r['environment']==environment(), 'Pinned absolute host environment differs')
    return out


def prepare(output=OUT, service=SERVICE):
    import collect_valu_restart783 as collect
    require(not output.exists() and not output.with_name(output.name+'.prepared.json').exists(), 'Fresh output only')
    q = life.read_bound(PRE,PRE_SHA); life.check(q['pins'])
    require(q['status']=='VALU_RESTART783_SPIKE_FULL_BEFORE_AFTER_VRF_CSR_GUARDS_PASS_NOT_DUT'
        and q['software_checks']==13144 and q['counts']['matched_instructions']==170167
        and q['VCS_launched'] is False and q['coverage_admitted'] is False, 'Frozen full preflight required')
    binding,pins = gold.binding783()
    require(binding==q['baseline'], 'Exact783 target binding')
    image = life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE) and
        image['image'][str(life.IMAGE)]==frozen.IMAGE_SEAL, 'Frozen66 image')
    pins = life.merge_pins(pins,q['pins'])
    pins = life.merge_pins(pins,image['image'])
    pins = life.merge_pins(pins,{str(PRE):PRE_SHA,str(life.PLAN):life.PLAN_SEAL})
    files = [Path(__file__).resolve(),Path(collect.__file__).resolve(),
        Path(__file__).with_name('test_run_valu_restart783.py'),
        Path(__file__).with_name('test_collect_valu_restart783.py')]
    for module in tuple(sys.modules.values()):
        p = getattr(module,'__file__',None)
        if p and str(life.ROOT/'verification') in p and Path(p).is_file(): files.append(Path(p).resolve())
    pins = life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    r = dict(case=CASE,output=str(output),command=command(output),pins=pins,preflight=q,
        preflight_seal=PRE_SHA,baseline_seal=gold.BASE_SHA,baseline=783,timeout_s=900,
        systemd_runtime_max_s=960,service=service,environment=environment(),
        automatic_retry=False,coverage_admitted=False,qualification_automatic=False,
        ELF_sha256=life.digest(gold.OUT/'input.elf'),image_sha256=frozen.IMAGE_SEAL,
        authorization='SEPARATE_PARENT_AUTHORIZATION_REQUIRED',no_FSDB=True,RTL_changed=False,
        budget_estimate='170167 reference retires; 900s bound, not a guaranteed completion prediction',
        candidate_positions_upper_bound_only=422,official_percentage=False)
    validate(r); path=output.with_name(output.name+'.prepared.json');life.save(path,r)
    print(json.dumps(dict(prepared=str(path),seal=life.digest(path),pins=len(pins),EDA_launched=False)))


def check(path,seal):
    r=life.read_bound(path,seal);validate(r);life.check(r['pins']);return r


def run(path,seal):
    r=check(path,seal);output=validate(r);require(not output.exists(),'No repeat run')
    pins=life.merge_pins(r['pins'],{str(path):seal});actual=dict(r,pins=pins)
    output.mkdir();life.save(output/'manifest.json',actual)
    child=None;start=time.monotonic();timed_out=False
    try:
        with (output/'console.log').open('x') as log:
            child=subprocess.Popen(r['command'],cwd=output,stdout=log,stderr=subprocess.STDOUT,
                start_new_session=True,env=dict(os.environ,**r['environment']))
            identity=FunctionType(worker.process_identity.__code__,dict(vars(worker),command=command))(
                child.pid,output,r['image_sha256'],r['service'])
            life.save(output/'live-simv-identity.json',identity)
            try: rc=child.wait(timeout=BUDGET)
            except subprocess.TimeoutExpired: timed_out=True;raise
        require(type(rc) is int and rc==0,'Nonzero simulator exit');life.check(pins)
        life.save(output/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=rc,timeout=False,elapsed_s=time.monotonic()-start,case=CASE,coverage_admitted=False))
    except BaseException as error:
        if child is not None and child.poll() is None:
            try: os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait()
        life.save(output/'simulation-status.json',dict(status='SIMULATION_FAILED_NOT_ADMITTED',
            returncode=None if child is None else child.returncode,timeout=timed_out,
            reason=str(error),elapsed_s=time.monotonic()-start,coverage_admitted=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','check','run'))
    p.add_argument('--output',type=Path,default=OUT);p.add_argument('--input',type=Path)
    p.add_argument('--seal');p.add_argument('--service',default=SERVICE);p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();require((a.mode=='run')==a.parent_authorized,'Run needs separate parent authorization')
    if a.mode=='prepare':prepare(a.output.absolute(),a.service)
    else:
        require(a.input is not None and a.seal is not None,'Prepared input/seal required')
        if a.mode=='check':check(a.input.absolute(),a.seal);print('CHECK_PASS_NO_EDA')
        else:run(a.input.absolute(),a.seal)
