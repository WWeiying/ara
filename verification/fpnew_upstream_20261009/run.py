#!/usr/bin/env python3
"""Frozen actual-DUT VCS runs, with an independent Spike SoftFloat oracle."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import oracle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OPS = dict(fma=0, mul=3, div=4, sqrt=5, cast=10, f2i=11, i2f=12)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(rows, trace, console, flush, stress=False):
    expected = list(rows)
    if flush:
        expected += [dict(id=100000+d, unit=5, expected=0x4008000000000000,
                          mask=(1 << 64)-1, flags=0, group='flush_recovery')
                     for d in (0, 1, 2, 3, 1099)]
    if stress:
        expected += [dict(r, id=200000+r['id']+u*10000) for u in range(5)
                     for r in rows if r['unit'] == u and r['id'] % 7 == 0]
        expected += [dict(id=300000+u, unit=u, mask=(1 << 64)-1, flags=0,
                         expected=0xffffffff3f800000 if u == 2 else
                         0xffffffffffff3c00 if u == 4 else 0x3ff0000000000000,
                         group='reset_recovery') for u in range(6)]
    actual = list(csv.DictReader(trace.splitlines()))
    if len(actual) != len(expected):
        raise ValueError(f'trace count {len(actual)} expected {len(expected)}')
    failures = []
    for wanted, got in zip(expected, actual):
        if (int(got['id']), int(got['unit']), int(got['tag'])) != (
                wanted['id'], wanted['unit'], wanted['id']):
            raise ValueError('ID/unit/tag mismatch')
        mismatch = ((int(got['result'], 16) & wanted['mask']) != wanted['expected'] or
                    int(got['flags'], 16) != wanted['flags'])
        if int(got['mismatch']) != int(mismatch):
            raise ValueError('SV/independent host checker disagree')
        if mismatch:
            failures.append(dict(case=wanted, measured=got))
    if not re.search(rf'^COMPLETE cases={len(expected)} bad=\d+$', console, re.M):
        raise ValueError('missing complete marker')
    if re.search(r'Fatal|Error-|Error:|Assertion.*fail|TIMEOUT', console):
        raise ValueError('simulation diagnostic')
    if flush:
        events = re.findall(r'^FLUSH delay=(\d+) vector=(\d+) func=([01]) op=([01]) done=([01]) bad=(\d+)$', console, re.M)
        if [(int(x[0]), int(x[1])) for x in events] != [(0, 0), (1, 0), (2, 0), (3, 0), (99, 1)]:
            raise ValueError('missing flush checks')
        failures += [dict(flush_event=e) for e in events if e[-1] != '0']
    if stress:
        events = re.findall(r'^STREAM unit=(\d+) sent=(\d+) received=(\d+) max_inflight=(\d+) blocked=(\d+)$', console, re.M)
        for u in range(5):
            n = sum(r['unit'] == u and r['id'] % 7 == 0 for r in rows)
            matches = [e for e in events if int(e[0]) == u]
            if n and (len(matches) != 1 or tuple(map(int, matches[0][1:3])) != (n, n)
                      or int(matches[0][3]) < 2 or int(matches[0][4]) == 0):
                raise ValueError('stream pressure/count missing')
        resets = re.findall(r'^RESET unit=(\d+) canceled=1 ghost=0$', console, re.M)
        if resets != list(map(str, range(6))):
            raise ValueError('reset checks missing')
    return failures


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--flush', action='store_true')
    p.add_argument('--stress', action='store_true')
    p.add_argument('--group', help='optional comma-separated oracle groups')
    p.add_argument('--rtl-snapshot', type=Path, help='existing frozen inputs/ tree, never live mutation')
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs = out / 'inputs'
    deps = args.rtl_snapshot.resolve() if args.rtl_snapshot else ROOT/'hardware/deps'
    fpnew = deps/'fpnew'
    common = deps/'common_cells'
    for name, src in [('fpnew/src', fpnew/'src'), ('fpnew/vendor/openc910', fpnew/'vendor/openc910'),
                      ('common_cells/include', common/'include')]:
        shutil.copytree(src, inputs/name)
    cc = inputs/'common_cells/src'
    cc.mkdir()
    for name in ('cf_math_pkg.sv', 'lzc.sv'):
        shutil.copy2(common/'src'/name, cc/name)
    fixture = inputs/'fixture'
    fixture.mkdir()
    for name in ('run.py', 'oracle.py', 'upstream_tb.sv'):
        shutil.copy2(HERE/name, fixture/name)
    shutil.copy2(oracle.LIB, inputs/'libsoftfloat.so')
    rows = oracle.cases(inputs/'libsoftfloat.so')
    if args.group:
        groups = set(args.group.split(','))
        rows = [r for r in rows if r['group'] in groups]
    if not rows:
        raise ValueError('empty suite')
    (out/'cases.json').write_text(json.dumps(rows, indent=2)+'\n')
    lines = []
    for r in rows:
        src = r['src'] if r['op'] != 'i2f' else r['dst']
        dst = r['dst'] if r['op'] != 'f2i' else r['src']
        iw = r['src'] if r['op'] == 'i2f' else (r['dst'] if r['op'] == 'f2i' else 32)
        fields = [r['id'], r['unit'], OPS[r['op']], oracle.FMT[src], oracle.FMT[dst],
                  oracle.INTFMT[iw], int(r['unsigned']), r['rm']]
        lines.append(' '.join(map(str, fields)) + ' ' + ' '.join(
            f'{r[k] & ((1<<64)-1):016x}' for k in ('a', 'b', 'c', 'expected', 'mask'))
                     + f' {r["flags"]:02x}')
    (out/'cases.txt').write_text('\n'.join(lines)+'\n')
    hashes = {str(f.relative_to(out)): sha(f) for f in sorted(inputs.rglob('*')) if f.is_file()}
    hashes.update({n: sha(out/n) for n in ('cases.json', 'cases.txt')})
    (out/'sources.json').write_text(json.dumps(hashes, indent=2)+'\n')
    srcs = [cc/'cf_math_pkg.sv', inputs/'fpnew/src/fpnew_pkg.sv', cc/'lzc.sv']
    srcs += [inputs/'fpnew/src'/n for n in ('fpnew_classifier.sv', 'fpnew_rounding.sv',
        'fpnew_cast_multi.sv', 'fpnew_fma.sv', 'fpnew_fma_multi.sv', 'fpnew_divsqrt_th_64_multi.sv')]
    srcs += sorted((inputs/'fpnew/vendor/openc910').rglob('*.v'))
    srcs += [fixture/'upstream_tb.sv']
    command = ['vcs', '-full64', '-sverilog', '-assert', 'svaext', '-timescale=1ns/1ps',
               f'+incdir+{inputs}/common_cells/include', '-top', 'upstream_tb',
               *map(str, srcs), '-o', 'simv', '-l', 'compile.log']
    (out/'command.json').write_text(json.dumps(command, indent=2)+'\n')
    with (out/'compile.console').open('w') as f:
        subprocess.run(command, cwd=out, stdout=f, stderr=subprocess.STDOUT, timeout=300, check=True)
    with (out/'run.console').open('w') as f:
        result = subprocess.run([str(out/'simv'), '-l', 'run.log'] + ([] if args.flush else ['+ARITH_ONLY'])
                                + (['+STRESS'] if args.stress else []),
                                cwd=out, stdout=f, stderr=subprocess.STDOUT, timeout=120)
    report = dict(status='FAIL', oracle='Spike SoftFloat, tininess after rounding',
                  cases=len(rows), returncode=result.returncode, binary_sha256=sha(out/'simv'))
    try:
        errors = audit(rows, (out/'trace.csv').read_text(), (out/'run.log').read_text(), args.flush, args.stress)
        report.update(status='FAIL' if errors or result.returncode else 'PASS', failures=errors)
    except ValueError as e:
        report['audit_error'] = str(e)
    report['frozen_sources_unchanged'] = all(sha(out/n) == h for n, h in hashes.items())
    if not report['frozen_sources_unchanged']:
        report['status'] = 'FAIL'
    (out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'failures'}, indent=2))
    print('mismatches', len(report.get('failures', [])))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
