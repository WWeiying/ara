#!/usr/bin/env python3
"""Freeze, generate, and optionally run a bounded host-VCS resident-PV gate.

Default is host-only preparation. --module-ready explicitly enables VCS.
Every invocation requires a new output directory; no report is overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MANIFEST = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/'
                'chain_soc_20261107_01/source-pins.json')
LIBRARY = Path('/home/wangwy/software/toolchains/spike/lib/libsoftfloat.so')
SOURCES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_classifier.sv',
    'hardware/deps/fpnew/src/fpnew_rounding.sv',
    'hardware/deps/fpnew/src/fpnew_fma.sv',
    'hardware/deps/fpnew/src/fpnew_noncomp.sv',
    'hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv',
]
CASE_PATTERN = re.compile(
    r'^PV_CASE_PASS id=(\d+) mode=(\d+) seeds=(\d+) packets=(\d+) issued=(\d+) '
    r'returned=(\d+) commits=(\d+) flags=(\d+) cycles=(\d+)$', re.M)
PASS_PATTERN = re.compile(
    r'^PV_UNIT_PASS cases=(\d+) done=(\d+) reset=(\d+) issued=(\d+) returned=(\d+) '
    r'cancelled=(\d+) commits=(\d+) cycles=(\d+) pipe=(\d+)$', re.M)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, data):
    with Path(path).open('x') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write('\n')


def verify(pins):
    actual = {name: sha(name) for name in pins}
    drift = [name for name in pins if actual[name] != pins[name]]
    if drift:
        raise ValueError('Source/artifact drift: '+', '.join(drift))
    return actual


def dependency_selection(pins):
    selected = {}
    headers = set()
    for name in pins:
        marker = '/hardware/deps/common_cells/include/'
        if marker in name:
            headers.add('hardware/deps/common_cells/include/'+name.split(marker, 1)[1])
    if not headers:
        raise ValueError('Frozen common_cells headers missing')
    for relative in SOURCES + sorted(headers):
        candidates = sorted(name for name in pins if name.endswith('/'+relative))
        if not candidates or len({pins[name] for name in candidates}) != 1:
            raise ValueError('Missing/conflicting frozen dependency: '+relative)
        for name in candidates:
            if '/verification/out/' not in name or '/source/hardware/deps/' not in name:
                raise ValueError('Refusing live dependency: '+name)
            if sha(name) != pins[name]:
                raise ValueError('Frozen dependency drift: '+name)
        selected[relative] = candidates
    return selected


def snapshot(out, args):
    manifest_hash = sha(args.manifest)
    baseline = json.loads(args.manifest.read_text())
    selected = dependency_selection(baseline)
    originals = {str(args.manifest): manifest_hash, str(args.library): sha(args.library)}
    inputs = out/'inputs'
    inputs.mkdir()
    provenance = {}
    for relative, candidates in selected.items():
        for name in candidates:
            originals[name] = baseline[name]
        dest = inputs/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidates[0], dest)
        if sha(dest) != baseline[candidates[0]]:
            raise ValueError('Copy identity mismatch: '+relative)
        provenance[relative] = dict(source=candidates[0], aliases=candidates,
                                    sha256=baseline[candidates[0]])
    local = [HERE/'generate_vectors.py', HERE/'run.py', HERE/'test_generator.py',
             HERE/'tb.sv', HERE/'README.md', HERE.parent/'ordered_reference.py',
             ROOT/'verification/fpnew_upstream_20261009/oracle.py']
    if args.module_ready:
        local.append(HERE/'akv_resident_pv_lane.sv')
    for path in local:
        originals[str(path)] = sha(path)
        dest = inputs/path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        if sha(dest) != originals[str(path)]:
            raise ValueError('Local input changed while copying: '+str(path))
    shutil.copyfile(args.library, inputs/'libsoftfloat.so')
    if sha(inputs/'libsoftfloat.so') != originals[str(args.library)]:
        raise ValueError('SoftFloat copy changed')
    if args.real_json:
        originals[str(args.real_json)] = sha(args.real_json)
        payload = json.loads(args.real_json.read_text())
        if not payload.get('artifacts') or not payload.get('cases'):
            raise ValueError('Real corpus lacks artifact pins or cases')
        for name, digest in payload['artifacts'].items():
            if not Path(name).is_absolute() or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('Invalid real artifact pin')
            if name in originals and originals[name] != digest:
                raise ValueError('Real artifact conflicts with selected oracle')
            originals[name] = digest
        shutil.copyfile(args.real_json, inputs/'real.json')
        if sha(inputs/'real.json') != originals[str(args.real_json)]:
            raise ValueError('Real corpus copy changed')
    verify(originals)
    save(out/'dependency-provenance.json', provenance)
    save(out/'original-pins.json', originals)
    return originals


def command(argv, cwd, log, seconds):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    # GNU timeout also bounds compiler children; each command gets a separate log.
    with log.open('x') as f:
        result = subprocess.run(['timeout', '--signal=TERM', '--kill-after=10s',
                                 str(seconds), *argv], cwd=cwd, env=env,
                                stdout=f, stderr=subprocess.STDOUT)
    text = log.read_text(errors='replace')
    if result.returncode or re.search(r'(?m)^(Error-|Error:|Fatal:|FATAL|\s*\$fatal)', text):
        raise RuntimeError(f'Command failed rc={result.returncode}: {log}')
    return text


def check_log(text, corpus, pipe):
    parsed = [tuple(map(int, m)) for m in CASE_PATTERN.findall(text)]
    terminal = PASS_PATTERN.findall(text)
    expected = corpus['cases_by_id']
    if len(parsed) != len(expected) or [r[0] for r in parsed] != list(range(len(expected))):
        raise ValueError('Missing, duplicate, or out-of-order per-case PASS records')
    if len(terminal) != 1:
        raise ValueError('Missing/duplicate final PASS record')
    totals = tuple(map(int, terminal[0]))
    cancelled = 0
    names = ('id', 'mode', 'seeds', 'packets', 'issued', 'returned', 'commits', 'flags', 'cycles')
    records = []
    for values, case in zip(parsed, expected):
        row = dict(zip(names, values))
        row['name'] = case['name']
        nwords = (case['elements']+3)//4
        slots = nwords*case['heads']
        if row['mode'] != case['mode'] or row['cycles'] <= 0 or row['returned'] > row['issued']:
            raise ValueError('Inconsistent case accounting')
        if case['mode'] == 0:
            if (row['seeds'], row['packets'], row['issued'], row['returned'], row['commits'], row['flags']) != (
                    slots, case['tokens']*(nwords+1), case['tokens']*slots,
                    case['tokens']*slots, slots, case['fma_flags']):
                raise ValueError('Normal case incomplete or flags mismatch: '+case['name'])
        elif case['mode'] == 1:
            if any(row[k] for k in ('seeds', 'packets', 'issued', 'returned', 'commits', 'flags')):
                raise ValueError('Invalid command transferred data')
        elif case['mode'] in (2, 4):
            if row['commits'] or row['issued'] != row['returned']:
                raise ValueError('Fault failed to drain or committed data')
        else:
            cancelled += row['issued']-row['returned']
        records.append(row)
    wanted = (len(expected), sum(c['mode'] != 3 for c in expected),
              sum(c['mode'] == 3 for c in expected), sum(r['issued'] for r in records),
              sum(r['returned'] for r in records), cancelled,
              sum(r['commits'] for r in records), sum(r['cycles'] for r in records), pipe)
    if totals != wanted or totals[3] != totals[4]+totals[5]:
        raise ValueError('Final count mismatch')
    coverage = re.findall(r'^PV_COVERAGE (.+)$', text, re.M)
    if len(coverage) != 1:
        raise ValueError('Missing/duplicate coverage record')
    counters = dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', coverage[0]))
    required = ('request_stalls', 'stream_stalls', 'result_stalls', 'done_stalls', 'raw_stalls',
                'reordered', 'simultaneous', 'reset_pending', 'abort_pending', 'malformed_pending')
    if any(counters.get(k, 0) <= 0 for k in required):
        raise ValueError('Required handshake/error scenario unexercised')
    return dict(pipe=pipe, cases=records, totals=dict(zip(
        ('cases', 'done', 'reset', 'issued', 'returned', 'cancelled', 'commits', 'cycles', 'pipe'), totals)),
        coverage=counters)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--module-ready', action='store_true')
    p.add_argument('--manifest', type=Path, default=MANIFEST)
    p.add_argument('--library', type=Path, default=LIBRARY)
    p.add_argument('--real-json', type=Path)
    p.add_argument('--latencies', nargs='+', type=int, choices=(1, 3, 5), default=[3])
    p.add_argument('--random-cases', type=int, default=32)
    p.add_argument('--seed', type=lambda s: int(s, 0), default=0x505631)
    p.add_argument('--compile-seconds', type=int, default=180)
    p.add_argument('--run-seconds', type=int, default=180)
    a = p.parse_args()
    if a.random_cases < 0 or min(a.compile_seconds, a.run_seconds) < 1 or max(a.compile_seconds, a.run_seconds) > 600:
        p.error('Nonnegative random count and bounded timeouts (1..600) required')
    if len(set(a.latencies)) != len(a.latencies):
        p.error('Duplicate pipeline configuration')
    a.manifest=a.manifest.resolve(strict=True); a.library=a.library.resolve(strict=True)
    if a.real_json:
        a.real_json=a.real_json.resolve(strict=True)
    out=a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins = {}
    report = dict(state='FAIL', scope='Isolated resident-PV controller; not SoC or FPGA acceptance',
                  synthesis=False, simulator='host VCS', configurations=[])
    try:
        print('PV_PREPARING '+str(out), flush=True)
        pins = snapshot(out, a)
        inputs=out/'inputs'
        here=inputs/HERE.relative_to(ROOT)
        before={**pins, **{str(f): sha(f) for f in inputs.rglob('*') if f.is_file()}}
        save(out/'preparation-pins-before.json', verify(before))
        argv=[sys.executable, '-B', str(here/'generate_vectors.py'), str(out/'vectors'),
              '--library', str(inputs/'libsoftfloat.so'), '--random-cases', str(a.random_cases),
              '--seed', str(a.seed)]
        if a.real_json:
            argv += ['--real-json', str(inputs/'real.json')]
        save(out/'generation-command.json', argv)
        command(argv, out, out/'generation.log', 180)
        verify(before)
        corpus=json.loads((out/'vectors/vectors.json').read_text())
        report.update(cases=corpus['cases'], real_cases=corpus['real_cases'])
        pins={**before, **{str(f): sha(f) for f in (out/'vectors').rglob('*') if f.is_file()}}
        save(out/'source-pins.json', pins)
        save(out/'source-pins-before.json', verify(pins))
        if a.module_ready:
            vcs=shutil.which('vcs')
            if not vcs:
                raise ValueError('Host VCS not on PATH')
            save(out/'tool.json', dict(vcs=vcs, resolved=str(Path(vcs).resolve()), sha256=sha(vcs)))
            for latency in a.latencies:
                work=out/f'pipe{latency}'
                work.mkdir()
                compile_cmd=[vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
                    '-top', 'resident_pv_tb', '-o', 'simv',
                    f'-pvalue+resident_pv_tb.PipeRegs={latency}',
                    '+incdir+'+str(inputs/'hardware/deps/common_cells/include'),
                    *[str(inputs/relative) for relative in SOURCES],
                    str(here/'akv_resident_pv_lane.sv'), str(here/'tb.sv')]
                run_cmd=[str(work/'simv'), '-no_save', '+VECTORS='+str(out/'vectors/vectors.txt')]
                save(work/'commands.json', dict(compile=compile_cmd, run=run_cmd))
                save(work/'pins-before.json', verify(pins))
                print(f'PV_COMPILING pipe={latency}', flush=True)
                command(compile_cmd, work, work/'compile.log', a.compile_seconds)
                verify(pins)
                image_pin={str(work/'simv'): sha(work/'simv')}
                save(work/'image-pins.json', image_pin)
                print(f'PV_RUNNING pipe={latency}', flush=True)
                text=command(run_cmd, work, work/'run.log', a.run_seconds)
                result=check_log(text, corpus, latency)
                verify(image_pin)
                save(work/'pins-after.json', verify(pins))
                save(work/'report.json', dict(state='PASS', **result))
                report['configurations'].append(result['totals'])
                print(f'PV_PASSED pipe={latency} cases={corpus["cases"]}', flush=True)
            report['state']='PASS'
        else:
            report['state']='PREPARED_NOT_COMPILED'
        save(out/'source-pins-after.json', verify(pins))
    except Exception as exc:
        report.update(state='FAIL', error=str(exc))
        if pins:
            actual={name: sha(name) if Path(name).is_file() else None for name in pins}
            save(out/'failure-pins-after.json', actual)
            report['drift']=[name for name in pins if actual[name] != pins[name]]
    # Bind the receipt to raw evidence, commands, image pins, and checked reports.
    # The final receipt cannot hash itself; it is written exactly once below.
    evidence_dirs = [out, out/'vectors', *[out/f'pipe{n}' for n in a.latencies]]
    report['artifacts'] = {str(f): sha(f) for directory in evidence_dirs if directory.is_dir()
                           for f in sorted(directory.iterdir())
                           if f.is_file() and f.suffix in ('.json', '.log', '.txt')}
    save(out/'report.json', report)
    print(json.dumps(report), flush=True)
    return 1 if report['state']=='FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
