#!/usr/bin/env python3
"""Two original130-call prefixes only; original682 remains an explicit hold."""
import argparse
import copy
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import prepare_m4_plan as prior
from recover import HERE, read, save, sha

OLD=HERE/'candidate04_plan03'
OLD_SHA='f503af9bfac573987090e3ac1eea08f10f8e7768e390c757ea4e5095769caed6'
PLAN=HERE/'candidate04_restart_plan05'
RUN=HERE/'candidate04_restart_run01'
NAMES={'restart_e16m2_prefix130','restart_unmasked_e16m2_prefix130'}
QUOTAS={'whole':6,'nf7':2,'nf8':8,'prefix5':2,'fp':2}
GATHER=HERE.parent/'gather_original_review/remainder75_01/vcs_candidate04_01'


def require(ok,message):
    if not ok:raise ValueError(message)


def identity():
    require(sha(prior.IMAGE/'image.json')==prior.IMAGE_SHA,'Wrong M4 image')
    ledger=read(prior.IMAGE/'image.json'); snap=Path(ledger['snapshot'])
    require(sha(snap/'snapshot.json')==ledger['snapshot_sha256'],'Snapshot drift')
    repo=prior.shared.sealed(snap); framework=prior.shared.framework(repo)
    simv=Path(ledger['simv'])
    require(framework[3](simv)==ledger['files'],'Image drift')
    manifest=simv.parent/'vcs_source_manifest.json'
    require(sha(manifest)==ledger['manifest_sha256'] and
            sha(simv.parent/'simulator.conf')==ledger['configuration_sha256'],'Image metadata drift')
    from ara_verify.vcs_source_manifest import collect
    captured=read(manifest)
    require(collect(Path(captured['filelist']),repo,[Path(p) for p in captured['extra_sources']])==captured['files'],'Compiled sources drift')
    import ara_verify.runner as engine
    require(Path(engine.__file__).is_relative_to(repo),'Runner is not frozen M4')
    return ledger,repo,framework,engine


def contract(data):
    require(data['jobs']==2 and data['stop_first_fail'] and data['no_build'],'Execution contract')
    require(len(data['cases'])==2 and {c['id'] for c in data['cases']}==NAMES,'Only exact two prefixes allowed')
    require(all(c['calls']==130 and c['timeout_s']==3600 for c in data['cases']),'Original count or budget changed')
    old=read(OLD/'plan.json')
    require(data['cases']==[c for c in old['cases'] if c['id'] in NAMES],'ELF/oracle/trace target drift')
    require(data['held_cases']==[dict(status='HOLD_NOT_RUN',case=c) for c in old['cases'] if c['id'] not in NAMES],
            '682 scope must remain unchanged and held')


def resource_math(live,available,units):
    require(set(units)==set(QUOTAS)|{'gather','final38'} and len(set(units.values()))==7,'Exact distinct units required')
    require(all(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service',u) for u in units.values()),'Invalid service unit')
    counts={name:0 for name in units}; unknown=[]
    for process in live:
        parts={s for line in process['cgroup'].splitlines() for s in line.split('/')}
        owners=[name for name,unit in units.items() if unit in parts]
        require(len(owners)<=1,'Ambiguous nested ownership')
        if owners:counts[owners[0]]+=1
        else:unknown.append(process)
    total=sum(max(n,counts[name]) for name,n in QUOTAS.items())+len(unknown)
    require(not counts['gather'] and not counts['final38'],'Gather/38 workers still live')
    require(counts['fp']<=2 and total<=24 and available>=32*1024**3,'Resource admission failed; no retry')
    return dict(counts=counts,unknown=unknown,quotas=QUOTAS,total_live_plus_reserved=total,
                mem_available_bytes=available,cap=24,own_slots=2)


def resources(units):
    live=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if (proc/'comm').read_text().strip()!='simv':continue
            live.append(dict(pid=int(proc.name),cgroup=(proc/'cgroup').read_text(),
                             argv=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()))
        except (FileNotFoundError,ProcessLookupError):continue
    available=int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')))*1024
    return dict(time=time.time(),**resource_math(live,available,units))


def gates(review,plan_sha):
    require(review.get('parent_authorized') is True and review.get('plan_sha256')==plan_sha and
            review.get('image_sha256')==prior.IMAGE_SHA and review.get('jobs')==2,'Parent approval missing/wrong')
    require(review.get('old38_reservation_accounting_confirmed') is True,'Reservation coordination not confirmed')
    evidence=review['evidence']; records={}
    expected={'final38_terminal':prior.FINAL38/'complete.json','gather_terminal':GATHER/'complete.json',
              'gather_worker_exit':GATHER/'worker_exit.json'}
    require(set(evidence)==set(expected)|{'nf8_initial_admission'},'All gate evidence required')
    for name,entry in evidence.items():
        path=Path(entry['path']).resolve()
        require(name not in expected or path==expected[name],'Wrong terminal evidence path')
        require(sha(path)==entry['sha256'],'Evidence changed: '+name)
        records[name]=read(path)
    final_plan=read(prior.FINAL38/'plan.json')
    require(prior.completed38(final_plan,records['final38_terminal']) and
            records['final38_terminal']['plan_sha256']==sha(prior.FINAL38/'plan.json'),'38 is not exact terminal PASS')
    gather=records['gather_terminal']; worker=records['gather_worker_exit']
    require(gather['status'] in ('PASS_8_ACCEPTED_PLUS_75_SOURCE_SINGLES_CANDIDATE04','NOT_ACCEPTED') and
            gather.get('finished',0)>0 and worker.get('finished',0)>0 and
            gather['plan_sha256']==worker['plan_sha256'],'Gather75 is not terminal; admission is insufficient')
    # A failed Gather terminal only releases scheduling; it is not arithmetic acceptance.
    nf8=records['nf8_initial_admission']; ng=nf8['gate']
    require(nf8['jobs']==8 and nf8['reserved_through_pilot']==8 and nf8['start_unix']>0 and
            ng['own_reserved']==8 and ng['cap']==24 and ng['total_live_plus_reserved']<=24 and
            ng['mem_available_bytes']>=32*1024**3,'NF8 initial admission not established')
    units=review['units']
    require(ng['units']=={n:units[{'parent38':'final38','nf7':'nf7','gather':'gather','whole':'whole'}[n]]
                        for n in ('parent38','nf7','gather','whole')},'Units differ from actual NF8 admission')
    for name in ('gather','final38'):
        state=subprocess.check_output(['systemctl','--user','show',units[name],'-p','ActiveState','--value'],text=True).strip()
        require(state in ('inactive','failed'),'Service still active: '+name)
    return records


def execute(data,out,dry_run,units=None):
    contract(data)
    ledger,repo,(parent,options,case,_),engine=identity()
    entries={c['id']:c for c in data['cases']}
    engine.FAIL_RE=re.compile(engine.FAIL_RE.pattern+'|'+prior.BAD.pattern,engine.FAIL_RE.flags)
    checked=prior.runner_class(parent,entries)
    class Admitted(checked):
        def _run_test(self,test,image):
            try:
                if not dry_run and not self.cancel_event.is_set():
                    save(out.parent/'admission'/f'{test.name}.json',resources(units))
                return super()._run_test(test,image)
            except BaseException:
                self.cancel_event.set(); raise
    tests=[case(c['id'],'app','',Path(c['elf']),c['id'],c['timeout_s']) for c in data['cases']]
    opts=options(repo,out,'default',2,1,dry_run,False,True,Path(ledger['simv']),True,None)
    return Admitted(opts,tests,sys.argv).run()


def prepare():
    require(sha(OLD/'plan.json')==OLD_SHA,'Sealed03 changed')
    old=read(OLD/'plan.json'); prior.shared_adapter.verify(old['pins'])
    PLAN.mkdir(exist_ok=False)
    inherited=prior.self_test(); require(len(inherited)==27,'Inherited host27 changed')
    import unittest
    import test_restart_successor as tests
    with (PLAN/'successor_tests.log').open('x') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    require(result.wasSuccessful(),'Successor host gate failed')
    save(PLAN/'host_gate.json',dict(status='PASS',inherited_count=27,inherited_checks=inherited,
        successor_count=result.testsRun,successor_tests_log_sha256=sha(PLAN/'successor_tests.log')))
    data=copy.deepcopy(old)
    data.update(status='PREPARED_NOT_AUTHORIZED',scope='Two original130-call prefixes (260 calls);682 held, never942 DUT PASS',
        cases=[c for c in old['cases'] if c['id'] in NAMES],
        held_cases=[dict(status='HOLD_NOT_RUN',case=c) for c in old['cases'] if c['id'] not in NAMES],
        launch_entrypoint_present=True,predecessor_plan=str(OLD/'plan.json'),predecessor_sha256=OLD_SHA,
        output=str(RUN),budget=dict(inner_each_s=3600,inner_sum_s=7200,jobs=2,outer_s=4500,
            basis='Unchanged plan03 budgets. Outer leaves900s beyond concurrent3600s for setup, trace checks and teardown.',
            held682='Not scheduled; after both PASS, measured throughput may inform a separately reviewed long-case plan.'))
    data['gates']['require_explicit_long_budget_approval']=False
    data['gates']['held682_requires_separate_plan_and_approval']=True
    for p in (Path(__file__),HERE/'test_restart_successor.py',OLD/'plan.json',PLAN/'host_gate.json',PLAN/'successor_tests.log'):
        data['pins'][str(p.resolve())]=sha(p)
    contract(data); save(PLAN/'plan.json',data)
    rows=execute(data,PLAN/'dryrun',True)
    require(len(rows)==2 and {r.name for r in rows}==NAMES and all(r.status=='DRY_RUN' for r in rows),'Dryrun scope differs')
    prior.shared_adapter.verify(data['pins'])
    digest=sha(PLAN/'plan.json')
    save(PLAN/'preflight.json',dict(status='READY_2_PREFIXES_682_HOLD_NOT_LAUNCHED',plan_sha256=digest,
        host27_pass=True,dryrun_names=[r.name for r in rows],pins_unchanged=True,pin_count=len(data['pins']),
        gates_polled=False,VCS_started=False))
    save(PLAN/'review.template.json',dict(parent_authorized=False,plan_sha256=digest,image_sha256=prior.IMAGE_SHA,jobs=2,
        old38_reservation_accounting_confirmed=False,
        units={n:'PARENT_SUPPLY_SERVICE_UNIT' for n in (*QUOTAS,'gather','final38')},
        evidence={n:dict(path=str(p),sha256='PARENT_PIN_TERMINAL_HASH') for n,p in
            [('final38_terminal',prior.FINAL38/'complete.json'),('gather_terminal',GATHER/'complete.json'),
             ('gather_worker_exit',GATHER/'worker_exit.json'),('nf8_initial_admission',Path('PARENT_SUPPLY_NF8_WORKER_JSON'))]}))
    print('READY_NOT_LAUNCHED',digest,flush=True)


def work(approved,review_path,review_hash,authorized):
    require(authorized and approved==sha(PLAN/'plan.json'),'Explicit approved plan hash required')
    require(review_path is not None and review_hash==sha(review_path),'Explicit pinned parent review required')
    require(not RUN.exists(),'Fresh run only; no retry')
    data=read(PLAN/'plan.json'); contract(data); prior.shared_adapter.verify(data['pins'])
    review=read(review_path); evidence=gates(review,approved)
    admission=resources(review['units']); identity()
    RUN.mkdir(); (RUN/'admission').mkdir()
    save(RUN/'launch.json',dict(pid=os.getpid(),time=time.time(),plan_sha256=approved,
        review_path=str(review_path),review_sha256=review_hash,gate_records=evidence,admission=admission))
    try:
        results=execute(data,RUN/'replay',False,review['units'])
        prior.shared_adapter.verify(data['pins']); identity()
        require(sha(PLAN/'plan.json')==approved,'Approved plan changed during replay')
        require(sha(review_path)==review_hash,'Review changed during replay')
        require(all(sha(Path(x['path']))==x['sha256'] for x in review['evidence'].values()),'Gate evidence changed')
        passed=len(results)==2 and {r.name for r in results}==NAMES and all(r.status=='PASS' and r.returncode==0 for r in results)
        calibration=[]
        if passed:
            for r in results:
                trace=read(r.artifact_dir/'architectural_trace_audit.json')
                calibration.append(dict(name=r.name,elapsed_s=r.elapsed_s,**trace,
                    retired_per_s=trace['retired']/r.elapsed_s,cycles_per_s=trace['last_cycle']/r.elapsed_s))
        save(RUN/'complete.json',dict(status='PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4' if passed else 'NOT_PASS',
            plan_sha256=approved,pins_unchanged=True,results=[dict(name=r.name,status=r.status,returncode=r.returncode,
                elapsed_s=r.elapsed_s,reason=r.reason,artifact_dir=str(r.artifact_dir)) for r in results],
            calibration=calibration,held682='HOLD_NOT_RUN',full942_dut_pass=False,finished=time.time()))
        return int(not passed)
    except BaseException as error:
        save(RUN/'complete.json',dict(status='ERROR_NOT_PASS',error=str(error),held682='HOLD_NOT_RUN',finished=time.time()))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','work'])
    parser.add_argument('--authorize-run',action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--review',type=Path)
    parser.add_argument('--review-sha256')
    args=parser.parse_args()
    env=prior.shared.environment()
    os.environ.clear(); os.environ.update(env)
    if args.mode=='prepare':prepare()
    else:raise SystemExit(work(args.approved_plan_sha256,args.review,args.review_sha256,args.authorize_run))
