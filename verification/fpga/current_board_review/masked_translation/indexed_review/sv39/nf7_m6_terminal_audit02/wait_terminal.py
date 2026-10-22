"""Prepared inotify/pidfd continuation. Parent must authorize starting this tool."""
import os
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
import audit as a
OUT=a.HERE/'wait01'


def report(result):
    s=result['aggregate']
    lines=['# NF7 M6 Full96 Independent Terminal Review','',result['status'],
        f'Actual overall audit wait() exit0; {result["audit_seconds"]:.6f}s. All24 case auditors exit0.',
        f'CSV files/parses{s["csv_files"]}/{s["csv_parses"]}; rows{s["rows"]}; retired_rows{s["retired_rows"]}.',
        f'Original96 trials, {s["checks"]} comparisons, {s["checkpoints"]} checkpoints, {s["pagefaults"]} faults and{s["ecalls"]} S-ecalls.',
        'Every original row delivered unchanged to the frozen generic validator and original NF7 oracle in one pass per CSV.',
        'Actual PC/code matches private ELF; full original fractional tails/guards/memory/partial-field/restart/CSR context retained.',
        'All24 simulator outcome records contain actual numeric rc0 before runner postchecks. Independent audit rc is recorded separately.',
        f'Pins pre/post{result["pins_verified"]}, including878 original NF7 plan pins and actual accepted NF2 prerequisite.',
        'Noabort/retry;2400s child elapsed checked.2700s group enforcement comes from sealed worker timers and sticky abort, not a new wallclock measurement.',
        'Outer service historical returncode UNKNOWN; no GC default used. No added post-restore CSR readback claimed.',
        'Scope: original source-derived grouped96 on frozen M6, not original Linux replay or its unidentified exact failure phase.',
        '',f'Plan SHA: `{a.PLAN_SHA}`.',f'Parent SHA: `{a.PARENT_SHA}`.',f'Image SHA: `{a.IMAGE_SHA}`.',
        f'Complete SHA: `{result["complete_sha256"]}`.',f'Result SHA: `{a.sha(a.HERE/"terminal01/result.json")}`.',
        f'Verified-pins SHA: `{a.sha(a.HERE/"terminal01/verified_pins.json")}`.',
        f'Actual audit-exit SHA: `{a.sha(OUT/"audit_exit.json")}`.','']
    with (a.HERE/'terminal01/REVIEW.md').open('x') as stream:stream.write('\n'.join(lines))


def main():
    assert __debug__ and len(sys.argv)==3 and sys.argv[1]=='--authorize-wait', 'Parent authorization required'
    prepared_sha=sys.argv[2];assert a.sha(a.HERE/'prepared.json')==prepared_sha
    prepared=a.read(a.HERE/'prepared.json');a.verify(prepared['pins'])
    OUT.mkdir();child=None
    a.save(OUT/'invocation.json',dict(pid=os.getpid(),argv=[sys.executable,'-B',*sys.argv],started=time.time(),
        prepared_sha256=prepared_sha,authorization='Explicit parent --authorize-wait; prepare alone did not start watcher'))
    def cancelled(sig,frame):raise RuntimeError('Offline watcher signal '+str(sig))
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    try:
        waiter=a.load(a.OLD/'wait_terminal.py','nf7_accepted_event_wait');waiter.a=a;waiter.OUT=OUT
        complete_sha=waiter.wait_complete(time.monotonic()+prepared['wait_seconds'])
        a.admission(prepared_sha,complete_sha)
        a.save(OUT/'terminal_admission.json',dict(status='WHOLE24_FULL_TERMINAL_GATES_PASSED_NOT_AUDIT_PASS',
            prepared_sha256=prepared_sha,complete_sha256=complete_sha,time=time.time()))
        cmd=[sys.executable,'-B',str(a.HERE/'audit.py'),'terminal','--authorize-terminal-audit',
            '--prepared-sha256',prepared_sha,'--complete-sha256',complete_sha]
        with (OUT/'audit.stdout.log').open('x') as stdout,(OUT/'audit.stderr.log').open('x') as stderr:
            child=subprocess.Popen(cmd,cwd=a.HERE,stdout=stdout,stderr=stderr)
            a.save(OUT/'audit_invocation.json',dict(pid=child.pid,parent_pid=os.getpid(),command=cmd,started=time.time(),
                prepared_sha256=prepared_sha,complete_sha256=complete_sha))
            rc=child.wait(timeout=prepared['audit_timeout_seconds'])
        a.save(OUT/'audit_exit.json',dict(pid=child.pid,actual_wait_returncode=rc,time=time.time(),
            evidence='Actual subprocess.Popen.wait returncode, not PID disappearance',
            stdout_sha256=a.sha(OUT/'audit.stdout.log'),stderr_sha256=a.sha(OUT/'audit.stderr.log')))
        assert a.zero(rc),'First audit failure; no retry'
        a.verify(prepared['pins']);assert a.sha(a.P/'complete.json')==complete_sha
        result=a.read(a.HERE/'terminal01/result.json')
        assert result['status']==a.ACCEPT and result['accepted'] is True and result['complete_sha256']==complete_sha
        report(result)
        a.save(OUT/'complete.json',dict(status='INDEPENDENT_TERMINAL_AUDIT_ACCEPTED',actual_audit_returncode=rc,
            complete_sha256=complete_sha,result_sha256=a.sha(a.HERE/'terminal01/result.json'),
            review_sha256=a.sha(a.HERE/'terminal01/REVIEW.md'),no_retry=True))
        print('INDEPENDENT_TERMINAL_AUDIT_ACCEPTED',flush=True)
    except BaseException as error:
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        a.save(OUT/'firstfailure.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),time=time.time(),
            DUT_complete_sha256=a.sha(a.P/'complete.json') if (a.P/'complete.json').is_file() else None))
        print('NOT_ACCEPTED_NO_RETRY',repr(error),flush=True)
        raise


if __name__=='__main__':main()
