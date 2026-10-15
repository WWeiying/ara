"""One bounded inotify subscription; metadata only, no collector rerun."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'prepared01'
PLAN_SHA = '7dcf6503906b5c50e09e9fa6d681f0664d3f69c3fae31095606621863ec2e5cc'

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')

def main():
    assert sha(OUT / 'plan.json') == PLAN_SHA
    # Same original service deadline plus its already configured teardown bound.
    deadline = read(OUT / 'launch.json')['started'] + 13200 + 360
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'inotify_init1')
    try:
        if libc.inotify_add_watch(fd, os.fsencode(OUT), 0x8 | 0x80) < 0:
            raise OSError(ctypes.get_errno(), 'inotify_add_watch')
        save('started.json', dict(pid=os.getpid(), started=time.time(), deadline=deadline,
             plan_sha256=PLAN_SHA, watch=str(OUT), method='inotify CLOSE_WRITE/MOVED_TO',
             no_CPU_queries=True, no_CSV_reads=True, no_retries=True))
        needed = ['collector_result.json', 'collector_exit.json']
        while not all((OUT / name).is_file() for name in needed):
            remaining = deadline - time.time()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                raise TimeoutError('Original service plus teardown deadline; no retry')
            os.read(fd, 65536)
        result = read(OUT / 'collector_result.json')
        exit_receipt = read(OUT / 'collector_exit.json')
        names = needed + ['service_exit.json', 'complete.json']
        metadata = {name: read(OUT / name) for name in names if (OUT / name).is_file()}
        report_path = OUT / 'replay/tests/arithmetic_original_e32_m4_full5985_packed/strict_original.json'
        report = read(report_path) if report_path.is_file() else None
        accepted = (result.get('status') == 'ACCEPTED_M9_ORIGINAL_E32_M4_FULL5985_NOT_LINUX'
                    and type(exit_receipt.get('actual_wait_returncode')) is int
                    and exit_receipt['actual_wait_returncode'] == 0
                    and exit_receipt.get('timed_out') is False
                    and exit_receipt.get('retries') == 0
                    and sha(OUT / 'plan.json') == PLAN_SHA)
        save('notification.json', dict(status='TERMINAL_COLLECTOR_ACCEPTED' if accepted else 'NOT_ACCEPTED',
             observed_at=time.time(), plan_sha256=PLAN_SHA, metadata=metadata,
             strict_report=report, metadata_sha256={name: sha(OUT/name) for name in names if (OUT/name).is_file()},
             strict_report_sha256=sha(report_path) if report else None,
             no_CSV_reads=True, no_reference_or_DUT_runs=True,
             scope='M9 source-derived original e32/m4 full5985; not Linux closure'))
        return 0 if accepted else 1
    finally:
        os.close(fd)

if __name__ == '__main__':
    try:
        rc = main()
    except BaseException as error:
        save('wait_failure.json', dict(status='NOT_ACCEPTED', cause=f'{type(error).__name__}: {error}',
             observed_at=time.time(), retries=0))
        rc = 1
    save('wait_exit.json', dict(exit_code=rc, pid=os.getpid(), finished=time.time()))
    raise SystemExit(rc)
