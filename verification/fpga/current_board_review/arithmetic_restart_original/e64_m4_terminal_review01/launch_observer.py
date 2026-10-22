#!/usr/bin/env python3
"""Submit exactly one independent observer, never a simulator or producer."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
UNIT = 'ara-e64m4-terminal-review01.service'


def save(name, value):
    with (HERE/name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    script = HERE/'observe.py'
    command = ['systemd-run', '--user', '--unit='+UNIT, '--property=RuntimeMaxSec=15000',
               '--property=KillMode=control-group', '--property=Restart=no',
               '--property=WorkingDirectory='+str(HERE),
               '--property=StandardOutput=append:'+str(HERE/'observer_service.log'),
               '--property=StandardError=append:'+str(HERE/'observer_service.log'),
               sys.executable, '-B', str(script)]
    save('observer_submission_command.json', dict(command=command,
         observer_sha256=hashlib.sha256(script.read_bytes()).hexdigest(), time=time.time(),
         no_existing_matching_observer_seen=True, no_DUT_launch=True, no_retry=True))
    env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    start = time.monotonic()
    with (HERE/'observer_submission.log').open('x') as log:
        child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        rc = child.wait(timeout=30)
    save('observer_submission_exit.json', dict(actual_wait_returncode=rc, pid=child.pid,
         elapsed_s=time.monotonic()-start, no_retry=True))
    if rc:
        return rc
    query = subprocess.run(['systemctl','--user','show',UNIT,
                            '--property=Id,LoadState,ActiveState,SubState,MainPID,ExecStart,ControlGroup,RuntimeMaxUSec,KillMode,Restart'],
                           env=env, text=True, capture_output=True, timeout=15)
    props = dict(line.split('=',1) for line in query.stdout.splitlines() if '=' in line)
    save('observer_startup_once.json', dict(actual_query_returncode=query.returncode,
         properties=props, stderr=query.stderr, queried_at=time.time(), CPU_queries=0, CSV_reads=0))
    print(json.dumps(dict(observer_unit=UNIT, submission_actual_exit=rc, properties=props)), flush=True)
    return 0 if query.returncode == 0 and props.get('LoadState') == 'loaded' else 1


if __name__ == '__main__':
    raise SystemExit(main())
