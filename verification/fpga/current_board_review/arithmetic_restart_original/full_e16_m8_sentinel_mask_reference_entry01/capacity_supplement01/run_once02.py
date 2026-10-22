"""One focused rg scan; never hash or fully parse raw a second time."""
import os,resource,shutil,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;R=HERE.parent
sys.path.insert(0,str(R))
from context import artifacts,read,sha,require
from reference02 import durable,verify
from check import validate
def stat(p):
    s=p.stat()
    return dict(device=s.st_dev,inode=s.st_ino,size=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
def main():
    folder=R/'reference01'
    execution=read(folder/'execution.json');audit_execution=read(folder/'audit_execution.json')
    for receipt in (execution,audit_execution):
        require(receipt['actual_wait_returncode']==0 and not receipt['timed_out'],'Successful true terminal before focused exception')
    result=read(folder/'result.json');ready=read(R/'READY.json')
    require(ready['reference_sha256']==sha(folder/'result.json') and result['firmware_to_HTIF']<=3000000
        and ready['firmware']==result['firmware_to_HTIF'],'Actual result and explicit firmware gate')
    inherited=read(folder/'preflight_pins.json');verify(inherited)
    symbols,code,helpers,machine=artifacts();expected=helpers['capacity']
    require(len(expected)==3 and [(x['op'],x['args']) for x in machine.functions['capacity']]==
        [('li','t0,-1'),('vsetvli','a0,t0,e16,m8,tu,mu'),('ret','')],'Actual linked capacity semantics')
    raw=folder/'commits.log';before=stat(raw)
    require(raw.resolve()==raw and before['size']==result['raw_bytes'],'Original closed raw path/size binding')
    executable=Path(shutil.which('rg')).resolve()
    pins=dict(inherited)
    for p in (folder/'result.json',folder/'execution.json',folder/'audit_execution.json',R/'READY.json',
        R/'TERMINAL_QUALIFICATION_HOLD01.json',HERE/'check.py',HERE/'run_once02.py',executable):
        pins[str(p)]=sha(p)
    durable(HERE/'preflight.json',dict(pins=pins,raw_stat=before,
        inherited_raw_sha256=result['raw_sha256'],raw_hash_not_recomputed=True,expected=expected,
        scope='Exactly three capacity PCs only; existing full audit retained with capacity gap'))
    addresses='|'.join(format(x['pc'],'x') for x in expected)
    regex=r'^core[[:space:]]+0:[[:space:]]+[0-9]+[[:space:]]+0x0*('+addresses+r')[[:space:]]+\('
    command=[str(executable),'--no-config','--line-number','--no-heading','--color','never','--no-mmap',
        '--regexp',regex,str(raw)]
    durable(HERE/'command.json',dict(command=command,maximum_output_bytes=65536,timeout_s=120,
        focused_raw_scans=1,no_full_numeric_reparse=True,raw_hash_not_recomputed=True))
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))
    start=time.monotonic();timed=False
    with (HERE/'matched.log').open('x') as f:
        child=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT,preexec_fn=limits)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        durable(HERE/'execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
            elapsed_s=time.monotonic()-start,timed_out=timed,retries=0,validated=False))
    require(rc==0 and not timed,'Actual focused rg outcome')
    require(stat(raw)==before,'Closed raw stat unchanged across focused scan')
    verify(pins);output=HERE/'matched.log'
    require(output.stat().st_size<=65536,'Focused output <=64KiB')
    report=validate(output.read_text(),expected)
    report.update(original_result_sha256=sha(folder/'result.json'),original_READY_sha256=sha(R/'READY.json'),
        raw_sha256_inherited=result['raw_sha256'],raw_stat_before=before,raw_stat_after=stat(raw),
        focused_output_sha256=sha(output),focused_output_bytes=output.stat().st_size,
        actual_rg_execution_sha256=sha(HERE/'execution.json'),pins_pre_post_unchanged=True,
        original_capacity_gap_preserved=True,firmware_to_HTIF=result['firmware_to_HTIF'],
        calls=result['calls'],results=result['results'],guards=result['guards'],vstart_zero=result['vstart_zero'],
        packed_output_reads=result['packed_output_reads'],reference_attempts=1,DUT_runs=0,
        independent_combined_terminal_review_pending=True)
    durable(HERE/'result.json',report);durable(HERE/'postflight.json',dict(pins=pins,raw_stat=stat(raw)))
    print('FOCUSED_CAPACITY_ACCEPTED',sha(HERE/'result.json'),flush=True)
if __name__=='__main__':
    try:main()
    except BaseException as error:
        durable(HERE/'STOPPED.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),
            execution=str(HERE/'execution.json'),no_reference_retry=True));raise
