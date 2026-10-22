#!/usr/bin/env python3
"""Launch observers only; original DUT units are never altered."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
           DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
for shape in ('e8_m8', 'e16_m8'):
    out = HERE / shape
    out.mkdir(exist_ok=True)
    receipt = out / 'launch.json'
    if receipt.exists() or (out / 'attachment.json').exists():
        raise RuntimeError('Existing launch: no duplicate allowed')
    unit = 'ara-' + shape.replace('_', '-') + '-m9-terminal-observer01'
    command = ['systemd-run', '--user', '--unit=' + unit,
        '--property=Type=exec', '--property=Restart=no',
        '--property=RemainAfterExit=yes', '--property=KillMode=control-group',
        '--property=RuntimeMaxSec=13200', '--property=TimeoutStopSec=10',
        '--property=WorkingDirectory=' + str(HERE),
        '--property=StandardOutput=append:' + str(out / 'service.log'),
        '--property=StandardError=append:' + str(out / 'service.log'),
        sys.executable, '-B', str(HERE / 'observe.py'), '--shape', shape]
    actual = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    value = dict(command=command, actual_returncode=actual.returncode,
        stdout=actual.stdout, stderr=actual.stderr, observed_at=time.time(),
        observer_sha256=hashlib.sha256((HERE / 'observe.py').read_bytes()).hexdigest(),
        original_service_modified=False,
        deadline_rule='Original ExecMainStartTimestampMonotonic + 13200 seconds; observer safety cap cannot extend it')
    with receipt.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(shape, actual.returncode, str(receipt), flush=True)
    if actual.returncode:
        raise SystemExit(actual.returncode)
