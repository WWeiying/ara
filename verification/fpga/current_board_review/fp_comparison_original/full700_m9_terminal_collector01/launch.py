"""Launch only the authorized independent collector, never the DUT."""
import os
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode = True
import collect as c

digest = '94081f451dbf9be6d30e5c3d1a7e83444431568093c839b6cb57722b41531976'
c.require(c.sha(c.HERE / 'READY.json') == digest, 'Sealed collector identity')
c.require(not (c.HERE / 'launch_command.json').exists(), 'One launch attempt')
command = ['systemd-run', '--user', '--unit=' + c.UNIT, '--property=Type=exec',
           '--property=RemainAfterExit=yes', '--property=RuntimeMaxSec=10800',
           '--property=KillMode=control-group', '--property=Restart=no',
           '--property=WorkingDirectory=' + str(c.HERE),
           '--property=StandardOutput=append:' + str(c.HERE / 'service.log'),
           '--property=StandardError=append:' + str(c.HERE / 'service.log'),
           sys.executable, '-B', str(c.HERE / 'collect.py'), 'attach', '--ready-sha256', digest]
c.save(c.HERE / 'launch_command.json', dict(command=command, launcher_sha256=c.sha(Path(__file__)),
       ready_sha256=digest, authority='Main authorized independent event collector; Zeno confirmed actual producer identity',
       no_DUT_launch=True, timestamp=time.time()))
start = time.monotonic()
p = subprocess.Popen(command, env=c.bus(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = p.communicate(timeout=30)
c.save(c.HERE / 'launch_exit.json', dict(returncode=p.returncode, stdout=stdout, stderr=stderr,
       elapsed_s=time.monotonic()-start, child_pid=p.pid, actual_wait=True))
c.require(p.returncode == 0, 'Collector service launch failure, no automatic retry')
print(stdout + stderr)
