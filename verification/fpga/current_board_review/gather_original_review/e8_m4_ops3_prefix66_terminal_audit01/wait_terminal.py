"""One authorized event wait, then one conditional offline audit child; no polling."""
import argparse
import ctypes
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode=True
from support import *


def worker_identity():
    proc=Path('/proc')/str(WORKER_PID)
    try:
        cmd=(proc/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        stat=(proc/'stat').read_text();ticks=stat[stat.rfind(')')+2:].split()[19]
        cg=(proc/'cgroup').read_text()
    except (FileNotFoundError,ProcessLookupError):
        return dict(pid=WORKER_PID,state='ABSENT_EXIT_UNKNOWN')
    launch=read(P/'launch.json')
    require(str(W/'replay.py') in cmd and str(P) in cmd and PLAN_SHA in cmd and AUTH_SHA in cmd,
            'Known worker command identity differs')
    require(launch['owner']['properties']['ControlGroup'] in [s.split(':',2)[-1] for s in cg.splitlines()],
            'Known worker cgroup differs')
    return dict(pid=WORKER_PID,state='LIVE_IDENTITY_ONLY_NOT_EXIT0',start_ticks=ticks,argv=cmd,cgroup=cg)


def stop_audit(child):
    try:os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    return child.wait()


def wait_event(prepared,out):
    libc=ctypes.CDLL(None,use_errno=True)
    libc.inotify_init1.argtypes=[ctypes.c_int]
    libc.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
    fd=libc.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
    require(fd>=0,'Cannot install terminal event watch')
    pidfd=None
    try:
        require(libc.inotify_add_watch(fd,os.fsencode(P),0x8|0x80|0x100|0x400|0x800)>=0,
                'Cannot watch actual output directory')
        try:pidfd=os.pidfd_open(WORKER_PID)
        except ProcessLookupError:pass
        identity=worker_identity()
        if identity['state'].startswith('LIVE'):
            original=prepared['worker_identity']
            require(pidfd is not None and original['state'].startswith('LIVE') and
                    identity['start_ticks']==original['start_ticks'],'Known worker PID generation differs')
        else:
            if pidfd is not None:os.close(pidfd);pidfd=None
        save(out/'wait_started.json',dict(pid=os.getpid(),worker=identity,started=time.time(),
            mechanism='inotify_and_pidfd_blocking_select_no_periodic_poll',worker_exit_status='UNKNOWN'))
        ended=pidfd is None
        deadline=time.monotonic()+prepared['wait_seconds']
        while True:
            # Checked only initially and after filesystem/process events, never on an interval.
            exists=(P/'complete.json').is_file()
            if ended:
                require(exists,'Observed worker ended with no complete publication; no audit')
                break
            left=deadline-time.monotonic();require(left>0,'Bounded event wait expired')
            ready,_,_=select.select([fd,pidfd],[],[],left)
            require(ready,'Bounded event wait expired')
            if fd in ready:
                data=os.read(fd,65536);offset=0
                while offset<len(data):
                    _,mask,_,size=struct.unpack_from('iIII',data,offset);offset+=16+size
                    require(not mask&(0x400|0x800|0x4000|0x8000),'Watch lost/overflow; no audit')
            if pidfd in ready:
                ended=True;os.close(pidfd);pidfd=None
        _,_,digest=terminal_gate()
        save(out/'admission.json',dict(status='FULL_TERMINAL_METADATA_ADMITTED_NOT_AUDIT_PASS',
            complete_sha256=digest,worker_lifetime_ended_or_absent=True,
            worker_numeric_exit_inferred=False,outer_service_exit_inferred=False,monitor_returncode=0))
        return digest
    finally:
        os.close(fd)
        if pidfd is not None:os.close(pidfd)


def run(prepared_sha):
    require(sha(HERE/'prepared.json')==prepared_sha,'Exact prepared audit SHA required')
    prepared=read(HERE/'prepared.json');verify(prepared['code_pins']);static_gate()
    out=HERE/'wait01';out.mkdir()  # A second invocation cannot dispatch a second audit.
    save(out/'invocation.json',dict(pid=os.getpid(),argv=sys.argv,started=time.time(),prepared_sha256=prepared_sha))
    child=None
    def cancel(signum,frame):raise RuntimeError('Offline watcher cancelled '+str(signum))
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    try:
        digest=wait_event(prepared,out);verify(prepared['code_pins'])
        command=[sys.executable,'-B',str(HERE/'audit.py'),'--authorize-terminal-audit',
                 '--prepared-sha256',prepared_sha,'--complete-sha256',digest]
        with (out/'audit.stdout.log').open('x') as stdout,(out/'audit.stderr.log').open('x') as stderr:
            child=subprocess.Popen(command,cwd=HERE,stdout=stdout,stderr=stderr,start_new_session=True)
            save(out/'audit_started.json',dict(child_pid=child.pid,parent_pid=os.getpid(),command=command,
                 started=time.time(),complete_sha256=digest,timeout_s=prepared['audit_seconds'],audit_attempt=1))
            timeout=False
            try:rc=child.wait(timeout=prepared['audit_seconds'])
            except subprocess.TimeoutExpired:
                timeout=True;rc=stop_audit(child)
        save(out/'actual_audit_exit.json',dict(child_pid=child.pid,actual_wait_returncode=rc,
             timed_out=timeout,command=command,observed_at=time.time(),retries=0))
        require(type(rc) is int and rc==0 and not timeout,'Actual offline auditor did not exit0; no retry')
        result=read(HERE/'terminal01/audit.json')
        require(result['status']=='ACCEPTED_E8M4_VI31_PREFIX66_DUT_CASE_ONLY_NOT_FULL2688' and
                result['complete_sha256']==digest and result['CSV_parses']==1,'Auditor scope/terminal mismatch')
        verify(prepared['code_pins']);require(sha(P/'complete.json')==digest,'Original terminal changed')
        report=['# Independent e8/m4 VI31 Prefix66 Terminal Acceptance','',
            'Accepted only the original66-call numerical child prefix, including65 predecessors.',
            'Original full512 byte oracle33792results/132guards,858helper retirements,66vstarts passed.',
            f'One complete CSV traversal: {result["csv_rows"]} rows /{result["retired"]} retirements; lastcycle{result["last_cycle"]}.',
            'Actual offline audit child wait returned0; no timeout/retry. Numeric monitor0 and no abort/failure verified.',
            'No worker/service exit0 inferred from pidfd completion, absent PID or service GC.',
            'Not full2688, original Linux execution/schedule, full parents or unknown historical stall reproduction.',
            'Plan SHA: `'+PLAN_SHA+'`.',
            'Audit SHA: `'+sha(HERE/'terminal01/audit.json')+'`.',
            'Actual auditor exit SHA: `'+sha(out/'actual_audit_exit.json')+'`.','']
        with (HERE/'terminal01/REPORT.md').open('x') as stream:stream.write('\n'.join(report))
        save(out/'complete.json',dict(status='OFFLINE_TERMINAL_AUDIT_ACCEPTED',actual_audit_returncode=0,
            audit_sha256=sha(HERE/'terminal01/audit.json'),report_sha256=sha(HERE/'terminal01/REPORT.md'),
            actual_audit_exit_sha256=sha(out/'actual_audit_exit.json'),complete_sha256=digest,
            no_retry=True,worker_service_exit0_inferred=False))
        print('OFFLINE_TERMINAL_AUDIT_ACCEPTED',flush=True)
    except BaseException as error:
        if child is not None:
            rc=stop_audit(child) if child.poll() is None else child.wait()
            if not (out/'actual_audit_exit.json').exists():
                save(out/'actual_audit_exit.json',dict(child_pid=child.pid,actual_wait_returncode=rc,
                     cancelled=True,retries=0,observed_at=time.time()))
        save(out/'NOT_ACCEPTED.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=repr(error),time=time.time()))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-event-wait',action='store_true')
    parser.add_argument('--prepared-sha256',required=True)
    args=parser.parse_args();require(args.authorize_event_wait,'Main must authorize event-service start')
    run(args.prepared_sha256)
