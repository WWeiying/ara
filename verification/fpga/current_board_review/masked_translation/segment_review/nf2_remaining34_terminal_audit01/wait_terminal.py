"""One event continuation and one offline audit; no simulator control or retries."""
import os
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import audit as a
OUT = a.HERE/'wait01'


def report(result):
    stats = result['aggregate']
    lines = ['# Independent NF2 Remaining34 Plus J4 Review','',result['status'],
        '',f'Actual offline audit exit0; {result["audit_seconds"]:.6f}s. Each of10 case auditors also exited0.',
        f'CSV files/parses: {stats["csv_files"]}/{stats["csv_parses"]}; rows{stats["rows"]}; retired_rows{stats["retired_rows"]}.',
        f'Checks{stats["checks"]}; checkpoints{stats["checkpoints"]}; pagefaults{stats["pagefaults"]}; S-ecalls{stats["ecalls"]}.',
        'Nine independently configured groups4x8+2 and unchanged J4 observer/ELF. Every row delivered unchanged to frozen generic and original case checkers.',
        'Original full field/tail/guard/memory oracle, trap/retry/partial-field rules, nofault precleanup, remap/refill, PC/code and normal completion retained.',
        'This batch proves34+J4 failed2; pinned prior M6 pilot4 completes40 distinct archived failed-source geometries. J4 positive2 reported separately.',
        f'Pins pre/post{result["pins_verified"]}, including1240 original plan pins; all10 persisted child returncodes numeric0, noabort/retry.',
        'Old J4 M2 evidence alone is not counted as M6. Source-derived real Sv39 is not original Linux ELF/signal-frame closure.',
        'RVFI scalar oracle is not direct vector payload capture. Only existing CSR checks are claimed; no new post-restore readback/state inference.',
        'Outer service exit is UNKNOWN; pidfd termination is not numeric exit evidence. Actual simulator outcomes are durable child records.',
        '',f'Plan SHA: `{a.PLAN_SHA}`.',f'Image SHA: `{a.IMAGE_SHA}`.',
        f'Complete SHA: `{result["complete_sha256"]}`.',
        f'Result SHA: `{a.sha(a.HERE/"terminal01/result.json")}`.',
        f'Pins SHA: `{a.sha(a.HERE/"terminal01/verified_pins.json")}`.',
        f'Audit exit SHA: `{a.sha(OUT/"audit_exit.json")}`.','']
    with (a.HERE/'terminal01/REVIEW.md').open('x') as stream: stream.write('\n'.join(lines))


def main():
    assert __debug__ and len(sys.argv) == 2
    digest = sys.argv[1]
    assert a.sha(a.HERE/'prepared.json') == digest
    prepared = a.read(a.HERE/'prepared.json'); a.verify(prepared['pins'])
    OUT.mkdir(); child = None
    a.save(OUT/'invocation.json',dict(pid=os.getpid(),argv=[sys.executable,'-B',*sys.argv],started=time.time(),
        prepared_sha256=digest,authorization_sha256=a.sha(a.HERE/'AUTHORIZATION.md')))
    def cancelled(sig,frame): raise RuntimeError('Watcher signal '+str(sig))
    signal.signal(signal.SIGTERM,cancelled); signal.signal(signal.SIGINT,cancelled)
    try:
        # Reuse the accepted pidfd/inotify routine, with this batch's paths only.
        waiter = a.load(a.OLD/'wait_terminal.py','nf2_frozen_event_wait')
        waiter.a = a; waiter.OUT = OUT
        complete_sha = waiter.wait_complete(time.monotonic()+prepared['wait_seconds'])
        command = [sys.executable,'-B',str(a.HERE/'audit.py'),'terminal','--authorize-terminal-audit',
            '--prepared-sha256',digest,'--complete-sha256',complete_sha]
        # Metadata/identity gates must pass before the audit process is started.
        a.admission(digest,complete_sha)
        a.save(OUT/'terminal_admission.json',dict(status='ALL10_FULL_TERMINAL_GATES_PASSED_NOT_AUDIT_PASS',
            complete_sha256=complete_sha,prepared_sha256=digest,time=time.time()))
        with (OUT/'audit.stdout.log').open('x') as stdout,(OUT/'audit.stderr.log').open('x') as stderr:
            child = subprocess.Popen(command,cwd=a.HERE,stdout=stdout,stderr=stderr)
            a.save(OUT/'audit_invocation.json',dict(pid=child.pid,parent_pid=os.getpid(),command=command,
                started=time.time(),complete_sha256=complete_sha,prepared_sha256=digest))
            rc = child.wait(timeout=prepared['audit_timeout_seconds'])
        a.save(OUT/'audit_exit.json',dict(pid=child.pid,actual_wait_returncode=rc,time=time.time(),
            evidence='Actual subprocess.Popen.wait; no vanished-PID/GC inference',
            stdout_sha256=a.sha(OUT/'audit.stdout.log'),stderr_sha256=a.sha(OUT/'audit.stderr.log')))
        assert rc == 0, 'First offline failure; no retry'
        a.verify(prepared['pins']); assert a.sha(a.P/'complete.json') == complete_sha
        result = a.read(a.HERE/'terminal01/result.json')
        assert result['status'] == a.ACCEPT and result['accepted'] is True and result['complete_sha256'] == complete_sha
        report(result)
        a.save(OUT/'complete.json',dict(status='INDEPENDENT_TERMINAL_AUDIT_ACCEPTED',actual_audit_returncode=rc,
            result_sha256=a.sha(a.HERE/'terminal01/result.json'),review_sha256=a.sha(a.HERE/'terminal01/REVIEW.md'),
            complete_sha256=complete_sha,no_retry=True))
        print('INDEPENDENT_TERMINAL_AUDIT_ACCEPTED',flush=True)
    except BaseException as error:
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        a.save(OUT/'firstfailure.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),time=time.time(),
            DUT_complete_sha256=a.sha(a.P/'complete.json') if (a.P/'complete.json').is_file() else None))
        print('NOT_ACCEPTED_NO_RETRY',repr(error),flush=True)
        raise


if __name__ == '__main__': main()
