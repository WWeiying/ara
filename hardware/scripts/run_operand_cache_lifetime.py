#!/usr/bin/env python3
"""Compile the actual operand requester and test cache lifetime boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--filelist', required=True, type=Path)
p.add_argument('--out', required=True, type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
out = a.out.resolve()
if out.exists():
    p.error('choose a new output directory')
original = a.filelist.resolve().read_text()
if '+define+ARA_RED_CHAIN_BYPASS_4LANE' not in original:
    p.error('filelist must enable reduction chain bypass')
vcs = shutil.which('vcs')
if not vcs:
    p.error('VCS executable not found')
out.mkdir(parents=True)
filelist = out / 'filelist'
filelist.write_text('\n'.join(line for line in original.splitlines()
                             if '/hardware/tb/' not in line and
                             '+define+FOR_VERIFY' not in line) + '\n')
tb = root / 'hardware/tb/operand_cache_lifetime_tb.sv'
rtl = root / 'hardware/src/lane/operand_requester.sv'
inputs = [tb, rtl, root / 'hardware/include/ara_pkg.sv', filelist]
manifest = {'pass': False, 'sha256': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs}}
shutil.copy2(rtl, out / 'operand_requester.sv.snapshot')
commands = [
    [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '+define+SIMULATION',
     '-top', 'operand_cache_lifetime_tb', '-f', str(filelist), str(tb), '-Mdir=csrc', '-o', str(out / 'simv')],
    [str(out / 'simv'), '-no_save'],
]
manifest['commands'] = commands
for command, name in zip(commands, ['compile', 'run']):
    with (out / (name + '.log')).open('w') as log:
        try:
            code = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300).returncode
        except subprocess.TimeoutExpired:
            code = 'timeout'
    manifest[name + '_returncode'] = code
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if code != 0:
        sys.exit(f'{name} failed: {code}')
output = (out / 'run.log').read_text()
manifest['failures'] = re.findall(r'^.*(?:Error:|Fatal:|\bFAIL\b|started at .*failed at).*$', output, re.M)
manifest['pass'] = not manifest['failures'] and 'PASS: operand cache lifetime' in output
manifest['simulator_sha256'] = hashlib.sha256((out / 'simv').read_bytes()).hexdigest()
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(('PASS' if manifest['pass'] else 'FAIL') + ': operand cache lifetime')
sys.exit(0 if manifest['pass'] else 1)
