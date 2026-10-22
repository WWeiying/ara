#!/usr/bin/env python3
"""Offline conversion of the single bounded capture, never starts simulation."""
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
VERDI = Path('/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1')
status = json.loads((HERE / 'complete.json').read_text())
assert status['returncode'] == 0 and status['planned_stop_observed'] and not status['timed_out']
assert not (HERE / 'selected.vcd').exists()
command = [str(VERDI / 'platform/linux64/bin/fsdb2vcd'), 'diagnostic.fsdb',
           '-o', 'selected.vcd', '-bt', '79000ns', '-et', '83000ns', '-compacttree']
with (HERE / 'convert_command.json').open('x') as f:
    json.dump(command, f, indent=2)
with (HERE / 'convert.log').open('x') as f:
    result = subprocess.run(command, cwd=HERE, stdout=f, stderr=subprocess.STDOUT,
                            env=dict(os.environ, LD_LIBRARY_PATH=str(VERDI / 'etc/lib/libstdc++/linux64')),
                            timeout=120)
with (HERE / 'convert_exit.json').open('x') as f:
    json.dump(dict(returncode=result.returncode), f)
result.check_returncode()
print('CONVERTED', (HERE / 'selected.vcd').stat().st_size)
