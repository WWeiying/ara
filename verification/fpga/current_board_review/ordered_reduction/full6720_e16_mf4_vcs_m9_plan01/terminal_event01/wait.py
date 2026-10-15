"""Bounded inotify terminal metadata observer; never opens CSV or raw traces."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import struct
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'prepared01'
PLAN = '49ffb74caba23b096d9addb009511a4d92e21f51c9182379d839b345e53978a1'
NAME = 'fp_redspecial_e16_mf4_full6720'
EVENT = 'collector.wait.json'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def require(ok, why):
    if not ok:
        raise ValueError(why)


def main():
    start = time.monotonic()
    fd = -1
    result = dict(status='NOT_ACCEPTED', CSV_raw_reads=0, DUT_launch=False)
    try:
        require(sha(OUT / 'plan.json') == PLAN, 'Exact launched plan')
        launch = read(OUT / 'launch.json')
        require(launch['plan_sha256'] == PLAN, 'Launch identity')
        # Observer headroom only; never changes any DUT/service deadline.
        deadline = time.monotonic() + max(0, launch['started'] + 13800 - time.time())
        libc = ctypes.CDLL(None, use_errno=True)
        libc.inotify_init1.argtypes = [ctypes.c_int]
        libc.inotify_init1.restype = ctypes.c_int
        libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        libc.inotify_add_watch.restype = ctypes.c_int
        fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
        require(fd >= 0, 'inotify_init1')
        require(libc.inotify_add_watch(fd, os.fsencode(OUT), 0x8 | 0x80) >= 0, 'inotify watch')
        save('armed.json', dict(status='WAITING_FOR_COLLECTOR_WAIT_EVENT', pid=os.getpid(),
             plan_sha256=PLAN, event=str(OUT / EVENT), launch_receipt_sha256=sha(OUT / 'launch.json'),
             deadline_epoch=launch['started'] + 13800, progress_polling=False,
             watch_before_exists_check=True, started=time.time()))
        found = (OUT / EVENT).exists()
        while not found:
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'Observer bound expired; no acceptance or retry')
            ready, _, _ = select.select([fd], [], [], remaining)
            require(bool(ready), 'No terminal receipt within observer bound')
            data = os.read(fd, 65536)
            offset = 0
            while offset < len(data):
                _, mask, _, length = struct.unpack_from('iIII', data, offset)
                name = data[offset + 16:offset + 16 + length].split(b'\0', 1)[0].decode()
                offset += 16 + length
                require(not mask & 0x4000, 'inotify overflow')
                if name == EVENT and mask & (0x8 | 0x80):
                    found = True
        paths = dict(collector_wait=OUT / EVENT, collector=OUT / 'collector_result.json',
                     service=OUT / 'service_exit.json', complete=OUT / 'complete.json',
                     numeric=OUT / 'replay/tests' / NAME / 'child_outcome.unvalidated.json')
        values = {}
        for key, path in paths.items():
            values[key] = read(path) if path.is_file() else None
        result.update(actual_collector_wait=values['collector_wait'],
                      actual_service_exit=values['service'], actual_child_outcome=values['numeric'],
                      collector=values['collector'], complete_status=(values['complete'] or {}).get('status'),
                      evidence_pins={str(p): sha(p) for p in paths.values() if p.is_file()})
        w, c, s, n, done = (values[k] for k in ('collector_wait', 'collector', 'service', 'numeric', 'complete'))
        require(type(w['actual_wait_exit']) is int and w['actual_wait_exit'] == 0 and w['timed_out'] is False,
                'Actual collector numeric0 required')
        require(s['kind'] == 'ACTUAL_SYSTEMD_EXEC_STOP_POST' and s['SERVICE_RESULT'] == 'success' and
                s['EXIT_CODE'] == 'exited' and s['EXIT_STATUS'] == '0', 'Actual service exit0 required')
        require(type(n['returncode']) is int and n['returncode'] == 0 and n['timed_out'] is False and
                n['failure_seen'] is False and 0 < n['elapsed_s'] <= 10800, 'Actual simulator numeric0 required')
        require(c['status'] == 'PASS_FULL6720_M9_METADATA_COLLECTED_NOT_LINUX' and c['pins_unchanged'] is True,
                'Full collector acceptance required')
        require(c['actual_simulator_wait'] == n and c['service_exit'] == s, 'Actual outcomes agree')
        require([c['scope'][k] for k in ('calls', 'output_bytes', 'flags', 'vstarts')] ==
                [6720, 967680, 6720, 6720], 'Full original scope')
        require(done['plan_sha256'] == PLAN and done['aborted'] is False and done['pins_unchanged'] is True and
                done['retries'] == 0, 'Exact non-aborted producer')
        require(c['evidence_pins'][str(OUT / 'plan.json')] == PLAN and
                c['evidence_pins'][str(OUT / 'complete.json')] == sha(OUT / 'complete.json'), 'Terminal identity')
        require(sha(OUT / 'plan.json') == PLAN, 'Terminal plan unchanged')
        result.update(status='TERMINAL_COLLECTOR_ACCEPTED_METADATA_ONLY', independent_CSV_parse=False,
                      original_Linux_closed=False, plan_sha256=PLAN)
    except BaseException as error:
        result['error'] = repr(error)
    finally:
        if fd >= 0:
            os.close(fd)
    result.update(elapsed_s=time.monotonic() - start, finished=time.time())
    save('notification.json', result)
    print(json.dumps(result), flush=True)
    return int(result['status'] != 'TERMINAL_COLLECTOR_ACCEPTED_METADATA_ONLY')


if __name__ == '__main__':
    raise SystemExit(main())
