#!/usr/bin/env python3
"""Offline full24 audit. No simulator, build, worker, or capacity gate invocation."""
import concurrent.futures
import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import vcs_adapter as old
from support import accepted_helpers, read, save

SOURCE = HERE.parent / 'vcs_plan06'
PLAN_SHA = 'edc7b0e20d0ef1cbf99b978421b8ca5df1eb9ce6505ec22e3bbc69db3e901839'
UNIT = 'ara-indexed-nf7-candidate02-06.service'
OUT = HERE / 'results'
sha = old.ref.base.sha
require = old.require


def normalized(value):
    return json.loads(json.dumps(value))


def no_abort(end):
    require(end['status'] == 'NF7_FULL96_PASS', 'Aggregate not PASS')
    require('firstfailure' in end and end['firstfailure'] is None, 'Aggregate abort/firstfailure')
    require(not list(SOURCE.rglob('firstfailure.json')), 'Firstfailure artifact exists')
    require(end['post_hashes'] == 'UNCHANGED', 'Original post-run identity failure')
    require(set(end['groups']) == {str(g) for g in range(24)}, 'Aggregate membership')


def check_elapsed(value, limit):
    require(isinstance(value, (int, float)) and math.isfinite(value) and 0 < value < limit,
            f'Elapsed {value!r} violates strict {limit}s bound')


def no_owned_processes():
    owners = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != os.getuid():
                continue
            comm = (p / 'comm').read_text().strip()
            cgroup = (p / 'cgroup').read_text()
            argv = (p / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        except (FileNotFoundError, ProcessLookupError):
            continue
        owned = UNIT in cgroup or str(SOURCE) in argv or 'successor_resources06.py worker' in argv
        if owned:
            owners.append(dict(pid=int(p.name), comm=comm, cgroup=cgroup, argv=argv))
    require(not owners, 'Residual NF7-owned process: ' + repr(owners))
    return owners


def terminal_observation():
    keys = ('LoadState', 'ActiveState', 'MainPID', 'Result', 'ExecMainCode',
            'ExecMainStatus', 'ControlGroup', 'InactiveEnterTimestamp', 'ExecMainExitTimestamp')
    command = ['systemctl', '--user', 'show', UNIT]
    for k in keys:
        command += ['-p', k]
    raw = subprocess.check_output(command, text=True, timeout=10)
    state = dict(line.split('=', 1) for line in raw.splitlines())
    require(state['ActiveState'] == 'inactive' and state['MainPID'] == '0', 'NF7 unit not inactive')
    require(state['LoadState'] in ('loaded', 'not-found'), 'Unexpected unit state')
    if state['LoadState'] == 'loaded':
        require(state['Result'] == 'success' and state['ExecMainStatus'] == '0', 'Unit failed')
    return dict(command=command, raw=raw, state=state, residual_owners=no_owned_processes(),
                historical_service_result_source='Parent explicit terminal report in user request',
                historical_parent_report=dict(Result='success', MainPID=0, status=0),
                limitation='GC defaults are NOT independent evidence of historical service exit success.'
                if state['LoadState'] == 'not-found' else None)


def artifacts(g):
    d = SOURCE / 'groups' / f'g{g:02d}'
    t = d / 'run/tests' / f'nf7_g{g:02d}'
    return [d / n for n in ('complete.json', 'command.json', 'worker.log', 'run/run.json', 'run/summary.json')] + [
        t / n for n in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'commit_trace.csv', 'trace_summary.json')]


def group_metadata(g, plan, end, programs):
    name = f'nf7_g{g:02d}'
    d = SOURCE / 'groups' / f'g{g:02d}'
    t = d / 'run/tests' / name
    source = old.reference_directory(g)
    result = read(d / 'complete.json')
    require(result == end['groups'][str(g)], 'Group/aggregate disagreement')
    require(result['status'] == 'PASS' and result['returncode'] == 0 and result['group'] == g,
            'Group did not complete successfully')
    check_elapsed(result['elapsed_s'], 2700)
    summary = read(d / 'run/summary.json')
    require(summary == result['summary'] and len(summary) == 1, 'Runner/group summary mismatch')
    row = summary[0]
    require(row['name'] == name and row['status'] == 'PASS' and row['returncode'] == 0 and
            row['reason'] == '' and row['artifact_dir'] == str(t), 'Runner not an exact successful case')
    check_elapsed(row['elapsed_s'], 2400)
    run = read(d / 'run/run.json')
    for k, v in dict(status='COMPLETE', tests=[name], status_counts={'PASS': 1}, jobs=1,
                     timeout_s=2400, seed=1, commit_trace=True, input_snapshots=True,
                     simv=str(old.IMAGE / '_build/vcs/simv')).items():
        require(run[k] == v, 'Runner metadata differs: ' + k)
    command = old.command(SOURCE, g, True)
    require(read(d / 'command.json') == command and run['invocation'] == command[2:], 'Runner invocation differs')
    entry = programs[name]
    inputs = read(t / 'inputs.json')
    expected_sha = read(source / 'status.json')['elf_sha256']['soc']
    require(entry['path'] == str(source / 'soc.elf') and entry['cases'] == list(range(g*4, g*4+4)),
            'Source ELF membership differs')
    require(entry['sha256'] == inputs['binary']['sha256'] == sha(t / 'input.elf') ==
            sha(source / 'soc.elf') == expected_sha, 'Private ELF identity differs')
    require(inputs['binary']['source'] == entry['path'] and inputs['binary']['path'] == str(t / 'input.elf'),
            'Private input source differs')
    require(inputs['simv']['path'] == run['simv'] and inputs['simv']['image_sha256'] == plan['image_files'],
            'Runner image differs from pinned M2')
    expected_cmd = [run['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                    '+PRELOAD=' + str(t / 'input.elf'), '+TESTCASE=' + name, '+NO_FSDB',
                    '+COMMIT_TRACE=' + str(t / 'commit_trace.csv')]
    require(read(t / 'command.json') == dict(command=expected_cmd, cwd=str(t / 'work')),
            'Actual simulator invocation differs')
    console = (t / 'console.log').read_text()
    require(console.count('IX_SV39_PASS') == 1 and 'Core Test *** SUCCESS *** (tohost = 0)' in console and
            '$finish called from file' in console, 'Missing fixture/simulator success')
    require(str(t / 'input.elf') in console and 'current_board_memory_candidate02/frozen/sources/hardware/tb/ara_tb.sv' in console,
            'Console ELF/image provenance differs')
    for path in (t / 'console.log', d / 'worker.log', SOURCE / 'service.log'):
        require(not re.search(r'IX_SV39_FAIL|\b(?:FAIL|FAILED|CANCELLED|TIMEOUT|SIGTERM|SIGINT|Traceback|Fatal)\b',
                              path.read_text()), 'Failure/cancellation in ' + str(path))
    return dict(group=g, trials=entry['cases'], group_elapsed_s=result['elapsed_s'],
                runner_elapsed_s=row['elapsed_s'], private_elf_sha256=expected_sha)


def replay(g):
    start = time.monotonic()
    source = old.reference_directory(g)
    t = SOURCE / 'groups' / f'g{g:02d}' / 'run/tests' / f'nf7_g{g:02d}'
    checker = old.csv_oracle.Checker(read(source / 'soc.symbols.json'), read(source / 'cases.json'),
                                   read(source / 'status.json'), read(SOURCE / 'ledgers' / f'g{g:02d}.json'))
    rows = retires = 0
    last_pc = None
    with (t / 'commit_trace.csv').open() as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == old.csv_oracle.FIELDS, 'CSV header differs')
        for row in reader:
            checker.row(row)
            rows += 1
            if row['event'] == 'retire':
                retires += 1
                last_pc = row['pc']
    fresh = normalized(checker.finish())
    saved = read(SOURCE / 'groups' / f'g{g:02d}' / 'complete.json')['analysis']
    require(fresh == saved, 'Offline/online oracle differs for group ' + str(g))
    trace_summary = read(t / 'trace_summary.json')
    require(trace_summary['status'] == 'VALID' and trace_summary['rows'] == rows and
            trace_summary['retire_count'] == retires and trace_summary['last_cycle'] == fresh['last_cycle'],
            'Independent CSV counters differ')
    result = dict(status='FULL_CSV_RECOMPUTE_MATCH', group=g, analysis=fresh,
                  rows=rows, retires=retires, last_retiring_pc=last_pc, elapsed_s=time.monotonic()-start)
    save(OUT / f'g{g:02d}.json', result)
    return result


def main():
    OUT.mkdir()
    started = time.monotonic()
    save(OUT / 'service_observation.json', terminal_observation())
    require(sha(SOURCE / 'plan.json') == PLAN_SHA, 'Wrong accepted plan')
    plan = read(SOURCE / 'plan.json')
    end = read(SOURCE / 'complete.json')
    no_abort(end)
    require(plan['groups'] == list(range(24)) and plan['trials'] == list(range(96)), 'Plan scope differs')
    require(plan['max_jobs'] == 2 and plan['group_timeout_s'] == 2400 and plan['group_outer_s'] == 2700,
            'Original orchestration budgets differ')
    require(end['plan_sha256'] == read(SOURCE / 'worker.json')['plan_sha256'] == PLAN_SHA, 'Worker/aggregate plan differs')
    require(end['image_sha256'] == plan['image_sha256'] == old.IMAGE_SHA == sha(old.IMAGE / 'image.json'), 'Not original M2')
    old.verify(plan['pins'])
    helper = accepted_helpers()
    image = helper.check_image()
    require(image['files'] == plan['image_files'], 'Image membership differs')
    reference = old.accepted_references()
    require(reference == read(SOURCE / 'reference_acceptance.json'), 'Accepted full96 reference differs')
    programs = read(SOURCE / 'programs/programs.json')['programs']
    require(set(programs) == {f'nf7_g{g:02d}' for g in range(24)}, 'Programs membership differs')
    require({p.name for p in (SOURCE / 'groups').iterdir()} == {f'g{g:02d}' for g in range(24)}, 'Group directory membership differs')
    metadata = [group_metadata(g, plan, end, programs) for g in range(24)]
    paths = [SOURCE / n for n in ('plan.json', 'worker.json', 'complete.json', 'service.log', 'startup_observation.json')]
    paths += [p for g in range(24) for p in artifacts(g)] + [Path(__file__)]
    pins = {str(p): sha(p) for p in paths}
    save(OUT / 'evidence_pins.json', pins)
    save(OUT / 'preflight.json', dict(status='OFFLINE_AUDIT_PREFLIGHT_PASS', groups=metadata,
         plan_pins=len(plan['pins']), image_files=len(image['files']), frozen_sources=539,
         source_plan_sha256=PLAN_SHA, image_sha256=old.IMAGE_SHA))
    print('Preflight PASS; full24 CPU-only CSV recomputation starting', flush=True)
    results = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(replay, g): g for g in range(24)}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results[result['group']] = result
            print(f"Group {result['group']:02d}: full CSV exact match, {result['analysis']['checks']} checks", flush=True)
    require(sorted(results) == list(range(24)), 'Incomplete recomputation')
    old.verify(pins)
    old.verify(plan['pins'])
    require(helper.check_image() == image, 'Post-audit image drift')
    no_abort(read(SOURCE / 'complete.json'))
    no_owned_processes()
    save(OUT / 'complete.json', dict(status='NF7_M2_FULL96_INDEPENDENT_CSV_AUDIT_PASS',
         scope='Source-derived original NF7 96 trials on frozen candidate02 only; not Linux replay, M4, or current RTL validation.',
         service_exit_evidence='Parent-reported terminal success; independently observed GC/not-found, not inferred historical exit code.',
         groups=metadata, trials=[t for g in range(24) for t in results[g]['analysis']['trials']],
         checks=sum(v['analysis']['checks'] for v in results.values()),
         checkpoints=sum(len(v['analysis']['checkpoints']) for v in results.values()),
         traps=sum(len(v['analysis']['traps']) for v in results.values()),
         rows=sum(v['rows'] for v in results.values()), retires=sum(v['retires'] for v in results.values()),
         plan_sha256=PLAN_SHA, image_sha256=old.IMAGE_SHA, firstfailure=None,
         pre_post_pins='UNCHANGED', elapsed_s=time.monotonic()-started))
    print('NF7_M2_FULL96_INDEPENDENT_CSV_AUDIT_PASS', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if OUT.exists() and not (OUT / 'failure.json').exists():
            save(OUT / 'failure.json', dict(status='NOT_ACCEPTED', error=repr(error)))
        raise
