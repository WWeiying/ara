"""Attach only a terminal observer. Never start/query the DUT service."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
UNIT = 'ara-fp-unboxed-full17920-m9-terminal-observer01.service'
DEADLINE = 1792024000.28614 + 13200 + 300 + 120


def save(name, data):
    with (HERE/name).open('x') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def main():
    # Exclusive attachment prevents accidental repeated observers.
    with (HERE/'attachment.lock').open('x') as f:
        f.write(str(os.getpid())+'\n')
    script = HERE/'observe.py'
    ast.parse(script.read_text())
    env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    before = subprocess.run(['systemctl','--user','show',UNIT,'--property=Id,LoadState,ActiveState,MainPID'],
                            env=env, text=True, capture_output=True, timeout=15)
    save('observer_unit_before.json',dict(actual_returncode=before.returncode,stdout=before.stdout,stderr=before.stderr))
    props = dict(line.split('=',1) for line in before.stdout.splitlines() if '=' in line)
    if before.returncode != 0 or props.get('LoadState') != 'not-found' or props.get('MainPID') != '0':
        raise RuntimeError('Observer unit not proven absent; no launch')
    remaining = int(DEADLINE-time.time())
    if remaining <= 0:
        raise RuntimeError('Original absolute observation deadline expired; no launch')
    cmd = ['systemd-run','--user','--unit='+UNIT,'--property=Type=exec',
           '--property=RemainAfterExit=no','--property=KillMode=control-group','--property=Restart=no',
           '--property=RuntimeMaxSec='+str(remaining),'--property=TimeoutStopSec=20',
           '--property=WorkingDirectory='+str(HERE),
           '--property=StandardOutput=append:'+str(HERE/'service.log'),
           '--property=StandardError=append:'+str(HERE/'service.log'),
           '/usr/bin/python3','-B',str(script)]
    save('launch_command.json',dict(command=cmd,observer_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
         absolute_deadline=DEADLINE,submitted_at=time.time(),DUT_launch=False,DUT_query=False,CSV_read=False))
    result = subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=30)
    save('systemd_run.json',dict(actual_returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    if result.returncode:
        raise RuntimeError('Observer submission failed, no retry')
    print(json.dumps(dict(observer_unit=UNIT,actual_submission_rc=result.returncode,path=str(HERE))))


if __name__ == '__main__':
    main()
