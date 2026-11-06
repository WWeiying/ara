#!/usr/bin/env python3
"""Complete and re-audit the component run with explicit VCS fatal-log gates.

The initial worker rejects a zero return code even for a specifically expected
assertion. Preserve its FAIL; this successor never labels that worker PASS.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess

from audit import digest, require, verify_pins
from run_weight_line_assembler import check, HERE, VERIFY

REASONS = dict(empty='must be a nonempty compacted prefix', prefix='must be a nonempty compacted prefix',
               overflow='exceeds its private bank', order='is not sequential')


def contract_rejection(code, text, reason):
    require(code in (0, 1), 'Unexpected negative-process exit')
    require(len(re.findall(r'^Fatal: .*qbs_weight_line_assembler[.]sv', text, re.M)) == 1 and
            text.splitlines().count('QBS weight line input ' + reason) == 1 and
            'fixture was not rejected' not in text and 'WEIGHT_LINE_COMPONENT_PASS' not in text and
            '$finish called from file ' in text and 'Error:' not in text, 'Missing unique specific RTL contract fatal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.run.resolve(strict=True)
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY / 'verification/out'), 'Fresh verification output')
    out.mkdir(parents=True, exist_ok=False)
    pins = {str(p.resolve()): digest(p) for p in (Path(__file__), HERE / 'test_weight_line_contract.py',
                                                 HERE / 'audit.py', HERE / 'run_weight_line_assembler.py')}
    result = dict(state='CHECKING', production_path_changed=False, soc_integrated=False,
                  physical_supply_widened=False, performance_measured=False, area_measured=False)
    commands = []
    try:
        prior = json.loads((root / 'result.json').read_text())
        require(prior['state'] == 'FAIL' and prior['error'] ==
                "ValueError('Missing specific contract rejection: empty')", 'Not the scoped VCS-return-code failure')
        original = json.loads((root / 'source-pins.json').read_text())
        verify_pins(original)
        verify_pins(prior['artifacts'])
        for path, expected in original.items():
            require(path not in pins or pins[path] == expected, 'Collector/worker source conflict')
            pins[path] = expected
        for path in (root / 'result.json', root / 'source-pins.json', root / 'commands.json',
                     root / 'functional.log', root / 'reject-empty.log'):
            pins[str(path)] = digest(path)
        recorded = json.loads((root / 'commands.json').read_text())
        require([r['label'] for r in recorded] == ['compile', 'functional', 'reject-empty'] and
                all(r['returncode'] == 0 for r in recorded), 'Original command history differs')
        compile_argv = recorded[0]['argv']
        image = root / 'build/simv'
        dut = HERE.parents[2] / 'hardware/src/vlsu/qbs/qbs_weight_line_assembler.sv'
        bench = HERE / 'qbs_weight_line_assembler_tb.sv'
        require(compile_argv.count(str(dut)) == compile_argv.count(str(bench)) == 1 and
                compile_argv[compile_argv.index('-o') + 1] == str(image) and
                compile_argv[compile_argv.index('-top') + 1] == 'qbs_weight_line_assembler_tb' and
                compile_argv[compile_argv.index('-assert') + 1] == 'svaext' and
                original[str(image)] == digest(image), 'Compiled RTL/bench/image identity differs')
        require(recorded[1]['argv'] == [str(image)] and
                recorded[2]['argv'] == [str(image), '+NEGATIVE=empty'], 'Original executed image differs')
        measured = check((root / 'functional.log').read_text())
        contract_rejection(0, (root / 'reject-empty.log').read_text(), REASONS['empty'])
        negatives = ['empty']
        for name in ('prefix', 'overflow', 'order'):
            verify_pins(pins)
            argv = [str(image), '+NEGATIVE=' + name]
            row = dict(label='reject-' + name, argv=argv, timeout=30)
            commands.append(row)
            with (out / ('reject-' + name + '.log')).open('xb') as stream:
                child = subprocess.Popen(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = child.wait(timeout=30)
                except BaseException:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    raise
            row['returncode'] = code
            log = out / ('reject-' + name + '.log')
            contract_rejection(code, log.read_text(), REASONS[name])
            pins[str(log)] = digest(log)
            negatives.append(name)
        verify_pins(pins)
        result.update(state='WEIGHT_LINE_ASSEMBLER_COMPONENT_REAUDITED_WITH_CONTRACT_GUARDS',
            original_worker=str(root), original_worker_state='FAIL', original_worker_relabelled=False,
            original_result_sha256=digest(root / 'result.json'), image_sha256=digest(image),
            measured=measured, contract_rejections=negatives,
            interpretation='Normal cases require clean PASS; negative cases require a unique matching RTL fatal, not a nonzero VCS exit',
            limitations=['Standalone per-bank assembler only, no native-profile steering or wide AXI integration',
                         'No new SoC/SDK/model timing or SRAM/PPA acceptance'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in out.iterdir() if p.is_file() and p.name != 'result.json'}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
