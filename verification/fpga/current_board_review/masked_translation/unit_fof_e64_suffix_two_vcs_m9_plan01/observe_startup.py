#!/usr/bin/env python3
"""One bounded pair of startup samples, no loop or simulation control."""
import json
import os
from pathlib import Path
import subprocess
import hashlib
import time

HERE = Path(__file__).resolve().parent
OUT = HERE/'prepared01'
UNIT = 'ara-unit-fof-e64-two-m9-01.service'
IMAGE_EXE='/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image/_build/vcs/simv'
PLAN=json.loads((OUT/'plan.json').read_text())
EXPECTED={c['id']:c['sha256'] for c in PLAN['cases']}


def snapshot():
    q = subprocess.run(['systemctl', '--user', 'show', UNIT, '-p', 'LoadState', '-p', 'ActiveState',
                        '-p', 'MainPID', '-p', 'ControlGroup', '-p', 'Result', '-p', 'ExecMainStatus'],
                       text=True, capture_output=True, timeout=15)
    q.check_returncode()
    unit = dict(line.split('=', 1) for line in q.stdout.splitlines())
    group = unit.get('ControlGroup')
    processes = []
    if group:
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if (proc/'comm').read_text().strip() != 'simv':
                    continue
                if (proc/'cgroup').read_text().strip() != '0::'+group:
                    continue
                argv = (proc/'cmdline').read_bytes().decode().strip('\0').split('\0')
                trace_arg = [a for a in argv if a.startswith('+COMMIT_TRACE='+str(OUT)+'/')]
                assert len(trace_arg) == 1, 'Owned simv missing expected trace'
                trace = Path(trace_arg[0].split('=', 1)[1])
                private = trace.parent/'input.elf'
                assert '+PRELOAD='+str(private) in argv, 'Private ELF argv mismatch'
                testcase=[a.split('=',1)[1] for a in argv if a.startswith('+TESTCASE=')]
                assert len(testcase)==1 and testcase[0] in EXPECTED, 'Exact runtime membership'
                assert hashlib.sha256(private.read_bytes()).hexdigest()==EXPECTED[testcase[0]], 'Actual private ELF'
                assert os.readlink(proc/'exe')==IMAGE_EXE and argv[0]==IMAGE_EXE, 'Actual M9 executable'
                stat = (proc/'stat').read_text().rsplit(')', 1)[1].split()
                size, last = None, None
                if trace.exists():
                    size = trace.stat().st_size
                    with trace.open('rb') as f:
                        f.seek(max(0, size-16384))
                        tail = f.read()
                    rows = tail.split(b'\n')[:-1]
                    if rows:
                        fields = rows[-1].decode().split(',')
                        if len(fields) == 14 and fields[0].isdigit():
                            last = dict(cycle=int(fields[0]), event=fields[1], order=fields[2], pc=fields[5])
                processes.append(dict(testcase=testcase[0],private_elf_sha256=EXPECTED[testcase[0]],pid=int(proc.name), exe=os.readlink(proc/'exe'), argv=argv,
                                      starttime_ticks=int(stat[19]), cpu_ticks=int(stat[11])+int(stat[12]),
                                      private_elf=str(private), trace=str(trace), bytes=size, last_complete_row=last))
            except (FileNotFoundError, ProcessLookupError):
                continue
    return dict(time=time.time(), unit=unit, processes=processes)


if __name__ == '__main__':
    out = HERE/'startup_observation.json'
    if out.exists():
        raise SystemExit('No observation overwrite/retry')
    time.sleep(15)
    first = snapshot()
    time.sleep(5)
    second = snapshot()
    old = {p['pid']: p for p in first['processes']}
    growth = []
    for p in second['processes']:
        q = old.get(p['pid'])
        if q and p['starttime_ticks'] == q['starttime_ticks']:
            growth.append(dict(pid=p['pid'], cpu_delta=p['cpu_ticks']-q['cpu_ticks'],
                               csv_delta=(p['bytes'] or 0)-(q['bytes'] or 0)))
    confirmed = (first['unit']['LoadState'] == second['unit']['LoadState'] == 'loaded'
                 and first['unit']['MainPID'] == second['unit']['MainPID'] != '0'
                 and second['unit']['ActiveState'] == 'active'
                 and len(growth)==2 and {p['testcase'] for p in second['processes']}==set(EXPECTED)
                 and all(p['cpu_delta'] > 0 and p['csv_delta'] > 0 for p in growth))
    result = dict(status='ACTUAL_SIMV_AND_CSV_PROGRESS_NOT_PASS' if confirmed else 'STARTUP_NOT_CONFIRMED',
                  first=first, second=second, growth=growth, samples=2, interval_s=5,
                  no_future_polling=True, full_csv_parsed=False)
    with out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(dict(status=result['status'], main_pid=second['unit']['MainPID'], growth=growth)))
    raise SystemExit(0 if confirmed else 1)
