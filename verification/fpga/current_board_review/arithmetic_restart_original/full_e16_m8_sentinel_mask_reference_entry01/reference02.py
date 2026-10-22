"""One independently reviewed finite reference, followed by one closed audit."""
from context import *
import argparse,os,resource,subprocess,time
from reference_check02 import audit
ENTRY=HERE/'ENTRY02.json'
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
def durable(path,obj):
    with Path(path).open('x') as f:
        json.dump(obj,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(str(Path(path).parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def verify(pins):
    for path,digest in pins.items():require(sha(path)==digest,'Consumed pin drift '+path)
def child_once(command,log,receipt,seconds,limits=None):
    start=time.monotonic();timed=False
    with log.open('x') as f:
        child=subprocess.Popen(command,cwd=HERE,stdout=f,stderr=subprocess.STDOUT,preexec_fn=limits)
        try:rc=child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        durable(receipt,dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,
            timed_out=timed,retries=0,validated=False))
    require(type(rc)is int and rc==0 and not timed,'Actual child outcome '+str(receipt))
    return rc
def offline():
    folder=HERE/'reference01';pins=read(folder/'preflight_pins.json');verify(pins)
    execution=read(folder/'execution.json')
    require(execution['actual_wait_returncode']==0 and not execution['timed_out'],'Closed successful actual reference only')
    raw=folder/'commits.log';before=raw.stat();digest=sha(raw)
    require(before.st_size<=768*1024**2,'Bounded closed raw')
    report=audit(raw)
    after=raw.stat()
    require((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
        and digest==sha(raw),'Closed raw drift')
    verify(pins)
    report.update(raw_sha256=digest,raw_bytes=after.st_size,pins_pre_post_unchanged=True,
        actual_execution=execution,source_SEW=16,source_LMUL='m8',source_CAP=512,vtype=11,
        physical_registers_each_group=8,checked_output_bytes=1028,tail_read_bytes=4,
        physical_input_bytes_each=2048,upper_predicate_bytes_zero=64,
        firmware_count_basis='EXACT_CLOSED_COMMIT_RETIREMENT_LEDGER_NOT_DEBUG_COUNTER',
        debug_counter_receipt_available=False)
    durable(folder/'result.json',report)
def execute(review_path,review_sha):
    require(review_path and sha(review_path)==review_sha,'Actual independent review hash')
    entry,review=read(ENTRY),read(review_path)
    require(review['status']=='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT'
        and review['entry_sha256']==sha(ENTRY) and review['one_attempt'] is True
        and review['DUT_authorized'] is False,'Actual exact independent entry')
    pins=dict(entry['pins']);pins[str(ENTRY)]=sha(ENTRY);pins[str(review_path.resolve())]=review_sha
    verify(pins);folder=HERE/'reference01';folder.mkdir()
    durable(folder/'preflight_pins.json',pins)
    with (folder/'spike.cmd').open('x') as f:f.write('rs 4000000\nquit\n')
    command=[str(SPIKE),'-d','--debug-cmd='+str(folder/'spike.cmd'),'--isa=rv64gcv_zvl1024b','-m2',
        '--log-commits','--log='+str(folder/'commits.log'),str(ELF)]
    durable(folder/'command.json',dict(command=command,timeout_s=120,max_raw_bytes=768*1024**2,
        hard_steps=4000000,debug_script_sha256=sha(folder/'spike.cmd'),attempt=1,
        review=str(review_path),review_sha256=review_sha,executor_sha256=sha(__file__),
        authorization='Parent conditional task authorization after exact independent ENTRY; not DUT'))
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024**2,768*1024**2))
    try:
        rc=child_once(command,folder/'spike.log',folder/'execution.json',120,limits)
        verify(pins)
        command=[sys.executable,'-B',str(HERE/'reference02.py'),'audit']
        durable(folder/'audit_command.json',dict(command=command,timeout_s=600,attempt=1))
        arc=child_once(command,folder/'audit.log',folder/'audit_execution.json',600)
        report=read(folder/'result.json');verify(pins);within=report['firmware_to_HTIF']<=3000000
        durable(HERE/('READY.json' if within else 'HOLD.json'),dict(
            status='REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT' if within else 'REFERENCE_FULL4095_PASS_HOLD_COST_OVER_3M',
            SEW=16,LMUL='m8',CAP=512,vtype=11,calls=4095,results=2096640,guards=8190,
            returned_vstart_zero=4095,helper_instructions=53235,packed_output_reads=528255,
            checked_bytes_each=1028,firmware=report['firmware_to_HTIF'],firmware_to_exit=report['firmware_to_exit'],actual_reference_rc=rc,actual_audit_rc=arc,
            reference_sha256=sha(folder/'result.json'),entry_sha256=sha(ENTRY),actual_review_sha256=review_sha,
            actual_reference_execution_sha256=sha(folder/'execution.json'),
            actual_audit_execution_sha256=sha(folder/'audit_execution.json'),
            source_pins_pre_post_unchanged=True,reference_attempts=1,DUT_runs=0,
            original_Linux_historical_stall_closed=False,DUT_budget_not_authorized=True))
        print('READY' if within else 'HOLD',report['firmware_to_HTIF'],flush=True)
    except BaseException as error:
        durable(folder/'STOPPED.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),
            numeric_receipts=[str(p) for p in (folder/'execution.json',folder/'audit_execution.json') if p.exists()],
            reference_attempts=1,DUT_runs=0));raise
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('execute','audit'))
    parser.add_argument('--review',type=Path);parser.add_argument('--review-sha');args=parser.parse_args()
    if args.mode=='audit':offline()
    else:execute(args.review,args.review_sha)
