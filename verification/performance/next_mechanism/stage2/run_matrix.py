#!/usr/bin/env python3
"""Paired full-engine/shared-reader QBS gate with four real lane multipliers.

Engine-only fixture: busy_o supplies command ownership; native_quiescent is 1.
No SoC admission, CPU, DDR or model-speedup acceptance is implied.
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
CAPTURE = OUT / 'qbs-matrix-reuse-pair-20261023-01'
LOCAL = ('run_matrix.py', 'matrix_lenders.sv', 'test_run_matrix.py')
PACKAGES = (
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/include/rvv_pkg.sv', 'hardware/include/ara_pkg.sv')
GENERATOR = Path('verification/akv/canonical_promotion/generate_standalone.py')
COMPOSER = Path('verification/akv/shared_reader_integration')
TB = Path('verification/qbs/qbs_engine_tb.sv')
SLICES = (('m4a', 0, 4, 0, 32), ('m4b', 4, 4, 0, 32),
          ('m8a', 0, 8, 0, 16), ('m8b', 0, 8, 16, 16))
LOAN_PORTS = '''
    output logic loan_valid_o,
    input logic [3:0] loan_ready_i,
    output logic [15:0] loan_weight_o [4],
    output logic [63:0] loan_activation_o,
    input logic [3:0] loan_result_valid_i,
    input logic signed [16:0] loan_result_pair_i [4][4]'''
TB_LENDERS = '''
  localparam bit Stage2CooperativeWaves = `STAGE2_COOPERATIVE_WAVES;
  logic stage2_loan_valid;
  logic [3:0] stage2_loan_ready, stage2_loan_result_valid;
  logic [15:0] stage2_loan_weight [4];
  logic [63:0] stage2_loan_activation;
  logic signed [16:0] stage2_loan_result_pair [4][4];
  stage2_matrix_lenders #(.CooperativeWaves(Stage2CooperativeWaves)) lenders (
    .clk_i(clk), .rst_ni(rst_n), .lease_i(busy),
    .command_fire_i(command_valid && command_ready),
    .success_i(success_valid), .fault_i(fault_valid),
    .command_m_i(command_m), .command_n_i(dut.i_engine.n_q),
    .profile_i(dut.i_engine.weight_profile_q),
    .engine_pairs_i(useful_pairs), .engine_dot_cycles_i(dot_active_cycles),
    .native_valid_i(dut.i_engine.i_compute_engine.i_profile_engine_int.dot_issue),
    .native_stream_valid_i(dut.i_engine.i_compute_engine.i_profile_engine_int.decoder_stream_valid),
    .native_k_per_i(dut.i_engine.i_compute_engine.i_profile_engine_int.decoder_k_per),
    .loan_valid_i(stage2_loan_valid), .loan_ready_o(stage2_loan_ready),
    .loan_weight_i(stage2_loan_weight), .loan_activation_i(stage2_loan_activation),
    .loan_result_valid_o(stage2_loan_result_valid),
    .loan_result_pair_o(stage2_loan_result_pair)
  );
'''
TB_PORTS = '''    .loan_valid_o(stage2_loan_valid), .loan_ready_i(stage2_loan_ready),
    .loan_weight_o(stage2_loan_weight), .loan_activation_o(stage2_loan_activation),
    .loan_result_valid_i(stage2_loan_result_valid),
    .loan_result_pair_i(stage2_loan_result_pair),
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def verify(pins):
    for name, expected in pins.items():
        if sha(name) != expected:
            raise ValueError('Identity drift: ' + name)


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Non-unique adaptation anchor: ' + repr(before))
    return text.replace(before, after, 1)


def adapt(wrapper, bench):
    # Each change is reversible; original assertions/tasks/expected data stay intact.
    changes = [
        ('    parameter type         vid_t', "    parameter bit CooperativeWaves = 1'b0,\n    parameter type         vid_t"),
        ('    .SeedRestoreEnable(SeedRestoreEnable),',
         '    .SeedRestoreEnable(SeedRestoreEnable),\n    .CooperativeWaves(CooperativeWaves),')]
    result = wrapper
    for old, new in changes:
        result = once(result, old, new)
    end = result.index('\n  );')
    result = result[:end] + ',' + LOAN_PORTS + result[end:]
    restored = result[:result.index(',' + LOAN_PORTS)] + result[result.index(',' + LOAN_PORTS) + len(',' + LOAN_PORTS):]
    for old, new in reversed(changes):
        restored = once(restored, new, old)
    if restored != wrapper:
        raise ValueError('Wrapper adaptation not reversible')
    anchor = '  qbs_engine_composed #(\n'
    adapted = once(bench, anchor, TB_LENDERS + anchor + '    .CooperativeWaves(Stage2CooperativeWaves),\n')
    clock = '    .clk_i                           (clk),\n'
    adapted = once(adapted, clock, TB_PORTS + clock)
    restored = once(adapted, TB_PORTS + clock, clock)
    restored = once(restored, TB_LENDERS + anchor + '    .CooperativeWaves(Stage2CooperativeWaves),\n', anchor)
    if restored != bench:
        raise ValueError('TB checker changed')
    return result, adapted


def vectors(text):
    lines = text.splitlines()
    header = lines[0].split()
    if len(header) != 2 or header[0] != 'QBSCMD1':
        raise ValueError('Bad vector header')
    cases, current = [], None
    for line in lines[1:]:
        fields = line.split()
        if not fields:
            raise ValueError('Blank vector record')
        if fields[0] == 'CMD':
            if current is not None or len(fields) != 9:
                raise ValueError('Bad CMD')
            current = dict(zip(('id', 'profile', 'wl', 'al', 'm', 'n', 'kb'), map(int, fields[1:8])))
            current.update(flags=int(fields[8], 16), outputs={})
        elif fields[0] == 'O':
            index, bits = int(fields[1]), int(fields[2], 16)
            if current is None or index in current['outputs'] or len(fields) != 3:
                raise ValueError('Bad/duplicate output')
            current['outputs'][index] = bits
        elif fields[0] == 'C':
            if current is None or 'counts' in current or len(fields) != 9:
                raise ValueError('Bad C')
            current['counts'] = list(map(int, fields[1:]))
        elif fields[0] == 'END':
            if current is None or 'counts' not in current:
                raise ValueError('Incomplete vector')
            stride = 32 if current['m'] <= 4 else 16
            expected = {r * stride + c for r in range(current['m']) for c in range(current['n'])}
            if set(current['outputs']) != expected:
                raise ValueError('Output shape/stride')
            cases.append(current)
            current = None
        elif fields[0] not in ('T', 'A', 'W', 'ENDT'):
            raise ValueError('Unknown vector record')
    if current is not None or len(cases) != int(header[1]) or [c['id'] for c in cases] != list(range(len(cases))):
        raise ValueError('Vector case identity/count')
    return cases


def candidate_vector(text):
    vectors(text)
    profile = m = None
    result, changes = [], []
    for line in text.splitlines(keepends=True):
        fields = line.split()
        if fields[0] == 'CMD':
            profile, m = int(fields[2]), int(fields[5])
        if fields[0] == 'C' and (profile, m) == (1, 8):
            before = int(fields[6])
            if before % 2:
                raise ValueError('Odd baseline dot cycles')
            fields[6] = str(before // 2)
            changes.append(dict(before=before, after=before // 2))
            line = ' '.join(fields) + '\n'
        result.append(line)
    updated = ''.join(result)
    old, new = vectors(text), vectors(updated)
    for a, b in zip(old, new):
        expected = json.loads(json.dumps(a))
        expected['outputs'] = a['outputs']
        if (a['profile'], a['m']) == (1, 8):
            expected['counts'][5] //= 2
        if expected != b:
            raise ValueError('Adapted more than candidate dot count')
    return updated, changes


def fields(line):
    pairs = [p.split('=', 1) for p in line.split()[1:]]
    if any(len(p) != 2 for p in pairs) or len(dict(pairs)) != len(pairs):
        raise ValueError('Malformed/duplicate log field')
    return {k: int(v) if v.isdecimal() else v for k, v in pairs}


def check_log(text, cases, cooperative, suite):
    if re.search(r'(?im)^(?:\s*(?:Error[-:]|Fatal[: -]|Assertion failed)|.*\$fatal|.*STAGE2_MATRIX_FAIL)', text):
        raise ValueError('Simulator error/fatal/assertion')
    expected_terminal = f'QBS engine PASS: {len(cases)} functional cases' + (' plus four fault classes' if suite == 'synthetic' else '')
    terminals = re.findall(r'^QBS engine PASS:.*$', text, re.M)
    if terminals != [expected_terminal]:
        raise ValueError('Canonical checker terminal missing/duplicate/wrong')
    rows = re.findall(r'^QBS end-to-end case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) Kb=(\d+) layouts=(\d+)/(\d+) cycles=(\d+)$', text, re.M)
    expected = [(c['id'], c['profile'], c['m'], c['n'], c['kb'], c['wl'], c['al']) for c in cases]
    parsed = [tuple(map(int, r)) for r in rows]
    if [r[:-1] for r in parsed] != expected or any(r[-1] <= 0 for r in parsed):
        raise ValueError('Canonical functional case identity/count')
    if suite == 'synthetic':
        for kind in ('validation', 'MMU', 'AXI', 'PMA'):
            if text.count(f'QBS {kind} atomic-fault PASS') != 1:
                raise ValueError('Missing original fault class')
    if suite == 'context' and len(re.findall(r'^QBS activation context FILL/REUSE/RELEASE PASS ', text, re.M)) != len(cases):
        raise ValueError('Missing original context cases')
    work = [fields(line) for line in text.splitlines() if line.startswith('STAGE2_MATRIX_COMMAND ')]
    resets = [fields(line) for line in text.splitlines() if line.startswith('STAGE2_MATRIX_RESET ')]
    done = [fields(line) for line in text.splitlines() if line.startswith('STAGE2_MATRIX_LENDERS_DONE ')]
    if len(done) != 1 or not work or len({w['seq'] for w in work + resets}) != len(work + resets):
        raise ValueError('Missing/duplicate lender accounting')
    totals = done[0]
    if (totals['commands'], totals['reset_commands'], totals['latency'], totals['instances'], totals['scope']) != (len(work), len(resets), 3, 4, 'engine_not_soc'):
        raise ValueError('Wrong lender terminal')
    if {w['seq'] for w in work + resets} != set(range(1, len(work) + len(resets) + 1)):
        raise ValueError('Unaccounted commands')
    for w in work:
        eligible = cooperative and (w['m'], w['profile']) == (8, 1)
        if w['cooperative'] != cooperative or w['success'] + w['fault'] != 1 or w['latency'] != 3 or w['loan_issues'] != w['loan_returns']:
            raise ValueError('Command/return accounting')
        if w['native_products'] != 32 * w['native_issues'] or w['loan_products'] != 32 * w['loan_issues']:
            raise ValueError('Physical 32-products accounting')
        if w['success'] and (w['loan_issues'] != (w['native_issues'] if eligible else 0) or
                             (eligible and w['loan_useful'] != w['native_useful'])):
            raise ValueError('Paired/fallback work mismatch')
    for key in ('native_issues', 'loan_issues', 'loan_returns'):
        if sum(w[key] for w in work + resets) != totals[key]:
            raise ValueError('Lost work across reset/terminal')
    if totals['loan_issues'] != totals['loan_returns'] + totals['reset_flushed']:
        raise ValueError('Undrained loan work')
    if cooperative and any((c['profile'], c['m']) == (1, 8) for c in cases) and totals['loan_issues'] == 0:
        raise ValueError('Candidate borrowing not exercised')
    if not cooperative and totals['loan_issues']:
        raise ValueError('Baseline borrowed')
    return dict(cycles=[r[-1] for r in parsed], commands=work, totals=totals,
                phases=[fields(l) for l in text.splitlines() if l.startswith('QBS phase case=')],
                fp=[fields(l) for l in text.splitlines() if l.startswith('QBS FP probe case=')],
                traffic=[fields(l) for l in text.splitlines() if l.startswith('QBS traffic case=')])


def command(argv, cwd, log, deadline, limit=1200):
    timeout = min(limit, deadline - time.monotonic())
    if timeout <= 0:
        raise TimeoutError('Worker deadline')
    with log.open('x') as stream:
        result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError(f'Command exit={result.returncode}; see {log}')


def rtl_sources(root):
    block = (root / 'verification/qbs/Makefile').read_text().split('RTL_SOURCES := \\\n', 1)[1].split('RTL_SOURCES +=', 1)[0]
    names = block.replace('\\\n', ' ').split()
    result = [p.replace('$(RTL_BLOCK_ADAPTER_SOURCE)', '$(ROOT)/hardware/src/vlsu/qbs/qbs_block_adapter.sv').replace('$(ROOT)/', '') for p in names]
    if any('$' in p or not (root / p).is_file() for p in result):
        raise ValueError('Unsupported QBS Makefile source list')
    return result[:3] + list(PACKAGES) + result[3:] + ['hardware/src/lane/simd_mul.sv', 'hardware/src/lane/qbs_lane_mul_borrow.sv']


def prepare(out):
    if out.parent != OUT or subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'], text=True).strip() != 'ara_dsa_signoff_integration':
        raise ValueError('Use unique direct signoff out child on verification branch')
    vcs, cc = shutil.which('vcs'), shutil.which('cc')
    if not vcs or not cc:
        raise ValueError('Host VCS and C compiler required')
    out.mkdir(exist_ok=False)
    snapshot, pins = out / 'inputs', {}

    def copy(source, target):
        digest = sha(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != digest:
            raise ValueError('Copy race: ' + str(source))
        pins[str(source)] = pins[str(target)] = digest

    sources = rtl_sources(ROOT)
    helpers = [GENERATOR, COMPOSER / 'compose_canonical_standalone.py', COMPOSER / 'compose_standalone.py',
               *sorted((ROOT / COMPOSER / 'standalone_port_contracts').glob('*'))]
    extras = [TB, Path('verification/qbs/Makefile'), Path('hardware/include/shared_reader_types.svh'),
              Path('apps/common/qbs_abi.h'), *(Path('verification/qbs') / p for p in ('qbs_command_vectors.c', 'qbs_ref.c', 'qbs_ref.h')),
              *(HERE.relative_to(ROOT) / p for p in LOCAL)]
    for rel in sorted(set(map(Path, sources)) | {p.relative_to(ROOT) if p.is_absolute() else p for p in helpers + extras}):
        copy(ROOT / rel, snapshot / rel)
    for folder in ('hardware/deps/common_cells/include', 'hardware/deps/axi/include'):
        for source in sorted((ROOT / folder).rglob('*')):
            if source.is_file():
                copy(source, snapshot / source.relative_to(ROOT))
    accepted = json.loads((CAPTURE / 'status.json').read_text())
    if accepted['state'] != 'PASS' or not accepted['paired_outputs']['q4_K']['bit_exact']:
        raise ValueError('Real capture is not the accepted paired input')
    copy(CAPTURE / 'status.json', snapshot / 'capture-status.json')
    for source in sorted((CAPTURE / 'inputs/q4_K').iterdir()):
        if source.is_file():
            if accepted['sources_and_inputs'].get(str(source)) != sha(source):
                raise ValueError('Accepted real input identity mismatch: ' + str(source))
            copy(source, snapshot / 'capture' / source.name)
    local = snapshot / HERE.relative_to(ROOT)
    deadline = time.monotonic() + 180
    command([sys.executable, '-B', local / 'test_run_matrix.py'], out, out / 'host-tests.log', deadline, 60)
    generated = out / 'canonical'
    command([sys.executable, '-B', snapshot / GENERATOR, '--source-root', snapshot, '--kind', 'qbs', '--tb', snapshot / TB, '--output', generated],
            out, out / 'generate.log', deadline, 60)
    wrapper, bench = adapt((generated / 'composed_engine.sv').read_text(), (generated / 'original_suite.sv').read_text())
    (out / 'matrix_engine.sv').write_text(wrapper)
    (out / 'matrix_tb.sv').write_text(bench)
    generator = out / 'qbs_command_vectors'
    command([cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-ffp-contract=off', '-frounding-math',
             '-I' + str(snapshot / 'apps/common'), snapshot / 'verification/qbs/qbs_command_vectors.c',
             snapshot / 'verification/qbs/qbs_ref.c', '-lm', '-o', generator], out, out / 'oracle-build.log', deadline)
    specs = [('synthetic', []), ('context', ['--context-suite'])]
    specs += [(name, ['--real', 'q4_K', snapshot / 'capture', '1536', '1536', str(start), str(m), str(col), str(n)]) for name, start, m, col, n in SLICES]
    vector_info = {}
    for name, args in specs:
        baseline = out / f'{name}_baseline.txt'
        command([generator, baseline, *args], out, out / f'{name}_oracle.log', deadline)
        updated, changes = candidate_vector(baseline.read_text())
        candidate = out / f'{name}_candidate.txt'
        candidate.write_text(updated)
        vector_info[name] = dict(baseline=str(baseline), candidate=str(candidate), changes=changes)
    coordinates = []
    for group in (SLICES[:2], SLICES[2:]):
        merged, flags = {}, 0
        for name, start, m, col, n in group:
            case, = vectors(Path(vector_info[name]['baseline']).read_text())
            stride = 32 if m <= 4 else 16
            for index, bits in case['outputs'].items():
                coord = (start + index // stride, col + index % stride)
                if coord in merged:
                    raise ValueError('Overlapping real output slices')
                merged[coord] = bits
            flags |= case['flags']
        coordinates.append((merged, flags))
    if coordinates[0] != coordinates[1] or len(coordinates[0][0]) != 256:
        raise ValueError('Real M4/M8 oracle mismatch')
    save(out / 'oracle-pair.json', dict(outputs=256, bit_exact=True, fflags=coordinates[0][1], input='Qwen2.5 attn_norm/attn_q raw q4_K; K=1536'))
    filelist = out / 'sources.f'
    filelist.write_text(''.join('+incdir+' + str(snapshot / p) + '\n' for p in ('hardware/include', 'hardware/deps/common_cells/include', 'hardware/deps/axi/include')) +
                        '\n'.join(str(snapshot / p) for p in sources) + '\n' + str(local / 'matrix_lenders.sv') + '\n' +
                        str(out / 'matrix_engine.sv') + '\n' + str(out / 'matrix_tb.sv') + '\n')
    save(out / 'selection.json', dict(vcs=vcs, local=str(local), vectors=vector_info, timeout_seconds=7200,
                                    scope='engine_not_soc', lease='busy_o', native_quiescent=1))
    for path in (Path(vcs).resolve(), Path(cc).resolve(), Path(sys.executable).resolve(), *out.glob('*'), *generated.glob('*')):
        if path.is_file() and path.name != 'source-pins.json':
            pins[str(path)] = sha(path)
    verify(pins)
    save(out / 'source-pins.json', pins)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', frozen_runner=str(local / 'run_matrix.py'),
                                    source_pins_sha256=sha(out / 'source-pins.json')))
    print(local / 'run_matrix.py', flush=True)


def image_pins(work):
    return {str(p): sha(p) for p in (work / 'simv', *(work / 'simv.daidir').rglob('*')) if p.is_file()}


def execute(out):
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_matrix.py':
        raise ValueError('Execute only the frozen runner')
    pins = json.loads((out / 'source-pins.json').read_text())
    deadline = time.monotonic() + config['timeout_seconds']
    report = dict(state='FAIL', scope='engine_not_soc; no CPU/DDR/model speedup', runs={}, images={})
    save(out / 'status.json', dict(state='RUNNING', phase='compile', scope=report['scope']))
    try:
        verify(pins)
        for arm, enable in (('baseline', 0), ('candidate', 1)):
            work = out / arm
            work.mkdir(exist_ok=False)
            argv = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4', '+lint=TFIPC-L',
                    '-top', 'qbs_engine_tb', '-o', 'simv', f'+define+STAGE2_COOPERATIVE_WAVES={enable}', '-f', out / 'sources.f']
            save(work / 'compile-command.json', list(map(str, argv)))
            print('STAGE2_MATRIX_COMPILING ' + arm, flush=True)
            command(argv, work, work / 'compile.log', deadline)
            verify(pins)
            report['images'][arm] = image_pins(work)
            if str(work / 'simv') not in report['images'][arm]:
                raise ValueError('Missing simulator image')
            save(work / 'image-pins.json', report['images'][arm])
        # Original suites gate both configurations before any real matrix run.
        for suite in ('synthetic', 'context', *(s[0] for s in SLICES)):
            for arm, enable in (('baseline', 0), ('candidate', 1)):
                verify(pins)
                verify(report['images'][arm])
                work = out / arm
                vector = Path(config['vectors'][suite][arm])
                argv = [work / 'simv', '-no_save', '+QBS_COMMAND_VECTOR_FILE=' + str(vector)]
                if suite != 'synthetic':
                    argv += ['+QBS_FUNCTIONAL_ONLY', '+QBS_FP_PROBE']
                if suite == 'context':
                    argv += ['+QBS_CONTEXT_SUITE']
                save(work / f'{suite}-command.json', list(map(str, argv)))
                save(out / 'status.json', dict(state='RUNNING', phase=suite, arm=arm))
                print(f'STAGE2_MATRIX_RUNNING {suite} {arm}', flush=True)
                command(argv, work, work / f'{suite}.log', deadline, 900)
                result = check_log((work / f'{suite}.log').read_text(), vectors(vector.read_text()), enable, suite)
                verify(pins)
                verify(report['images'][arm])
                report['runs'][f'{suite}_{arm}'] = result
                save(out / 'progress.json', report)
                print(f'STAGE2_MATRIX_CHECKED {suite} {arm}', flush=True)
        report['paired_cycles'] = {arm: {m: sum(report['runs'][f'{m}{half}_{arm}']['cycles'][0] for half in ('a', 'b'))
                                         for m in ('m4', 'm8')} for arm in ('baseline', 'candidate')}
        verify(pins)
        for image in report['images'].values():
            verify(image)
        report.update(state='PASS', source_post_match=True, images_post_match=True,
                      original_checker_preserved=True, canonical_shared_reader=True, extra_mac_arrays=0)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file() and
                           p.suffix in ('.log', '.json') and p.name not in ('report.json', 'status.json')}
    save(out / 'report.json', report)
    save(out / 'status.json', dict(state=report['state'], error=report.get('error'), report=str(out / 'report.json')))
    print('STAGE2_MATRIX_' + report['state'] + ' ' + str(out / 'report.json'), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        return execute(args.output.resolve())
    prepare(args.output.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
