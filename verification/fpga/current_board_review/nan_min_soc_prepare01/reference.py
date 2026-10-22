"""Once per original MIN single, bounded Spike and one full oracle extraction."""
import argparse
import resource
import subprocess
import time
import traceback
from common import *


def durable(path, value):
    import os
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')
        stream.flush();os.fsync(stream.fileno())


def prepare():
    require(read(HERE/'host03.json')['status']=='PASS_HOST_ONLY','compiled Host gate')
    require(read(HERE/'oracle_host01.json')['status']=='PASS_HOST_ONLY','independent MIN oracle gate')
    require(read(HERE/'csr_host01.json')['status']=='PASS_HOST_ONLY_NOT_RAW_ACCEPTANCE','CSR chain Host gate')
    require(read(HERE/'static_admission.json')['status']=='STATIC_ADMITTED_TWO_SINGLES_NOT_REFERENCE_PASS','static admission')
    inherited=read(HERE/'lineage.json')['sealed_MAX_pins']
    checkpins(inherited)
    commonpins={str(p):sha(p) for p in HERE.iterdir() if p.is_file()}
    for shape in SHAPES:
        dest=HERE/shape;proof=read(dest/'sourceproof.json')
        pins=dict(proof['external_pins']);pins.update(inherited);pins.update(commonpins)
        pins.update({str(p):sha(p) for p in dest.rglob('*') if p.is_file()})
        checkpins(pins)
        ref=dest/'reference01';ref.mkdir()
        sy=read(dest/'spike/symbols.json')
        (ref/'spike.cmd').write_text(f"rs {LIMITS['steps']}\nstr {sy['replay_log']:x}\nquit\n")
        pins[str(ref/'spike.cmd')]=sha(ref/'spike.cmd')
        command=[str(SPIKE),'-d','--debug-cmd='+str(ref/'spike.cmd'),'--isa='+ISA,'-m2',
                 '--log-commits','--log='+str(ref/'commits.log'),str(dest/'spike/program.elf')]
        durable(ref/'admission.json',dict(status='AUTHORIZED_ONE_MIN_REFERENCE_ONLY',limits=LIMITS,
            profile=ISA,command=command,pins=pins,scope=proof['scope'],
            authority='User explicitly authorized call1292/1232 once each, no DUT/RTL build',
            static_upper=read(dest/'static_cost.json')['upper_instructions'],retries=0))
        durable(ref/'admission.pin.json',dict(sha256=sha(ref/'admission.json')))
    durable(HERE/'reference_plan.json',dict(status='PREPARED_NOT_RUN',shapes=SHAPES,jobs=1,
        stop_first_error=True,limits_per_case=LIMITS,
        admissions={str(HERE/s/'reference01/admission.json'):sha(HERE/s/'reference01/admission.json') for s in SHAPES}))


def wait_once(command, log, receipt, timeout, spike=False):
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(LIMITS['raw_bytes'],LIMITS['raw_bytes']))
    start=time.monotonic();timed_out=False
    with log.open('x') as stream:
        child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,
                               preexec_fn=limits if spike else None)
        try: code=child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;child.kill();code=child.wait()
        durable(receipt,dict(returncode=code,child_pid=child.pid,elapsed_s=time.monotonic()-start,
            timed_out=timed_out,validated=False,command=command))
    require(code==0 and not timed_out,'actual child exit/timeout failed: stop without retry')
    return read(receipt)


def run_case(shape):
    dest=HERE/shape;ref=dest/'reference01';a=read(ref/'admission.json')
    require(sha(ref/'admission.json')==read(ref/'admission.pin.json')['sha256'],'admission pin')
    require(a['limits']==LIMITS and a['profile']==ISA,'resource/profile identity')
    checkpins(a['pins']);durable(ref/'pins_pre.json',a['pins'])
    durable(ref/'ATTEMPT_STARTED.json',dict(admission_sha256=sha(ref/'admission.json'),
                                          time=time.time(),retries=0))
    e=wait_once(a['command'],ref/'spike.log',ref/'actual_exit_unvalidated.json',120,True)
    raw={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in (ref/'commits.log',ref/'spike.log')}
    durable(ref/'execution.json',dict(actual=e,raw=raw,validated=False))
    require(e['elapsed_s']<120 and all(v['bytes']<=LIMITS['raw_bytes'] for v in raw.values()),'resource limits')
    checkpins(a['pins'])
    command=[sys.executable,'-B',str(HERE/'parse_reference.py'),shape]
    durable(ref/'parser_command.json',command)
    wait_once(command,ref/'parser.log',ref/'parser_actual_exit_unvalidated.json',120)
    result=read(ref/'architectural_result.json')
    checkpins(a['pins']);durable(ref/'pins_post.json',{p:sha(p) for p in a['pins']})
    require(read(ref/'pins_pre.json')==read(ref/'pins_post.json'),'pre/post pins')
    require(result['raw_sha256']==raw['commits.log']['sha256'],'parser/runner raw identity')
    durable(dest/'READY.json',dict(status='MIN_SOURCE_SINGLE_REFERENCE_READY_PENDING_INDEPENDENT_REVIEW',
        shape=shape,soc_elf=str(dest/'soc/program.elf'),soc_sha256=sha(dest/'soc/program.elf'),
        spike_sha256=sha(dest/'spike/program.elf'),reference_result=result,
        actual_spike_exit=e,actual_parser_exit=read(ref/'parser_actual_exit_unvalidated.json'),
        pins={**a['pins'],**{str(p):sha(p) for p in ref.iterdir() if p.is_file()}}))
    print(shape,'MIN_REFERENCE_EXECUTOR_PASS',result['firmware_retired'],flush=True)


def run():
    plan=read(HERE/'reference_plan.json');checkpins(plan['admissions'])
    durable(HERE/'BATCH_ATTEMPT_STARTED.json',dict(time=time.time(),plan_sha256=sha(HERE/'reference_plan.json')))
    completed=[]
    for shape in SHAPES:
        try: run_case(shape)
        except BaseException as error:
            durable(HERE/'STOPPED.json',dict(status='STOPPED_FIRST_ERROR_NO_RETRY',case=shape,
                completed=completed,not_dispatched=SHAPES[SHAPES.index(shape)+1:],
                error=repr(error),traceback=traceback.format_exc()))
            raise
        completed.append(shape)
    checkpins(read(HERE/'lineage.json')['sealed_MAX_pins'])
    durable(HERE/'READY.json',dict(status='TWO_MIN_SOURCE_SINGLE_REFERENCES_READY_PENDING_INDEPENDENT_MAIN_REVIEW',
        shapes=SHAPES,operation='MIN_OP1_NOT_MAX',results=[read(HERE/s/'READY.json')['reference_result'] for s in SHAPES],
        case_ready_pins={str(HERE/s/'READY.json'):sha(HERE/s/'READY.json') for s in SHAPES},
        sealed_MAX_pins_unchanged=True,no_retry=True,DUT_run=False,RTL_image_build=False,
        full_parent_accepted=False,preceding_helper_prefix_accepted=False))
    print('READY',sha(HERE/'READY.json'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run'])
    args=p.parse_args();prepare() if args.action=='prepare' else run()
