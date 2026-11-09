#!/usr/bin/env python3
"""Bounded host-VCS transport gate using four frozen production operand queues."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
ACCEPTED = OUT / 'resident_pv_vmfpu_20261108_04'
FROZEN = OUT / 'chain_soc_20261107_01/source'
SOURCES = (
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/common_cells/src/fifo_v3.sv',
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/include/rvv_pkg.sv',
    'hardware/include/ara_pkg.sv',
    'hardware/src/lane/operand_queue.sv',
)
HEADER = 'hardware/deps/common_cells/include/common_cells/assertions.svh'
CONTRACTS = ('hardware/src/lane/lane.sv', 'hardware/src/lane/operand_queues_stage.sv')
LOCAL = ('run.py', 'tb.sv', 'README.md', 'test_run.py', 'akv_resident_pv_import.sv')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for name, expected in pins.items():
        if sha(name) != expected:
            raise ValueError('Input identity drift: ' + name)


def collect_artifacts(out, pins):
    # Never digest a still-open service stdout/stderr as a completed artifact.
    paths = {Path(p) for p in pins if Path(p).is_relative_to(out/'inputs')}
    paths.update(out/name for name in (
        'source-pins.json', 'image-pins.json', 'source-selection.json',
        'commands.json', 'tests.log', 'compile.log', 'run.log'))
    return {str(p): sha(p) for p in sorted(paths) if p.is_file()}


def select_sources(filelist, pins, frozen=FROZEN):
    """Select the exact frozen queue closure in admitted compiler order."""
    selected, defines = [], []
    wanted = {str(frozen/p) for p in SOURCES}
    includes = set()
    for raw in filelist.splitlines():
        line = raw.strip()
        if line in wanted:
            if line not in pins:
                raise ValueError('Unpinned selected source: ' + line)
            if line in selected:
                raise ValueError('Duplicate selected source: ' + line)
            selected.append(line)
        elif line.startswith('+incdir+'):
            includes.update(line[len('+incdir+'):].split('+'))
        elif line.startswith('+define+') and line not in defines:
            if line != '+define+TARGET_VERILATOR':
                defines.append(line)
        elif line and not line.startswith(('/', '+define+')):
            raise ValueError('Unsupported admitted file-list entry: ' + line)
    if set(selected) != wanted:
        raise ValueError('Missing same-frozen compiler sources: ' + str(wanted-set(selected)))
    for relative in (HEADER, *CONTRACTS):
        if str(frozen/relative) not in pins:
            raise ValueError('Unpinned header/contract: ' + relative)
    if str(frozen/'hardware/deps/common_cells/include') not in includes:
        raise ValueError('Missing admitted common_cells include directory')
    for define in defines:
        names = {part.split('=')[0] for part in define.split('+')[2:]}
        if names & {'SYNTHESIS', 'TARGET_SRAM_MC', 'UVM', 'ASSERTS_OFF', 'XSIM'}:
            raise ValueError('Unsupported assertion/header configuration: '+define)
    return selected, defines


def check_headers(path):
    headers = re.findall(r'`include\s+"([^"]+)"', path.read_text())
    if headers and (path.name not in ('operand_queue.sv', 'fifo_v3.sv', 'lzc.sv') or
                    set(headers) != {'common_cells/assertions.svh'}):
        raise ValueError('Unexpected include closure: '+str(path))


def check_command_contract(lane, tb):
    def declaration(text):
        match = re.search(r'typedef struct packed\s*\{([^{}]*)\}\s*operand_queue_cmd_t;', text)
        if not match:
            raise ValueError('Missing operand_queue_cmd_t declaration')
        return re.sub(r'\s+', '', re.sub(r'//[^\n]*', '', match[1]))
    if declaration(lane) != declaration(tb):
        raise ValueError('Testbench command differs from frozen lane.sv')


def fields(text):
    pairs = re.findall(r'(\w+)=(\d+)', text)
    result = {k: int(v) for k, v in pairs}
    if len(result) != len(pairs) or ' '.join(f'{k}={v}' for k, v in result.items()) != text:
        raise ValueError('Malformed coverage fields')
    return result


def expected_cases():
    rows = Counter((w, h, t, m, 0) for w in (4, 6, 8) for h in (1, 2)
                   for t in (1, 8, 9, 63, 64) for m in (0, 1, 2))
    for w in (4, 6, 8):
        for h in (1, 2):
            for phase in (1, 2, 3):
                rows[w, h, 1 if phase == 3 else 9, 2, phase] += 1
                rows[w, h, 9, 1, 0] += 1
    return rows


def expected_invalid():
    return Counter([(w, h, 9) for w in range(16) if w not in (4, 6, 8) for h in (1, 2)] +
                   [(w, h, t) for w in (4, 6, 8) for h in (1, 2) for t in (0, 65, 127)])


def check_log(log):
    if re.search(r'(?im)^\s*(?:Error|Fatal|Warning-\[|\$fatal|Assertion.*fail)|ASSERT FAILED', log):
        raise ValueError('Simulator error/assertion diagnostic')
    rows, invalid, totals = [], [], []
    for line in log.splitlines():
        if not line.startswith('IMPORT_'):
            continue
        kind, _, data = line.partition(' ')
        row = fields(data)
        if kind == 'IMPORT_CASE_PASS':
            if set(row) != {'words', 'heads', 'tokens', 'mode', 'cancel', 'seeds',
                            'coefficients', 'sourcewords', 'cmdpops', 'sentinels'}:
                raise ValueError('Malformed case receipt')
            if (row['sourcewords'], row['cmdpops'], row['sentinels']) != (96, 4, 4):
                raise ValueError('Source/sentinel count mismatch')
            max_seeds = row['words']*row['heads']*4
            phase = row['cancel']
            if phase == 0 and (row['seeds'] != max_seeds or row['coefficients'] != row['tokens']):
                raise ValueError('Normal accepted seed/coefficient count mismatch')
            if phase == 1 and not (0 < row['seeds'] < max_seeds and row['coefficients'] == 0):
                raise ValueError('Seed cancellation not exercised')
            if phase in (2, 3) and (row['seeds'] != max_seeds or row['coefficients'] != (3 if phase == 2 else 1)):
                raise ValueError('Coefficient/drain cancellation not exercised')
            rows.append(row)
        elif kind == 'IMPORT_INVALID_PASS':
            if set(row) != {'words', 'heads', 'tokens'}:
                raise ValueError('Malformed invalid receipt')
            invalid.append(row)
        elif kind == 'IMPORT_PASS':
            totals.append(row)
        else:
            raise ValueError('Unknown import receipt')
    if Counter(tuple(r[k] for k in ('words', 'heads', 'tokens', 'mode', 'cancel')) for r in rows) != expected_cases():
        raise ValueError('Missing/duplicate shape/cancel/reuse coverage')
    if Counter(tuple(r[k] for k in ('words', 'heads', 'tokens')) for r in invalid) != expected_invalid():
        raise ValueError('Missing/duplicate invalid coverage')
    if len(totals) != 1:
        raise ValueError('Missing/duplicate gate completion')
    exact = dict(cases=170, good=108, invalid=44, cancelled=18, sourcewords=12096,
                 cmdpops=504, sentinels=504, latency=12600, held_done=1020)
    positive = {'seed_stalls', 'coefficient_stalls', 'full_credit', 'unequal'}
    total = totals[0]
    if set(total) != set(exact) | positive or any(total[k] != v for k, v in exact.items()):
        raise ValueError('Incorrect gate totals')
    if any(total[k] <= 0 for k in positive):
        raise ValueError('Missing protocol coverage')
    return dict(totals=total, cases=rows, invalid=invalid, measured_return_latency_cycles=1)


def command(argv, cwd, log, deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Gate wall-time budget exhausted')
    with Path(log).open('x') as stream:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            rc = proc.wait(timeout=remaining)
        except BaseException:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise
    result = Path(log).read_text(errors='replace')
    if rc:
        raise ValueError(f'Command exited {rc}: {argv[0]}; see {log}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(OUT) or out == OUT:
        parser.error('Use a fresh signoff verification/out subdirectory')
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started+540
    pins = {}
    report = dict(state='FAIL', scope='Four production StA operand queues/import transport only; '
                  'not numerical, context-FP, SoC, synthesis or FPGA acceptance',
                  wall_time_limit_seconds=540, accepted=str(ACCEPTED))
    try:
        manifest, receipt = ACCEPTED/'source-pins.json', ACCEPTED/'report.json'
        admitted_list = ACCEPTED/'inputs/sources.f'
        for p in (manifest, receipt, admitted_list):
            pins[str(p)] = sha(p)
        accepted = json.loads(manifest.read_text())
        admission = json.loads(receipt.read_text())
        if admission.get('state') != 'PASS' or admission.get('post_pins_match') is not True:
            raise ValueError('Predecessor gate not accepted')
        if accepted.get(str(admitted_list)) != sha(admitted_list):
            raise ValueError('Admitted filelist drift')
        selected, defines = select_sources(admitted_list.read_text(), accepted)
        inputs = out/'inputs'
        inputs.mkdir()
        copied = []
        for name in selected + [str(FROZEN/p) for p in (HEADER, *CONTRACTS)]:
            source = Path(name)
            pins[name] = accepted[name]
            if sha(source) != pins[name]:
                raise ValueError('Frozen dependency drift: '+name)
            if name in selected:
                check_headers(source)
            dest = inputs/source.relative_to(FROZEN)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            pins[str(dest)] = pins[name]
            if name in selected:
                copied.append(str(dest))
        for name in LOCAL:
            source, dest = HERE/name, inputs/name
            pins[str(source)] = sha(source)
            shutil.copyfile(source, dest)
            pins[str(dest)] = pins[str(source)]
        check_command_contract((inputs/CONTRACTS[0]).read_text(), (inputs/'tb.sv').read_text())
        filelist = inputs/'sources.f'
        include = '+incdir+'+str(inputs/'hardware/deps/common_cells/include')
        filelist.write_text('\n'.join(defines+[include]+copied+
                           [str(inputs/'akv_resident_pv_import.sv'), str(inputs/'tb.sv')])+'\n')
        pins[str(filelist)] = sha(filelist)
        save(out/'source-selection.json', dict(selected=selected, frozen=str(FROZEN), defines=defines,
             omitted_legacy_define='TARGET_VERILATOR', headers=[HEADER], contracts=list(CONTRACTS),
             top='resident_pv_import_tb', modified_production_rtl=[], queue_instances=4,
             queue_parameters=dict(CmdBufDepth=5, DataBufDepth=2, NrLanes=4, VLEN=1024,
                                   FPUSupport='FPUSupportNone', AccessCmdPop=1)))
        save(out/'source-pins.json', pins)
        verify(pins)
        if args.prepare_only:
            report['state'] = 'PREPARED_NOT_EXECUTED'
        else:
            vcs = shutil.which('vcs')
            if not vcs:
                raise ValueError('Host VCS unavailable')
            work = out/'work'
            work.mkdir()
            unit = [sys.executable, '-B', '-m', 'unittest', '-v', 'test_run.py']
            compile_cmd = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                           '-top', 'resident_pv_import_tb', '+define+SIMULATION',
                           '-f', str(filelist), '-o', 'simv']
            run_cmd = [str(work/'simv'), '-no_save']
            save(out/'commands.json', dict(tests=unit, compile=compile_cmd, run=run_cmd))
            command(unit, inputs, out/'tests.log', deadline)
            print('IMPORT_COMPILING', flush=True)
            command(compile_cmd, work, out/'compile.log', deadline)
            verify(pins)
            image = {str(p): sha(p) for p in work.rglob('*') if p.is_file()}
            save(out/'image-pins.json', image)
            print('IMPORT_RUNNING', flush=True)
            checked = check_log(command(run_cmd, work, out/'run.log', deadline))
            verify(pins)
            verify(image)
            report.update(checked, state='PASS', post_image_match=True)
        verify(pins)
        report['post_pins_match'] = True
    except Exception as exc:
        report.update(state='FAIL', error=str(exc))
        print('IMPORT_FAIL '+str(exc), flush=True)
    report['elapsed_seconds'] = round(time.monotonic()-started, 3)
    report['artifacts'] = collect_artifacts(out, pins)
    save(out/'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('artifacts', 'cases', 'invalid')}), flush=True)
    return int(report['state'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
