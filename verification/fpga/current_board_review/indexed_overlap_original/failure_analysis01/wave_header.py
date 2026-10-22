#!/usr/bin/env python3
"""Read existing FSDB metadata and export one bounded offline window; no simulator."""
import json
import os
from pathlib import Path
import re
import subprocess
from analyze import HERE, ART, sha, save

VERDI = Path('/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1')
TOOL = VERDI / 'platform/linux64/bin/fsdb2vcd'
FSDB = ART / 'work/indexed_first_round.fsdb'
env = dict(os.environ, LD_LIBRARY_PATH=str(VERDI / 'etc/lib/libstdc++/linux64'))
summary = subprocess.run([str(TOOL), str(FSDB), '-summary'], cwd=HERE, env=env,
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
with (HERE / 'fsdb_summary.log').open('x') as stream:
    stream.write(summary.stdout)
assert summary.returncode == 0
assert re.search(r'scale unit\s*:\s*100fs', summary.stdout)
end = re.search(r'max xtag\s*:\s*\((\d+) (\d+)\)', summary.stdout)
ticks = (int(end[1]) << 32) | int(end[2])
info = dict(fsdb=str(FSDB), fsdb_sha256=sha(FSDB), tool_sha256=sha(TOOL),
            scale='100fs', maximum_ticks=ticks, maximum_ns=ticks / 10000,
            first_capture_reported_time=3574300000, first_capture_ns=357430,
            planned_stop_ns=1000000, stop_reached=False,
            interpretation='Failure happened before planned dump-disable; not a temporal profile miss.',
            summary_command=[str(TOOL), str(FSDB), '-summary'])
command = [str(TOOL), str(FSDB), '-o', str(HERE / 'compact.vcd'),
           '-bt', '357000ns', '-et', '369000ns', '-compacttree']
try:
    with (HERE / 'conversion.log').open('x') as stream:
        result = subprocess.run(command, cwd=HERE, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=90)
    info['conversion'] = dict(command=command, returncode=result.returncode)
    if result.returncode == 0:
        info['conversion']['sha256'] = sha(HERE / 'compact.vcd')
except subprocess.TimeoutExpired:
    info['conversion'] = dict(command=command, status='OFFLINE_EXPORT_TIMEOUT_NOT_DUT')
info['excluded_exports'] = dict(target_and_faults='Stopped un-compacted offline export, incomplete; not evidence',
                                selected='Dot-separated scope not matched by exporter, rc255; not evidence')
save(HERE / 'wave_metadata.json', info)
print(json.dumps(info, indent=2))
