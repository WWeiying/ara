#!/usr/bin/env python3
"""Recheck the complete default QBS controller against a sealed cycle baseline."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

from audit import digest, require, verify_pins

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
PRIOR = RUNS / 'e2e_matrix_fault_schedule_20261106_02'
ORIGINAL = RUNS / 'e2e_matrix_engine_pair_20261106_01'
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from run_tile_context_engine import check_log, check_geometry


def check(text, vector, previous):
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed', text), 'Default engine failure')
    require(text.splitlines().count('MATRIX_ENGINE_CONFIG wide=0') == 1,
            'Wrong original arithmetic configuration')
    count = int(vector.splitlines()[0].split()[1])
    require(count == 36, 'Unexpected original fixture')
    measured = check_log(text, count, 1, 0)
    check_geometry(vector, measured['direct'])
    require(measured == check_log(previous, count, 1, 0),
            'Default numerical/work/cycle/context regression')
    return dict(normal_cases=count, context_cases=1, fault_classes=4,
                direct_and_context_cycles_identical=True,
                original_testbench_work_counter_checks_retained=True,
                direct=measured['direct'], contexts=measured['contexts'])


def run(out):
    out = out.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification output')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='PREPARING', performance_improvement_measured=False,
                  wide_weight_ingress=False, full_soc_tested=False, synthesis_run=False)

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = digest(path)
        require(expected is None or actual == expected, 'Input identity differs: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'Input drift: ' + str(path))
        pins[str(path)] = actual

    def save():
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')

    def command(argv, label, bound):
        argv = list(map(str, argv))
        argv[0] = shutil.which(argv[0]) or argv[0]
        pin(argv[0])
        verify_pins(pins)
        row = dict(label=label, argv=argv, timeout=bound)
        commands.append(row)
        result.update(state=label.upper(), child_pid=None)
        with (out / (label + '.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            result['child_pid'] = child.pid
            save()
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
        row['returncode'] = code
        result['child_pid'] = None
        save()
        verify_pins(pins)
        text = (out / (label + '.log')).read_text()
        require(code == 0 and not re.search(r'Fatal:|Error[-:]|Assertion.*failed', text), label + ' failed')
        return text

    try:
        for path in (Path(__file__), HERE / 'test_wide_default_engine.py', HERE / 'audit.py',
                     ROOT / 'verification/qbs/Makefile', ROOT / 'verification/qbs/run_tile_context_engine.py',
                     ROOT / 'verification/qbs/run_half_scale_soc.py'):
            pin(path)
        receipt = ROOT / 'verification/performance/evidence/matrix_engine_pair_20261106_01/result.json'
        pin(receipt)
        accepted = json.loads(receipt.read_text())
        require(accepted['state'] == 'MATRIX_FULL_ENGINE_COMPOSITE_REAUDITED' and
                Path(accepted['run']) == PRIOR, 'Wrong accepted complete-engine reference')
        pin(PRIOR / 'result.json', accepted['result_sha256'])
        pin(PRIOR / 'source-pins.json', accepted['source_pins_sha256'])
        old_pins = json.loads((PRIOR / 'source-pins.json').read_text())
        vector = ORIGINAL / 'matrix-base.txt'
        reference = ORIGINAL / 'run-matrix-gap0-0.log'
        wrapper = ORIGINAL / 'matrix_wrapper.sv'
        bench = PRIOR / 'matrix_fault_suite.sv'
        for path in (vector, reference, wrapper, bench):
            require(str(path) in old_pins, 'Reference lacks accepted binding')
            pin(path, old_pins[str(path)])
        # The already accepted stimulus correction changes only injected late
        # faults, not normal command timing. The original reference remains raw.
        require(check(reference.read_text(), vector.read_text(), reference.read_text())['normal_cases'] == 36,
                'Original full reference no longer checks')
        command([sys.executable, '-B', HERE / 'test_wide_default_engine.py'], 'unit-tests', 30)
        listing = command(['make', '-s', '--no-print-directory', '-C', ROOT / 'verification/qbs',
            "--eval=default-ingress-sources:;@printf '%s\\n' $(RTL_SOURCES)",
            'default-ingress-sources'], 'sources', 30).splitlines()
        sources = [Path(path) for path in listing]
        require(sources and len(sources) == len(set(sources)) and all(p.is_file() for p in sources),
                'Invalid RTL inventory')
        tree = out / 'tree'
        include_dirs = ('hardware/include', 'hardware/deps/common_cells/include', 'hardware/deps/axi/include')
        headers = [p for relative in include_dirs for p in (ROOT / relative).rglob('*.svh')]
        changed = {
            'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
            'hardware/src/vlsu/qbs/qbs_block_adapter.sv',
            'hardware/src/vlsu/qbs/qbs_payload_buffer.sv',
            'hardware/src/vlsu/qbs/qbs_engine.sv',
            'hardware/src/vlsu/qbs/qbs_read_engine.sv',
            'hardware/src/vlsu/qbs_akv_shared_reader.sv',
            'hardware/include/shared_reader_types.svh',
            'hardware/include/vlsu_shared_reader.svh',
        }
        added = {
            'hardware/src/vlsu/qbs_reader_narrow_view.sv',
            'hardware/src/vlsu/qbs/qbs_weight_line_assembler.sv',
            'hardware/src/vlsu/qbs/qbs_weight_wide_mapper.sv',
            'hardware/src/vlsu/qbs/qbs_weight_wide_bank.sv',
        }
        for path in dict.fromkeys([*sources, *headers]):
            relative = path.relative_to(ROOT).as_posix()
            expected = old_pins.get(str(path.resolve()), old_pins.get(str(path)))
            require(expected is not None or relative in added or path not in sources,
                    'Unexpected new RTL source: ' + relative)
            pin(path, None if relative in changed or relative in added else expected)
            destination = tree / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            pin(destination, pins[str(path.resolve())])
        for path in (wrapper, bench):
            destination = tree / path.name
            shutil.copyfile(path, destination)
            pin(destination, old_pins[str(path)])
        vcs = shutil.which('vcs')
        require(vcs is not None, 'Host VCS unavailable')
        pin(vcs)
        pin(Path(vcs).resolve().parent.parent / 'linux64/bin/vcs1')
        build = out / 'build'
        build.mkdir()
        image = build / 'simv'
        (out / 'source-pins-precompile.json').write_text(json.dumps(pins, indent=2) + '\n')
        command([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
            *['+incdir+' + str(tree / relative) for relative in include_dirs],
            '+incdir+' + str(HERE), *[tree / p.relative_to(ROOT) for p in sources],
            tree / wrapper.name, tree / bench.name, '-top', 'qbs_engine_tb',
            '-pvalue+qbs_engine_tb.Wide=0', '-Mdir=' + str(build / 'csrc'), '-o', image], 'compile', 600)
        pin(image)
        for path in build.rglob('*.so'):
            pin(path)
        (out / 'source-pins-presimulation.json').write_text(json.dumps(pins, indent=2) + '\n')
        log = command([image, '-no_save', '+QBS_COMMAND_VECTOR_FILE=' + str(vector),
                       '+QBS_RESPONSE_GAP=0'], 'functional', 300)
        measured = check(log, vector.read_text(), reference.read_text())
        verify_pins(pins)
        result.update(state='DEFAULT_COMPLETE_QBS_ENGINE_CYCLES_UNCHANGED', measured=measured,
                      old_reference=str(reference), original_reference_relabelled=False,
                      limitations=['Complete QBS controller/shared-reader/commit fixture, not CVA6 or whole SoC',
                                   'Default128 and WideMatrixDot=0 only; new wide path has a separate pair',
                                   'Unchanged direct/context cycles are not an end-to-end model speedup'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in out.iterdir()
                               if p.is_file() and p.name not in ('result.json', 'status.json')}
        save()
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
