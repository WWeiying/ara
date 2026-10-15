"""Start one observer only, not the simulator or the existing collector."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
UNIT = 'ara-redspecial-full6720-m9-terminal-event01.service'


def save(name, value):
    with (HERE / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def main():
    command = ['systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec',
               '--property=RemainAfterExit=no', '--property=RuntimeMaxSec=14100',
               '--property=KillMode=control-group', '--property=Restart=no',
               '--property=WorkingDirectory=' + str(HERE),
               '--property=StandardOutput=append:' + str(HERE / 'service.log'),
               '--property=StandardError=append:' + str(HERE / 'service.log'),
               sys.executable, '-B', str(HERE / 'wait.py')]
    save('command.json', dict(command=command, observer_only=True, DUT_start=False,
         script_sha256=hashlib.sha256((HERE / 'wait.py').read_bytes()).hexdigest()))
    env = os.environ.copy()
    env.update(XDG_RUNTIME_DIR='/run/user/' + str(os.getuid()),
               DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/' + str(os.getuid()) + '/bus')
    start = time.monotonic()
    p = subprocess.run(command, cwd=HERE, env=env, text=True, capture_output=True, timeout=20)
    save('launch_wait.json', dict(actual_wait_exit=p.returncode, stdout=p.stdout, stderr=p.stderr,
         elapsed_s=time.monotonic() - start, unit=UNIT))
    print(p.stdout + p.stderr, end='')
    return p.returncode


if __name__ == '__main__':
    raise SystemExit(main())
