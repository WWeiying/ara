#!/usr/bin/env python3
"""Successor product gate: explicit pre-port reference and bounded/exhaustive modes.

Original product/borrow workers and their pinned helper remain untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from run_product import (DEPENDENCIES, HEADERS, MULTIPLIERS, OUT, PACKAGES,
                         command, reference_copy, save, sha, verify)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REFERENCE = 'b0156f8ab6b86db0de9b44f47d1de4afb052762d'
BASE_TB_SHA256 = 'a832790d583355bc3bda07e491270cf7b8bd8c97abfe5933d1bdfd6b8608a00b'
LOCAL = ('product_tb.sv', 'run_product.py', 'run_product_v2.py', 'test_run_product_v2.py')


def bench(raw):
    if hashlib.sha256(raw).hexdigest() != BASE_TB_SHA256:
        raise ValueError('Original frozen product TB changed')
    text = raw.decode()
    replacements = (
        ('if(Sew==0) begin', 'if(Sew==0 && $test$plusargs("EXHAUSTIVE")) begin'),
        ('n<12000', 'n<6000'), ('n==6000', 'n==3000'), ('n==6002', 'n==3002'),
        ('$display("STAGE2_PRODUCT_PASS configurations=24 shared_no_bypass=3");',
         '$display("STAGE2_PRODUCT_V2_PASS configurations=24 shared_no_bypass=3 exhaustive=%0d", $test$plusargs("EXHAUSTIVE"));'))
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError('Ambiguous bounded TB anchor: ' + old)
        text = text.replace(old, new)
    return text


def check_log(text, exhaustive=False):
    if re.search(r'(?im)(?:fatal|error|assertion failed|timeout)', text):
        raise ValueError('Product simulator failure')
    marker = f'STAGE2_PRODUCT_V2_PASS configurations=24 shared_no_bypass=3 exhaustive={int(exhaustive)}'
    if text.count(marker) != 1 or text.count('STAGE2_PRODUCT_V2_PASS') != 1:
        raise ValueError('Missing/duplicate/wrong-mode completion')
    pattern = (r'^PRODUCT_CASE id=(\d+) shared=(\d+) sew=(\d+) pipes=(\d+) bypass=(\d+) '
               r'accepted=(\d+) retired=(\d+) flushed=(\d+) checks=(\d+) stalled=(\d+)$')
    rows = [tuple(map(int, match)) for match in re.findall(pattern, text, re.M)]
    if len(rows) != 27 or len(re.findall(r'^PRODUCT_CASE', text, re.M)) != 27 or {r[0] for r in rows} != set(range(27)):
        raise ValueError('Missing/duplicate/malformed configuration')
    for identity, shared, sew, pipes, bypass, accepted, retired, flushed, checks, stalled in rows:
        expected = (identity // 12, 8 << ((identity % 12) // 3), identity % 3, 1) if identity < 24 else (1, 8, identity - 24, 0)
        if (shared, sew, pipes, bypass) != expected:
            raise ValueError('Wrong configuration geometry')
        minimum = 199168 if exhaustive and sew == 8 else 2560
        if accepted != retired + flushed or retired < minimum or checks < retired or stalled == 0:
            raise ValueError('Insufficient checks or broken accounting')
        if pipes > 0 and (not shared or not bypass or sew != 8) and flushed == 0:
            raise ValueError('No pending reset coverage')
    return dict(configurations=24, shared_no_bypass=3, byte_pair_exhaustive=exhaustive,
                random_cycles_per_configuration=6000,
                accepted=sum(r[5] for r in rows), retired=sum(r[6] for r in rows),
                flushed=sum(r[7] for r in rows), checks=sum(r[8] for r in rows))


def prepare(out, reference=REFERENCE, exhaustive=False):
    if out.parent != OUT:
        raise ValueError('Use a unique direct signoff output child')
    if subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'], text=True).strip() != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong signoff worktree')
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--verify', reference + '^{commit}'], text=True).strip()
    originals = {rel: subprocess.check_output(['git', '-C', str(ROOT), 'show', revision + ':' + rel]) for rel in MULTIPLIERS}
    renamed = {rel: reference_copy(data, Path(rel).stem) for rel, data in originals.items()}
    vcs = shutil.which('vcs')
    if not vcs:
        raise ValueError('No host VCS')
    transformed = bench((HERE / 'product_tb.sv').read_bytes())
    out.mkdir(exist_ok=False)
    inputs, pins = out / 'inputs', {}
    for rel in (*PACKAGES, *MULTIPLIERS, *DEPENDENCIES, *HEADERS, *(str(HERE.relative_to(ROOT) / n) for n in LOCAL)):
        source, target = ROOT / rel, inputs / rel
        digest = sha(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != digest:
            raise ValueError('Copy race: ' + rel)
        pins[str(source)] = pins[str(target)] = digest
    refs = []
    for rel, content in renamed.items():
        path = inputs / (Path(rel).stem + '_before.sv')
        path.write_bytes(content)
        pins[str(path)] = sha(path)
        refs.append(path)
    tb = inputs / 'product_selected_tb.sv'
    tb.write_text(transformed)
    pins[str(tb)] = sha(tb)
    save(out / 'reference-identity.json', {rel: dict(commit=revision, sha256=hashlib.sha256(data).hexdigest())
                                         for rel, data in originals.items()})
    filelist = inputs / 'sources.f'
    filelist.write_text('+incdir+' + str(inputs / 'hardware/deps/common_cells/include') + '\n' +
        '\n'.join(str(inputs / p) for p in (*PACKAGES, *MULTIPLIERS, *DEPENDENCIES)) + '\n' +
        '\n'.join(map(str, (*refs, tb))) + '\n')
    local = inputs / HERE.relative_to(ROOT)
    config = dict(vcs=vcs, local=str(local), reference=revision, exhaustive=exhaustive,
                  timeout_seconds=1200 if exhaustive else 600,
                  coverage='same integer oracle and legacy comparison; 6000 random cycles; full byte pairs only with --exhaustive')
    save(out / 'selection.json', config)
    for path in (filelist, out / 'reference-identity.json', out / 'selection.json', Path(vcs).resolve()):
        pins[str(path)] = sha(path)
    verify(pins)
    save(out / 'source-pins.json', pins)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', frozen_runner=str(local / 'run_product_v2.py'),
                                    reference=revision, byte_pair_exhaustive=exhaustive))
    print(local / 'run_product_v2.py')


def execute(out):
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_product_v2.py':
        raise ValueError('Execute only the frozen successor runner')
    pins = json.loads((out / 'source-pins.json').read_text())
    work = out / 'work'
    work.mkdir(exist_ok=False)
    deadline = time.monotonic() + config['timeout_seconds']
    report = dict(state='FAIL', scope='standalone products/legacy interfaces only; not VMFPU/SoC/performance acceptance',
                  reference=config['reference'], byte_pair_exhaustive=config['exhaustive'])
    try:
        verify(pins)
        command([sys.executable, '-B', str(Path(config['local']) / 'test_run_product_v2.py')],
                work, work / 'host-tests.log', deadline)
        compile_cmd = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                       '-top', 'stage2_product_tb', '-o', 'simv', '-f', str(out / 'inputs/sources.f')]
        run_cmd = [str(work / 'simv'), '-no_save'] + (['+EXHAUSTIVE'] if config['exhaustive'] else [])
        save(work / 'commands.json', dict(compile=compile_cmd, run=run_cmd))
        print('STAGE2_PRODUCT_V2_COMPILING', flush=True)
        command(compile_cmd, work, work / 'compile.log', deadline)
        verify(pins)
        image = {str(p): sha(p) for p in (work / 'simv.daidir').rglob('*') if p.is_file()}
        image[str(work / 'simv')] = sha(work / 'simv')
        save(work / 'image-pins.json', image)
        print('STAGE2_PRODUCT_V2_RUNNING', flush=True)
        command(run_cmd, work, work / 'run.log', deadline)
        report['work'] = check_log((work / 'run.log').read_text(), config['exhaustive'])
        verify(pins)
        verify(image)
        save(out / 'source-pins-after.json', pins)
        report.update(state='PASS', post_pins_match=True, post_image_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): sha(p) for p in work.glob('*') if p.is_file()}
    save(out / 'report.json', report)
    print('STAGE2_PRODUCT_V2_' + report['state'] + ' ' + str(out / 'report.json'), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--reference', default=REFERENCE)
    parser.add_argument('--exhaustive', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        return execute(args.output.resolve())
    prepare(args.output.resolve(), args.reference, args.exhaustive)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
