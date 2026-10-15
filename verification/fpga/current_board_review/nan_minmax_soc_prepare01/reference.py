"""Exactly one bounded Spike attempt per fresh case, sequential first-error stop."""
import argparse
import resource
import subprocess
import time
import traceback
from common import *
from check_reference import extract, specification, validate, host_negatives
from test_raw import run as raw_negatives


def prepare():
    require(read(HERE/'host03.json')['status']=='PASS_HOST_ONLY','host preflight')
    require(read(HERE/'oracle_host01.json')['status']=='PASS_HOST_ONLY','independent bitwise host gate')
    require(read(HERE/'static_admission.json')['status']=='STATIC_ADMITTED_TWO_SINGLES_NOT_REFERENCE_PASS','static cost gate')
    commonpins={str(p):sha(p) for p in HERE.iterdir() if p.is_file()}
    for shape in SHAPES:
        dest=HERE/shape
        proof=read(dest/'sourceproof.json')
        pins=dict(proof['external_pins']);pins.update(commonpins)
        pins.update({str(p):sha(p) for p in dest.rglob('*') if p.is_file()})
        checkpins(pins)
        ref=dest/'reference01';ref.mkdir()
        sy=read(dest/'spike/symbols.json')
        (ref/'spike.cmd').write_text(f"rs {LIMITS['steps']}\nstr {sy['replay_log']:x}\nquit\n")
        pins[str(ref/'spike.cmd')]=sha(ref/'spike.cmd')
        command=[str(SPIKE),'-d','--debug-cmd='+str(ref/'spike.cmd'),'--isa='+ISA,'-m2',
                 '--log-commits','--log='+str(ref/'commits.log'),str(dest/'spike/program.elf')]
        save(ref/'admission.json',{'status':'AUTHORIZED_ONE_REFERENCE_ONLY','limits':LIMITS,'profile':ISA,
             'command':command,'pins':pins,'scope':proof['scope'],
             'authority':'User authorized two authentic single software/Spike preparations, no VCS, 3M/256MiB/120s, once per ELF after static cost',
             'static_upper':read(dest/'static_cost.json')['upper_instructions'],'retries':0})
        save(ref/'admission.pin.json',{'sha256':sha(ref/'admission.json')})
    save(HERE/'reference_plan.json',{'status':'PREPARED_NOT_RUN','shapes':SHAPES,'jobs':1,
         'stop_first_error':True,'profile':ISA,'limits_per_case':LIMITS,
         'admissions':{str(HERE/s/'reference01/admission.json'):sha(HERE/s/'reference01/admission.json') for s in SHAPES}})


def run_case(shape):
    dest=HERE/shape;ref=dest/'reference01'
    a=read(ref/'admission.json');digest=sha(ref/'admission.json')
    require(digest==read(ref/'admission.pin.json')['sha256'],'admission drift')
    require(a['limits']==LIMITS and a['profile']==ISA,'bounds/profile drift')
    checkpins(a['pins'])
    save(ref/'ATTEMPT_STARTED.json',{'time':time.time(),'admission_sha256':digest})
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(LIMITS['raw_bytes'],LIMITS['raw_bytes']))
    start=time.monotonic();rc=None;error=None
    with (ref/'spike.log').open('x') as stream:
        try:
            p=subprocess.run(a['command'],stdout=stream,stderr=subprocess.STDOUT,timeout=120,preexec_fn=limits)
            rc=p.returncode
        except subprocess.TimeoutExpired as failure:
            rc=failure.returncode if hasattr(failure,'returncode') else None
            error='WALL_BOUND_120_SECONDS'
    elapsed=time.monotonic()-start
    save(ref/'actual_exit_unvalidated.json',{'returncode':rc,'timed_out':error is not None,'error':error,
        'elapsed_s':elapsed,'admission_sha256':digest,'validated':False})
    execution={'returncode':rc,'error':error,'elapsed_s':elapsed,'profile':ISA,'admission_sha256':digest,
        'raw':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in (ref/'commits.log',ref/'spike.log') if p.exists()}}
    save(ref/'execution.json',execution)
    require(rc==0 and error is None and elapsed<120,'reference execution did not complete within bound; no retry')
    require(all(v['bytes']<=LIMITS['raw_bytes'] for v in execution['raw'].values()),'raw bound')
    checkpins(a['pins'])
    data=extract(dest,ref/'commits.log');save(ref/'ledger.json',data)
    s=specification(dest);validate(s,data)
    require(data['terminal']['firmware_retired']<a['static_upper'],'measured exceeds static admission')
    save(ref/'checker_host.json',host_negatives(s,data))
    save(ref/'raw_host01.json',raw_negatives(dest,ref/'commits.log'))
    (ref/'console.log').write_text(data['console'])
    checkpins(a['pins'])
    save(ref/'result.json',{'status':'EXECUTOR_REFERENCE_PASS_PENDING_INDEPENDENT_REVIEW',
         'shape':shape,'target_calls':1,'helper_instructions':21,'original_oracle_bytes':144,
         'fixture_fields':6720,'flags':0,'vstart':0,'result':hex(s['config']['expected']),
         'firmware_retired':data['terminal']['firmware_retired'],'retired_total':data['retired_total'],
         'parking_retired':data['parking_retired'],'elapsed_s':elapsed,
         'raw_bytes':execution['raw']['commits.log']['bytes'],'pins_unchanged':True,
         'DUT_run':False,'Linux_run':False,'full6720_accepted':False})
    pins=dict(a['pins']);pins.update({str(p):sha(p) for p in ref.iterdir() if p.is_file()})
    save(dest/'READY.json',{'status':'SOURCE_REFERENCE_READY_PENDING_INDEPENDENT_REVIEW',
        'shape':shape,'soc_elf':str(dest/'soc/program.elf'),'soc_sha256':sha(dest/'soc/program.elf'),
        'spike_sha256':sha(dest/'spike/program.elf'),'reference_result':read(ref/'result.json'),'pins':pins})
    print(shape,'REFERENCE_EXECUTOR_PASS',data['terminal']['firmware_retired'],round(elapsed,3),flush=True)


def run():
    plan=read(HERE/'reference_plan.json');checkpins(plan['admissions'])
    save(HERE/'BATCH_ATTEMPT_STARTED.json',{'time':time.time(),'plan_sha256':sha(HERE/'reference_plan.json')})
    completed=[]
    for shape in SHAPES:
        try:run_case(shape)
        except BaseException as e:
            save(HERE/'STOPPED.json',{'status':'STOPPED_FIRST_ERROR_NO_RETRY','case':shape,
                 'completed':completed,'not_dispatched':SHAPES[SHAPES.index(shape)+1:],
                 'error':repr(e),'traceback':traceback.format_exc()})
            raise
        completed.append(shape)
    save(HERE/'READY.json',{'status':'TWO_SINGLE_EXECUTOR_REFERENCE_PASS_PENDING_INDEPENDENT_REVIEW',
         'shapes':SHAPES,'same_original_single_scope':True,'DUT_run':False,'no_retry':True,
         'case_ready_pins':{str(HERE/s/'READY.json'):sha(HERE/s/'READY.json') for s in SHAPES},
         'results':[read(HERE/s/'reference01/result.json') for s in SHAPES]})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);a=p.parse_args()
    prepare() if a.action=='prepare' else run()

