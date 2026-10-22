#!/usr/bin/env python3
"""Export a derived container made by fsdbrecover from immutable copied sidecars."""
import json
import os
from pathlib import Path
import subprocess
from acquire import HERE, TOOL, VERDI, sha, save, files

acquisition = json.loads((HERE/'acquisition.json').read_text())
assert files() == acquisition['before']
for p, h in acquisition['pins'].items():
    assert sha(Path(p)) == h
env = dict(os.environ, LD_LIBRARY_PATH=str(VERDI/'etc/lib/libstdc++/linux64'))
summary_cmd = [str(TOOL), str(HERE/'recovered.fsdb'), '-summary']
result = subprocess.run(summary_cmd, cwd=HERE, env=env, text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
with (HERE/'recovered_summary.log').open('x') as stream:
    stream.write(result.stdout)
assert result.returncode == 0 and '100fs' in result.stdout and '(2 1410065408)' in result.stdout
command = json.loads((HERE/'export_profile.json').read_text())['command']
command[1] = str(HERE/'recovered.fsdb')
command[command.index('-o')+1] = str(HERE/'recovered_focus.vcd')
with (HERE/'export_recovered.log').open('x') as stream:
    result = subprocess.run(command, cwd=HERE, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
assert files() == acquisition['before']
for p, h in acquisition['pins'].items():
    assert sha(Path(p)) == h
save(HERE/'recovery_export.json', dict(recovery_command=[str(TOOL.with_name('fsdbrecover')),
    'inputs/indexed_first_round.fsdb', '-o', 'recovered.fsdb'], recovery_returncode=0,
    recovery_semantics='Vendor tool merges temporary files into a NEW container; no value repair, no original writes, no -cp/-del_src.',
    recovery_tool_sha256=sha(TOOL.with_name('fsdbrecover')), recovered_sha256=sha(HERE/'recovered.fsdb'),
    command=command, returncode=result.returncode, original_and_copied_inputs_unchanged=True,
    summary_command=summary_cmd, scale='100fs', original_max_ticks=10000000000,
    recovered_max_ticks=10000000000, no_DUT=True))
assert result.returncode == 0
print('RECOVERED_FOCUSED_EXPORT', (HERE/'recovered_focus.vcd').stat().st_size, flush=True)
