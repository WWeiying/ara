"""One bounded event-driven pilot startup observation, never a PASS verdict."""
import argparse
import csv
from pathlib import Path
import select
import subprocess
import time
import vcs_jobs8 as base


def confirm(out, unit):
    path = out / 'groups/group00/run/tests/nf8_g00/commit_trace.csv'
    events = base.live_tail.DirectoryEvents(out)
    stream = None
    pending = ''
    first = last = None
    first_time = None
    deadline = time.monotonic() + 180
    try:
        while True:
            if stream is None and path.exists():
                stream = path.open()
            if stream is not None:
                lines = (pending + stream.read()).split('\n')
                pending = lines.pop()
                for line in lines:
                    values = next(csv.reader([line]))
                    if values == base.csv_oracle.FIELDS:
                        continue
                    base.require(len(values) == len(base.csv_oracle.FIELDS), 'Malformed startup CSV')
                    row = dict(zip(base.csv_oracle.FIELDS, values))
                    if row['event'] == 'retire':
                        last = row
                if last is not None:
                    if first is None:
                        first = dict(last)
                        first_time = time.monotonic()
                    elif int(last['order']) >= int(first['order']) + 32 and int(last['cycle']) > int(first['cycle']):
                        break
            base.require(not (out / 'complete.json').exists(), 'Worker terminal before live confirmation')
            remaining = deadline - time.monotonic()
            base.require(remaining > 0, '180s startup observation expired; no retry')
            if select.select([events.fd], [], [], remaining)[0]:
                events.drain()
        state = dict(line.split('=', 1) for line in subprocess.check_output(
            ['systemctl', '--user', 'show', unit, '-p', 'ActiveState', '-p', 'MainPID',
             '-p', 'ControlGroup', '-p', 'RuntimeMaxUSec', '-p', 'KillMode', '-p', 'Restart'],
            text=True, timeout=10).splitlines())
        base.require(state['ActiveState'] == 'active' and state['MainPID'] != '0', 'Service not live')
        base.require(state['KillMode'] == 'control-group' and state['Restart'] == 'no', 'Wrong service cleanup/restart')
        root = Path('/sys/fs/cgroup') / state['ControlGroup'].lstrip('/')
        pids = {int(p) for file in [root / 'cgroup.procs', *root.rglob('cgroup.procs')]
                for p in file.read_text().split()}
        processes = []
        for pid in sorted(pids):
            proc = Path('/proc') / str(pid)
            try:
                if (proc / 'comm').read_text().strip() != 'simv':
                    continue
                exe = (proc / 'exe').resolve(strict=True)
                cwd = (proc / 'cwd').resolve(strict=True)
                argv = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode()
            except (FileNotFoundError, ProcessLookupError):
                continue
            base.require(exe == base.IMAGE / '_build/vcs/simv', 'Owned simv image differs')
            base.require(cwd.is_relative_to(out / 'groups/group00'), 'Not the isolated pilot')
            processes.append(dict(pid=pid, exe=str(exe), cwd=str(cwd), argv=argv))
        base.require(len(processes) == 1, 'Expected exactly one live pilot simv')
        base.require(base.sha(base.IMAGE / 'image.json') == base.IMAGE_SHA, 'Startup image drift')
        base.require(not list(out.rglob('firstfailure.json')), 'Failure evidence at startup')
        result = dict(status='PILOT_LIVE_CONFIRMED_ONCE_NOT_PASS', unit=unit, state=state,
                      simv=processes, trace=str(path), first_row=first, later_row=last,
                      growth_window_s=time.monotonic()-first_time, observed_unix=time.time(),
                      further_polling=False)
        base.save(out / 'startup_observation.json', result)
        print(result['status'], processes[0]['pid'], first['cycle'], last['cycle'], flush=True)
    finally:
        if stream is not None:
            stream.close()
        events.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--unit', required=True)
    a = p.parse_args()
    confirm(a.out.resolve(), a.unit)
