#!/usr/bin/env python3
"""Two bounded samples of actual simv processes; no completion polling."""
import json
from pathlib import Path
import time

from replay_candidate03 import OUT, IMAGE, UNIT, read, require, save


def sample(pid, argv):
    proc = Path('/proc') / str(pid)
    stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    trace = Path(next(a.split('=', 1)[1] for a in argv if a.startswith('+COMMIT_TRACE=')))
    size, cycle = 0, 0
    if trace.exists():
        with trace.open('rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size-65536))
            tail = stream.read()
        tail = tail[:tail.rfind(b'\n')]
        for line in reversed(tail.splitlines()):
            first = line.split(b',', 1)[0]
            if first.isdigit():
                cycle = int(first)
                break
    return dict(pid=pid, time=time.time(), cpu_ticks=int(stat[11])+int(stat[12]),
                state=stat[0], cwd=str((proc / 'cwd').resolve()),
                executable=str((proc / 'exe').resolve()), cgroup=(proc / 'cgroup').read_text(),
                argv=argv, trace=str(trace), trace_bytes=size, last_complete_cycle=cycle)


ledger = read(IMAGE / 'image.json')
processes = []
for proc in Path('/proc').glob('[0-9]*'):
    try:
        argv = [s.decode() for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
        if argv and argv[0] == ledger['simv'] and any(str(OUT) in a for a in argv):
            processes.append((int(proc.name), argv))
    except (OSError, UnicodeError):
        continue
require(len(processes) == 2, 'Startup did not expose exactly two own simv processes')
before = [sample(pid, argv) for pid, argv in processes]
time.sleep(3)
after = [sample(pid, argv) for pid, argv in processes]
advancing = all(b['cpu_ticks'] > a['cpu_ticks'] and
                b['trace_bytes'] > a['trace_bytes'] and
                b['last_complete_cycle'] > a['last_complete_cycle'] and
                UNIT in a['cgroup'] and UNIT in b['cgroup'] and
                b['executable'] == ledger['simv'] for a, b in zip(before, after))
save(OUT / 'actual_simv_confirmation.json', dict(status='ADVANCING_TWO_SIMV' if advancing else 'NOT_CONFIRMED',
     samples=[before, after], completion_polling=False, finished=time.time()))
require(advancing, 'Two-process cycle advancement was not confirmed; inspect retained samples')
print(json.dumps([dict(pid=a['pid'], cycles=[a['last_complete_cycle'], b['last_complete_cycle']],
                       trace_bytes=[a['trace_bytes'], b['trace_bytes']],
                       cpu_ticks=[a['cpu_ticks'], b['cpu_ticks']]) for a, b in zip(before, after)], indent=2))
