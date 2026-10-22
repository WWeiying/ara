#!/usr/bin/env python3
"""One short observation only; never cancel/relaunch or change acceptance."""
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / 'vcs_candidate04_01'
UNIT = 'ara-gather-focused-candidate04-01.service'


def sample():
    records = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / 'comm').read_text().strip() != 'simv':
                continue
            group = (proc / 'cgroup').read_text()
            if UNIT not in group:
                continue
            argv = (proc / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
            stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            trace = Path(next(arg.split('=', 1)[1] for arg in argv if arg.startswith('+COMMIT_TRACE=')))
            with trace.open('rb') as stream:
                size = trace.stat().st_size
                stream.seek(max(0, size-8192))
                lines = stream.read().splitlines()
            last = lines[-2].decode().split(',')
            records.append(dict(pid=int(proc.name), start_ticks=int(stat[19]),
                cpu_ticks=int(stat[11])+int(stat[12]), trace_bytes=size, last_cycle=int(last[0]),
                argv=argv, cgroup=group, cwd=str((proc / 'cwd').resolve()),
                executable=str((proc / 'exe').resolve())))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return sorted(records, key=lambda record: record['pid'])


before = sample()
time.sleep(3)
after = sample()
advancing = len(before) == len(after) == 2 and all(
    a['pid'] == b['pid'] and a['start_ticks'] == b['start_ticks'] and
    a['argv'] == b['argv'] and b['cpu_ticks'] > a['cpu_ticks'] and
    b['trace_bytes'] > a['trace_bytes'] > 0 and b['last_cycle'] > a['last_cycle'] > 0
    for a,b in zip(before, after))
record = dict(status='ADVANCING_TWO_SIMV' if advancing else 'SHORT_OBSERVATION_NOT_CONFIRMED',
              samples=[before, after], observation_only=True, retries=0)
with (OUT / 'actual_startup.json').open('x') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print(record['status'])
for a,b in zip(before, after):
    print(a['pid'], 'cycles', a['last_cycle'], b['last_cycle'], 'bytes', a['trace_bytes'], b['trace_bytes'])
