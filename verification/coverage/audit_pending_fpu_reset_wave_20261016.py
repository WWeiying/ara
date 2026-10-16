#!/usr/bin/env python3
"""Current-capture reset waveform sidecar. No simulation, old context or admission.

audit_reset_wave(CaseAudit) returns a mandatory microstructure_witness on success
and raises on any failed original predicate. Artifacts live in a.out/reset-wave.
The architecture adapter remains responsible for full scalar/vector recovery.
"""
from __future__ import annotations

import argparse
import inspect
from pathlib import Path
import re
import subprocess
import sys
from types import FunctionType, SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(Path(__file__).resolve().parent),
               str(ROOT / 'hardware/fpga/ara_dsa_vcu118/software/vendor/pyelftools-0.32-py3-none-any.whl')]
from audit_probe_semantics_20261015 import (
    BUILD, CONVERTER, CONVERTER_SHA, CaseAudit, install_guard, require, save, sha,
)

CASES = (744, 745, *range(747, 758), 764)


def private(function, **globals_):
    """Rebind only explicit data inputs; leave the original function code intact."""
    return FunctionType(function.__code__, dict(function.__globals__, **globals_),
                        function.__name__, function.__defaults__, function.__closure__)


def current_sources(a):
    book = a.bind_json(BUILD / 'build-source-pins.json')
    relatives = (
        'hardware/src/ara_soc.sv', 'hardware/src/ara_system.sv', 'hardware/src/ara.sv',
        'hardware/tb/ara_tb.sv', 'hardware/include/ara_pkg.sv', 'hardware/src/lane/vmfpu.sv',
        'hardware/deps/axi/include/axi/typedef.svh', 'hardware/deps/axi/src/axi_pkg.sv',
        'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_ctrl.v',
    )
    texts = {r: a.bind(ROOT / r, book[str(ROOT / r)]).read_text() for r in relatives}
    control = texts[relatives[-1]]
    require(re.search(r'reg\s+\[3:0\]\s+div_cur_state\s*;', control),
            'Current DIV controller must declare four-bit stage')
    for name, value in (('RF', '0100'), ('EX1', '0101'), ('EX2', '0110'), ('WB_REQ', '0111')):
        require(re.search(r'parameter\s+' + name + r"\s*=\s*4'b" + value + r'\s*;', control),
                'Current stage encoding differs: ' + name)
    vm = texts['hardware/src/lane/vmfpu.sv']
    require(re.search(r'typedef enum logic \[2:0\]\s*\{\s*NO_REDUCTION,\s*INTRA_LANE_REDUCTION,', vm)
            and "assign vinsn_issue_q_valid = (vinsn_queue_q.issue_cnt != '0);" in vm,
            'Current three-bit INTRA/positive-owner declaration differs')
    require('repeat (4) @(negedge clk);' in texts['hardware/tb/ara_tb.sv'],
            'Current testbench four-clock reset implementation differs')
    return dict(current_build_source_book=str(BUILD / 'build-source-pins.json'),
                sources={str(ROOT / r): book[str(ROOT / r)] for r in relatives},
                old_epoch_source_hashes_used=False)


def runtime_logs(a):
    from ucli_runtime_log_20261015 import iter_runtime_lines
    sources = {str(p): a.bind(p, a.plan['pins'][str(p)]).read_text()
               for p in sorted((a.case / 'ucli').glob('*.tcl'))}
    result = {}
    for name, path in (('console.log', a.case / 'console.log'), ('run.vcs.log', a.work / 'run.vcs.log')):
        with a.bind(path).open(errors='replace') as stream:
            result[name] = ''.join(iter_runtime_lines(stream, sources)) if sources else stream.read()
    return result


def convert(a, out, filename):
    a.bind(CONVERTER, CONVERTER_SHA)
    source = a.bind(a.work / filename)
    require(0 < source.stat().st_size <= 64 * 1024 * 1024, 'Missing/oversized focused VPD')
    target = out / 'reset.vcd'
    command = [str(CONVERTER), '+splitpacked', str(source), str(target)]
    with (out / 'conversion.log').open('x') as stream:
        result = subprocess.run(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                                timeout=120, check=True)
    require(target.is_file() and target.stat().st_size > 0, 'Empty converted reset waveform')
    receipt = dict(command=command, returncode=result.returncode, source_sha256=sha(source),
                   vcd=str(target), vcd_sha256=sha(target), simulation_started=False)
    save(out / 'conversion.json', receipt)
    return target, receipt


def four_clocks(path, parser, clock='ara_tb.clk', reset='ara_tb.rst_n'):
    reader = private(parser.vcd, ROOT='ara_tb', WIDTHS={clock[7:]: 1, reset[7:]: 1})
    iterator = iter(reader(path))
    _, declarations = next(iterator)
    clk, rst = declarations[clock]['code'], declarations[reset]['code']
    intervals, falling, rising, periods = [], 0, 0, set()
    last_rise = None
    for time, before, after in iterator:
        rb, ra = before.get(rst), after.get(rst)
        if rb == '1' and ra == '0':
            require(not intervals and after.get(clk) == '0', 'Unique falling-edge reset assertion required')
            intervals.append(time)
        elif intervals and len(intervals) == 1 and rb != ra:
            require(rb == '0' and ra == '1' and after.get(clk) == '0',
                    'Reset not stably low until falling-edge release')
            intervals.append(time)
        elif intervals and len(intervals) == 1:
            require(rb == ra == '0', 'Reset glitch/unknown during four-clock hold')
        if before.get(clk) == '0' and after.get(clk) == '1':
            if rb == '1' or last_rise is not None:
                if last_rise is not None:
                    periods.add(time - last_rise)
                last_rise = time
            if intervals and len(intervals) == 1 and time > intervals[0]:
                rising += 1
        if (before.get(clk) == '1' and after.get(clk) == '0' and intervals
                and time > intervals[0] and (len(intervals) == 1 or time == intervals[1])):
            falling += 1
    require(len(intervals) == 2 and len(periods) == 1 and rising == falling == 4
            and intervals[1] - intervals[0] == 4 * next(iter(periods)),
            'Exactly four complete stable reset clocks required')
    return dict(status='PASS', resets_100fs=intervals, low_rising_edges=rising,
                low_falling_edges=falling, period_100fs=next(iter(periods)), stable_low=True)


def preflight(a):
    original = Path(next(s.split('=', 1)[1] for s in a.plan['original_command'] if s.startswith('+PRELOAD=')))
    a.bind(original, a.plan['elf_sha256'])
    a.bind(a.case / 'input.elf', a.plan['elf_sha256'])
    if 747 <= a.index <= 757:
        pre = a.old['preflight_case']
        require(Path(pre['ELF']) == original, 'Original matrix preflight/ELF differs')
    else:
        path = original.parent / 'preflight.json'
        expected = a.old.get('preflight_seal', a.old.get('preseal', a.old.get('pins', {}).get(str(path))))
        require(expected is not None, 'Missing original preflight binding')
        pre = a.bind_json(path, expected)
    from elftools.elf.elffile import ELFFile
    with original.open('rb') as stream:
        table = ELFFile(stream).get_section_by_name('.symtab')
        require(table is not None, 'Same-ELF symbol table required')
        symbols = {s.name: s['st_value'] for s in table.iter_symbols()}
    require(all(symbols.get(name) == value for name, value in pre['symbols'].items()),
            'Original preflight symbols do not bind actual ELF')
    return pre, symbols


def selection(a, logs):
    selected = a.old['selection']
    a.bind(a.work / 'external-reset-selection.tcl', a.old['selection_sha256'])
    # This file is copied by the actual remapped entry script. Pin both copies.
    files = [p for p in (a.case / 'ucli').glob('*.tcl') if sha(p) == a.old['selection_sha256']]
    require(len(files) == 1, 'Unique executed source-pinned selection Tcl required')
    a.bind(files[0], a.old['selection_sha256'])
    target, value = selected['ext_target'], selected['ext_value']
    expected = [f'EXT_RESET_READY {target} {value}', f'EXT_RESET_TARGET {target} {value}',
                'EXT_RESET_ASSERT', *[f'EXT_RESET_LOW_EDGE {i}' for i in range(1, 5)],
                'EXT_RESET_RELEASE', 'EXT_RESET_DONE']
    for text in logs.values():
        require([s for s in text.splitlines() if s.startswith('EXT_RESET_')] == expected,
                'Original executed stage/four-edge markers differ')
    return selected


def ured_wave(shared, expected_word, out):
    # Original run_vmfpu_ured_reset763.collect uses this one declaration correction.
    # Its behavioral wave predicates are otherwise exactly shared.wave's source.
    source = inspect.getsource(shared.wave)
    require(source.count("'stage': 4") == 1, 'Original stage declaration changed')
    source = source.replace("'stage': 4", "'stage': 3")
    (out / 'ured-wave-original-width3.py').write_text(source)
    namespace = dict(shared.wave.__globals__, gold=SimpleNamespace(expected_word=expected_word))
    exec(compile(source, str(out / 'ured-wave-original-width3.py'), 'exec'), namespace)
    return namespace['wave']


def ured_window(path, q):
    names = q.states() + [s.rsplit('.', 1)[0] + '.vinsn_queue_q.issue_cnt' for s in q.states()]
    reader = private(q.audit.parser.vcd, ROOT='ara_tb',
                     WIDTHS={**{p[7:]: 3 for p in names}, 'rst_n': 1})
    iterator = iter(reader(path)); _, declarations = next(iterator)
    rst = declarations['ara_tb.rst_n']['code']
    windows = []
    for time, before, after in iterator:
        if before.get(rst) != '1' or after.get(rst) != '0':
            continue
        values = {}
        for name in names:
            bits = before.get(declarations[name]['code'], 'x')
            require(set(bits) <= {'0', '1'}, 'Unknown INTRA/positive-owner reset window')
            values[name] = int(bits, 2)
        require(all(values[p] == 1 for p in names[:4]) and all(values[p] > 0 for p in names[4:]),
                'Actual four-lane INTRA/positive-owner reset window differs')
        windows.append(dict(time_100fs=time, values=values))
    require(len(windows) == 1, 'Unique four-lane reset window required')
    return windows[0]


def reset_epoch(log, interval):
    observed = re.findall(r'@ (\d+):[^\n]*\[CVXIF/RESET\][^\n]*epoch=2', log)
    require(len(observed) == 1 and interval[0] < int(observed[0]) <= interval[1],
            'Actual UVM reset epoch is not inside waveform reset interval')
    return int(observed[0])


def audit_reset_wave(a):
    require(a.index in CASES, 'Unsupported FPU reset waveform case')
    out = a.out / 'reset-wave'
    out.mkdir()
    try:
        a.bind(__file__)
        receipt = a.bind_json(a.case / 'simulation-exit.json')
        require(receipt['executed'] is True and type(receipt['returncode']) is int and receipt['returncode'] == 0
                and receipt['timed_out'] is False and receipt['cancelled'] is False
                and receipt['command'] == a.plan['command'] and receipt['cwd'] == str(a.work),
                'Actual successful current simulator wait required')
        image = a.bind_json(BUILD / 'build-image.json')
        require(a.plan['command'][0] == str(BUILD / 'sim/simv'), 'Actual current build required')
        a.bind(a.plan['command'][0], image[a.plan['command'][0]])
        sources = current_sources(a)
        pre, symbols = preflight(a)
        logs = runtime_logs(a)
        import qualify_external_reset_fixture as shared
        import audit_gap115_axi_v2 as parser
        import run_gap115_active_reset as active
        import qualify_fpu_reset_matrix as matrix
        import run_vmfpu_ured_reset763 as ured
        for module in (shared, parser, active, matrix, matrix.matrix, ured):
            a.bind(module.__file__)
        filename = 'axi-only.vpd' if a.index == 744 else 'external-reset.vpd'
        path, conversion = convert(a, out, filename)
        clock = four_clocks(path, parser,
                            parser.ROOT + '.clk_i' if a.index == 744 else 'ara_tb.clk',
                            parser.ROOT + '.rst_ni' if a.index == 744 else 'ara_tb.rst_n')
        controller = None
        if a.index == 744:
            setup = parser.markers(logs['console.log'])
            axi = parser.read_bursts(path, symbols['source'] + 128,
                                     0x123456789abcdef0 * (1 + (1 << 64)))
            interval = axi['reset_times_100fs']
            save(out / 'capture-setup.json', setup)
        else:
            selected = selection(a, logs)
            if a.index == 764:
                require(selected == ured.selection(), 'Original all-four-INTRA stage selection differs')
                wave = ured_wave(shared, ured.expected_word, out)
                controller = ured_window(path, ured)
            elif a.index == 745:
                require(selected['ext_value'] == 6 and selected['ext_guard'].endswith('.vfdsu_ex2_half'),
                        'Original half EX2 selection differs')
                wave = shared.wave
            else:
                require(selected['ext_value'] == matrix.matrix.STAGES[a.old['stage']][0],
                        'Original SEW/stage code differs')
                wave = private(shared.wave, gold=SimpleNamespace(
                    expected_word=lambda i: matrix.expected_word(a.old['sew'], i)))
                controller = matrix.all_controller_states(path, a.old)
            axi = wave(path, selected, pre['symbols']['source'] + 128, symbols['snapshot'])
            if a.index == 764:
                axi['status'] = 'FOUR_INTRA_VALID_FOUR_CYCLE_RESET_ALL_AR_R_AW_W_B_PASS'
            elif a.index != 745:
                axi['status'] = 'EXACT_SEW_STAGE_FOUR_CLOCK_ALL_AXI_CHANNELS_PASS'
            interval = axi['resets_100fs']
            if controller is not None:
                require(controller['time_100fs'] == interval[0], 'Controller/AXI reset boundary differs')
        require(clock['resets_100fs'] == interval, 'Independent stable-clock/AXI reset intervals differ')
        epoch = reset_epoch(logs['run.vcs.log'], interval)
        for name, value in (('source-binding.json', sources), ('four-clock.json', clock),
                            ('axi.json', axi), ('controller.json', controller)):
            save(out / name, value)
        for source, digest in a.inputs.items():
            require(sha(source) == digest, 'Input changed while auditing reset waveform: ' + source)
        result = dict(status='PASS', required_for_case=True, index=a.index,
                      original_waveform_predicates_preserved=True, conversion=conversion,
                      stable_reset=clock, axi=axi, controller=controller,
                      actual_reset_epoch_time_100fs=epoch, actual_current_source_binding=sources,
                      report=str(out / 'audit.json'), architecture_required_separately=True,
                      simulation_started=False, old_PASS_reused=False, coverage_admitted=False,
                      input_pins=dict(a.inputs))
        save(out / 'audit.json', result)
        return result
    except Exception as error:
        save(out / 'rejection.json', dict(status='CHECKER_REQUIRED', reason=type(error).__name__ + ': ' + str(error),
                                         input_pins=dict(a.inputs), simulation_started=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=int, choices=CASES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / 'verification/out') and not output.exists(), 'Fresh independent output required')
    install_guard(output)
    output.mkdir()
    result = audit_reset_wave(CaseAudit(args.case, output))
    print(result['status'], result['report'], flush=True)


if __name__ == '__main__':
    main()
