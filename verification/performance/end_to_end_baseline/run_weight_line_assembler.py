#!/usr/bin/env python3
"""Exercise an unintegrated 32-byte SRAM word assembler, not SoC performance."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

from audit import digest, require, verify_pins

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
NORMAL_CASES = 32 * 128 * 4 + 3
NORMAL_BYTES = 32 * 4 * sum(range(1, 129)) + 128 + 1 + 128
ABORT_BYTES = 2 * (7 + 32)
REJECTIONS = dict(empty='nonempty compacted prefix', prefix='nonempty compacted prefix',
                  overflow='exceeds its private bank', order='not sequential')


def check(text):
    require(not re.search(r'Fatal:|Error:|Assertion failed', text), 'Component simulation failure')
    modes = re.findall(r'^WEIGHT_LINE_MODE_PASS mode=(\d+) cases=(\d+)$', text, re.M)
    require(modes == [(str(mode), str(4096 * (mode + 1))) for mode in range(4)], 'Missing/duplicate mode coverage')
    terminal = re.findall(r'^WEIGHT_LINE_COMPONENT_PASS cases=(\d+) abort_cases=(\d+) accepted_bytes=(\d+) written_bytes=(\d+)$',
                          text, re.M)
    require(terminal == [(str(NORMAL_CASES), '4', str(NORMAL_BYTES + ABORT_BYTES), str(NORMAL_BYTES))],
            'Incomplete component byte/state accounting')
    return dict(cases=NORMAL_CASES, abort_cases=4, accepted_bytes=NORMAL_BYTES + ABORT_BYTES,
                written_bytes=NORMAL_BYTES, discarded_bytes=ABORT_BYTES, input_ii1_checked=True,
                byte_canaries_checked=True, output_backpressure_stability_checked=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY / 'verification/out'), 'Fresh sole verification output')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'build').mkdir()
    pins, commands = {}, []
    result = dict(state='PREPARING', pid=os.getpid(), child_pid=None, production_path_changed=False,
                  soc_integrated=False, physical_supply_widened=False, performance_measured=False,
                  area_measured=False)

    def save():
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')

    def pin(path):
        path = str(Path(path).resolve(strict=True))
        actual = digest(path)
        require(path not in pins or pins[path] == actual, 'Input drift')
        pins[path] = actual

    def run(argv, label, bound):
        argv = list(map(str, argv))
        pin(argv[0])
        verify_pins(pins)
        row = dict(label=label, argv=argv, timeout=bound)
        commands.append(row)
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        result['state'] = label.upper()
        with (out / (label + '.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            result['child_pid'] = child.pid
            save()
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
            finally:
                result['child_pid'] = None
                save()
        row['returncode'] = code
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        verify_pins(pins)
        return code, (out / (label + '.log')).read_text()

    save()
    try:
        dut = ROOT / 'hardware/src/vlsu/qbs/qbs_weight_line_assembler.sv'
        bench = HERE / 'qbs_weight_line_assembler_tb.sv'
        for path in (Path(__file__), HERE / 'audit.py', HERE / 'test_weight_line_assembler.py', dut, bench):
            pin(path)
        vcs = shutil.which('vcs')
        require(vcs is not None, 'Host VCS unavailable')
        image = out / 'build/simv'
        code, _ = run([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
                       '+lint=TFIPC-L', dut, bench, '-top', 'qbs_weight_line_assembler_tb',
                       '-Mdir=' + str(out / 'build/csrc'), '-o', image], 'compile', 180)
        require(code == 0, 'Component compilation failed')
        pin(image)
        for path in (out / 'build/simv.daidir').rglob('*.so'):
            pin(path)
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        code, log = run([image], 'functional', 120)
        require(code == 0, 'Component functional simulation failed')
        measured = check(log)
        rejected = []
        for name, reason in REJECTIONS.items():
            code, log = run([image, '+NEGATIVE=' + name], 'reject-' + name, 30)
            require(code != 0 and 'Fatal:' in log and reason in log and
                    'fixture was not rejected' not in log and 'WEIGHT_LINE_COMPONENT_PASS' not in log,
                    'Missing specific contract rejection: ' + name)
            rejected.append(name)
        verify_pins(pins)
        result.update(state='WEIGHT_LINE_ASSEMBLER_COMPONENT_PASS', measured=measured,
            contract_rejections=rejected, source_pins_sha256=digest(out / 'source-pins.json'),
            limitations=['Per-bank ordered compacted-byte contract, not arbitrary rewrites',
                         'Native profile/row steering and actual wide AXI path are not integrated',
                         'SRAM scheduling and SoC/SDK performance require separate acceptance',
                         'No new ISA, arithmetic or production behavior enabled'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        save()
        result['artifacts'] = {str(p): digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('result.json', 'status.json')}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
