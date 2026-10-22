"""Bounded inotify/pidfd continuation; never starts a simulator or retries."""
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
import audit as a
OUT=a.HERE/'wait01'


def wait_complete(deadline):
    libc=ctypes.CDLL(None,use_errno=True)
    fd=libc.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
    assert fd>=0, ('inotify_init1',ctypes.get_errno())
    ownerfd=None
    try:
        assert libc.inotify_add_watch(fd,os.fsencode(a.P),0x8|0x80|0x100|0x400|0x800)>=0
        launch=a.read(a.P/'launch.json')
        assert launch['plan_sha256']==a.PLAN_SHA and launch['owner']['properties']['Id']==a.UNIT
        pid=launch['owner']['pid']; identity=dict(pid=pid,state='ABSENT_EXIT_UNKNOWN')
        try: ownerfd=os.pidfd_open(pid)
        except ProcessLookupError: pass
        if ownerfd is not None:
            try:
                proc=Path('/proc')/str(pid)
                argv=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
                cg=(proc/'cgroup').read_text()
                assert str(a.F/'replay.py') in argv and str(a.P) in argv
                assert launch['owner']['properties']['ControlGroup'] in [l.split(':',2)[-1] for l in cg.splitlines()]
                identity=dict(pid=pid,state='LIVE_OWNER_IDENTITY_VERIFIED',argv=argv,cgroup=cg)
            except FileNotFoundError:
                identity=dict(pid=pid,state='DISAPPEARED_EXIT_UNKNOWN')
        a.save(OUT/'wait_started.json',dict(pid=os.getpid(),time=time.time(),owner=identity,
            mechanism='inotify_and_owner_pidfd_no_polling',active_CSV_reads=0))
        while not (a.P/'complete.json').exists():
            left=deadline-time.monotonic(); assert left>0,'Wait deadline without terminal'
            ready,_,_=select.select([fd]+([ownerfd] if ownerfd is not None else []),[],[],left)
            assert ready,'Wait deadline without terminal'
            if fd in ready:
                data=os.read(fd,65536); at=0
                while at<len(data):
                    _,event,_,size=struct.unpack_from('iIII',data,at); at+=16+size
                    assert not event&(0x400|0x800|0x4000|0x8000),'Watch lost/overflow'
            if ownerfd in ready: assert (a.P/'complete.json').exists(),'Owner exited without complete; no fabricated PASS'
        if ownerfd is not None:
            left=min(60.0,deadline-time.monotonic())
            assert left>0 and select.select([ownerfd],[],[],left)[0],'Owner still live after complete'
        return a.sha(a.P/'complete.json')
    finally:
        os.close(fd)
        if ownerfd is not None: os.close(ownerfd)


def report(result,rc):
    s,g,l=result['strict'],result['generic'],result['lossless']
    lines=['# Independent NF2 M6 Terminal Review','',result['status']+'.',
        f'Actual audit command exit{rc}; audit duration{result["audit_seconds"]:.6f}s.',
        f'Actual simulator child rc{result["child_returncode"]}, elapsed{result["child_elapsed_s"]}s, '
        'persisted before postcheck and bound by strict report SHA; no GC exit inference.',
        f'One full CSV parse: {g["rows"]} original rows, {g["retire_count"]} retired instructions, lastcycle{g["last_cycle"]}.',
        f'Four exact source cases, eight checkpoints, {s["checks"]} scalar checks; '
        f'legal alternate-field flags{s["alternate_protected_field"]}.',
        'Both64-element fields, two output guards and full8KiB memory/PTE/neighbor/CSR oracle retained.',
        'Six handlers: two pagefaults/start2 and5 plus four S-ecalls; same-PC retry, both-field prefix poison.',
        'Two nofault precleanup checkpoints precede PTE cleanup; two unmapped refills each2048 halfwords.',
        'Complete original action order, actual retired PC/code, error-state veto, restore-readback firmware checks, magic and CTRL0 passed.',
        f'Pins verified before/after: {result["pins_verified"]}, including700 original plan pins.',
        'Lossless before/after row SHA: `'+l['before_sha256']+'`.',
        'Result SHA: `'+a.sha(a.HERE/'terminal01/result.json')+'`.',
        'Pins SHA: `'+a.sha(a.HERE/'terminal01/verified_pins.json')+'`.',
        'Audit exit evidence SHA: `'+a.sha(OUT/'audit_exit.json')+'`.',
        'Complete SHA: `'+result['complete_sha256']+'`.',
        'Plan SHA: `'+a.PLAN_SHA+'`.',
        'Image SHA: `'+a.IMAGE_SHA+'`.','',
        'Scope is four exact archived failed-single geometries on frozen M6, not full96/all40 or Linux signal ABI.',
        'Both protection/unmapped cases use invalid Sv39 PTEs; remap/refill distinction retained.',
        'Original mask128B versus fixture16B/helper8B consumed remains a documented port boundary.',
        'RVFI scalar full-oracle evidence is not direct vector payload or internal CSR signal capture.',
        'No reference evidence substituted for DUT. Outer service terminal returncode is UNKNOWN, not fabricated.', '']
    with (a.HERE/'terminal01/REVIEW.md').open('x') as f: f.write('\n'.join(lines))


def main():
    assert __debug__ and len(sys.argv)==2
    prepared_sha=sys.argv[1]
    assert a.sha(a.HERE/'prepared.json')==prepared_sha
    prepared=a.read(a.HERE/'prepared.json'); a.verify(prepared['pins'])
    assert not OUT.exists(), 'One watcher invocation only'
    OUT.mkdir(); child=None
    a.save(OUT/'invocation.json',dict(pid=os.getpid(),argv=[sys.executable,'-B',*sys.argv],
        started=time.time(),prepared_sha256=prepared_sha,authorization_sha256=a.sha(a.HERE/'AUTHORIZATION.md')))
    def cancelled(sig,frame): raise RuntimeError('Watcher signal '+str(sig))
    signal.signal(signal.SIGTERM,cancelled); signal.signal(signal.SIGINT,cancelled)
    try:
        digest=wait_complete(time.monotonic()+prepared['wait_seconds'])
        observed,*_=a.admission(prepared_sha,digest)
        assert observed==digest
        a.save(OUT/'terminal_admission.json',dict(status='ACTUAL_FULL_PASS_GATES_PASSED_NOT_AUDIT_ACCEPTANCE',
            complete_sha256=digest,prepared_sha256=prepared_sha,parent_sha256=a.PARENT_SHA,time=time.time()))
        assert not (a.HERE/'terminal01').exists()
        command=[sys.executable,'-B',str(a.HERE/'audit.py'),'terminal','--authorize-terminal-audit',
            '--prepared-sha256',prepared_sha,'--complete-sha256',digest]
        with (OUT/'audit.stdout.log').open('x') as stdout,(OUT/'audit.stderr.log').open('x') as stderr:
            child=subprocess.Popen(command,cwd=a.HERE,stdout=stdout,stderr=stderr)
            a.save(OUT/'audit_invocation.json',dict(pid=child.pid,parent_pid=os.getpid(),command=command,
                prepared_sha256=prepared_sha,complete_sha256=digest,started=time.time()))
            rc=child.wait(timeout=prepared['audit_timeout_seconds'])
        a.save(OUT/'audit_exit.json',dict(pid=child.pid,actual_wait_returncode=rc,time=time.time(),
            evidence='Actual subprocess.Popen.wait result; not PID disappearance',
            stdout_sha256=a.sha(OUT/'audit.stdout.log'),stderr_sha256=a.sha(OUT/'audit.stderr.log')))
        assert rc==0,'Offline audit failed; no retry'
        a.verify(prepared['pins']); assert a.sha(a.P/'complete.json')==digest
        result=a.read(a.HERE/'terminal01/result.json')
        assert result['status']==a.ACCEPT and result['accepted'] is True and result['complete_sha256']==digest
        report(result,rc)
        a.save(OUT/'complete.json',dict(status='INDEPENDENT_TERMINAL_AUDIT_ACCEPTED',actual_audit_returncode=rc,
            result_sha256=a.sha(a.HERE/'terminal01/result.json'),review_sha256=a.sha(a.HERE/'terminal01/REVIEW.md'),
            complete_sha256=digest,no_retry=True))
        print('INDEPENDENT_TERMINAL_AUDIT_ACCEPTED',flush=True)
    except BaseException as error:
        if child is not None and child.poll() is None: child.kill(); child.wait()
        a.save(OUT/'firstfailure.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),time=time.time(),
            DUT_complete_sha256=a.sha(a.P/'complete.json') if (a.P/'complete.json').is_file() else None))
        print('NOT_ACCEPTED_NO_RETRY',repr(error),flush=True)
        raise


if __name__=='__main__': main()
