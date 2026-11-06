#!/usr/bin/env python3
"""Bounded successor component evidence; one compile, no production integration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
MAIN = Path('/home/wangwy/openproject/ara_dsa')
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OUTPUT = VERIFY / 'verification/out/e2e_weight_line_boundaries_20261106_01'
AUDIT = VERIFY / 'verification/out/e2e_weight_line_assembler_audit_20261106_01'
AUDIT_SHA = '318802325ca59b9dc041527d2c7ee2c959ea3c611cbf14947eb23652290bb7aa'
DUT = MAIN / 'hardware/src/vlsu/qbs/qbs_weight_line_assembler.sv'
DUT_SHA = 'ff2735b3a6fece3d5a1ec44e8ca3a4c0d7cf2e4c473820b7c9ba4231058a4d5c'
WIDTHS = (6, 7, 8, 16)
REASONS = {
    'empty': (128, 'QBS weight line input must be a nonempty compacted prefix'),
    'prefix': (128, 'QBS weight line input must be a nonempty compacted prefix'),
    'overflow': (132, 'QBS weight line input exceeds its private bank'),
    'order': (130, 'QBS weight line input is not sequential'),
}
TERMINAL = 'WEIGHT_LINE_BOUNDARIES_PASS widths=4 cases=68 streams=60 aborts=8'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def clean_log(text):
    require(not re.search(r'(?i)\bfatal\s*:|\berror\s*:|assertion\s+failed|\boffending\b', text),
            'Unexpected simulation/tool diagnostic')


def contract_rejection(code, text, dut, kind):
    line, reason = REASONS[kind]
    require(code in (0, 1), 'Unexpected negative process status')
    require(len(re.findall(r'(?i)\bfatal\s*:', text)) == 1, 'Expected exactly one GLOBAL fatal')
    headers = re.findall(r'(?m)^\s*Fatal:\s*"([^"]+)",\s*(\d+):[^\n]*$', text)
    require(headers == [(str(dut), str(line))], 'Fatal is not the exact DUT guard')
    require(text.splitlines().count(reason) == 1, 'Wrong/duplicate contract reason')
    finishes = re.findall(r'\$finish called from file "([^"]+)"', text)
    require(finishes == [str(dut)], 'Missing/foreign/duplicate finish origin')
    require(not re.search(r'(?i)\berror\s*:|assertion\s+failed|NOT_REJECTED|fixture was not rejected|WEIGHT_LINE_\w*PASS', text),
            'Unexpected failure or success in negative run')
    return dict(global_fatals=1, source=str(dut), line=line, reason=reason, returncode=code)


def stream_geometry(width):
    capacity = 1 << width
    rows = []
    for chunk in (1, 3, 7, 16, 31):
        rows.extend(((1, min(3*chunk+5, capacity-1)),
                     (17, min(5*chunk+17, capacity-17))))
    rows.extend(((capacity-1, 1), (capacity-32, 32), (capacity-33, 33),
                 (0, capacity), (capacity//2+3, min(63, capacity-(capacity//2+3)))))
    return rows


def expected_width(width):
    rows = stream_geometry(width)
    written = sum(length for _, length in rows) + 4
    words = sum((base % 32 + length + 31)//32 for base, length in rows) + 4
    return (width, 17, 15, 2, 19, written+4, written, words)


def check_normal(code, text):
    require(code == 0, 'Normal simulation process failed')
    clean_log(text)
    rows = re.findall(r'^WEIGHT_LINE_BOUNDARIES_WIDTH_PASS width=(\d+) cases=(\d+) streams=(\d+) aborts=(\d+) epochs=(\d+) accepted_bytes=(\d+) written_bytes=(\d+) word_writes=(\d+)$', text, re.M)
    rows = [tuple(map(int, row)) for row in rows]
    require(sorted(rows) == [expected_width(w) for w in WIDTHS], 'Missing/duplicate/incorrect width accounting')
    require(text.splitlines().count(TERMINAL) == 1 and
            len(re.findall(r'^WEIGHT_LINE_BOUNDARIES_PASS\b.*$', text, re.M)) == 1,
            'Missing/duplicate/incorrect exact terminal')
    require(len(re.findall(r'^WEIGHT_LINE_BOUNDARIES_WIDTH_PASS\b.*$', text, re.M)) == len(WIDTHS),
            'Unexpected malformed width terminal')
    return [dict(zip(('width', 'cases', 'streams', 'aborts', 'epochs',
                      'accepted_bytes', 'written_bytes', 'word_writes'), row)) for row in sorted(rows)]


class Run:
    def __init__(self, out):
        self.out, self.pins, self.identities, self.commands = out, {}, {}, []

    def pin(self, path, expected=None):
        lexical = Path(path).absolute()
        resolved = lexical.resolve(strict=True)
        actual = digest(resolved)
        require(expected is None or actual == expected, 'Pinned identity mismatch: ' + str(path))
        require(str(resolved) not in self.pins or self.pins[str(resolved)] == actual,
                'Source drift: ' + str(path))
        self.pins[str(resolved)] = actual
        self.identities[str(lexical)] = str(resolved)
        return actual

    def verify(self):
        for path, resolved in self.identities.items():
            require(str(Path(path).resolve(strict=True)) == resolved, 'Path identity drift: ' + path)
        for path, expected in self.pins.items():
            require(digest(path) == expected, 'Source drift: ' + path)

    def run(self, argv, label, timeout, cwd=None):
        argv = list(map(str, argv))
        self.pin(argv[0])
        self.verify()
        row = dict(label=label, argv=argv, cwd=str(cwd or self.out), timeout=timeout)
        self.commands.append(row)
        write(self.out / 'commands.json', self.commands)
        with (self.out / (label + '.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=cwd or self.out, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = child.wait(timeout=timeout)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
        row['returncode'] = code
        write(self.out / 'commands.json', self.commands)
        self.verify()
        return code, (self.out / (label + '.log')).read_text(errors='replace')


def prior_audit(run):
    run.pin(AUDIT / 'result.json', AUDIT_SHA)
    old = read(AUDIT / 'result.json')
    require(old['state'] == 'WEIGHT_LINE_ASSEMBLER_COMPONENT_REAUDITED_WITH_CONTRACT_GUARDS' and
            old['original_worker_state'] == 'FAIL' and not old['original_worker_relabelled'],
            'Wrong prior acceptance scope')
    run.pin(AUDIT / 'source-pins.json', old['source_pins_sha256'])
    pins = read(AUDIT / 'source-pins.json')
    run.pin(DUT, DUT_SHA)
    require(pins[str(DUT)] == DUT_SHA, 'Prior DUT differs')
    original = Path(old['original_worker'])
    run.pin(original / 'result.json', old['original_result_sha256'])
    require(read(original / 'result.json')['state'] == 'FAIL', 'Original FAIL changed')
    checks = {}
    for kind in REASONS:
        log = (original if kind == 'empty' else AUDIT) / ('reject-' + kind + '.log')
        run.pin(log, pins[str(log)])
        checks[kind] = contract_rejection(0, log.read_text(), DUT, kind)
    commands = original / 'commands.json'
    run.pin(commands, pins[str(commands)])
    return checks, read(commands)[0]['argv'][0]


def execute(out):
    run = Run(out)
    report = dict(state='PREPARING', run=str(out), production_path_changed=False,
                  soc_integrated=False, physical_supply_widened=False,
                  performance_measured=False, area_measured=False, synthesis_run=False)
    try:
        inputs = out / 'inputs'
        inputs.mkdir()
        for name in ('qbs_weight_line_boundaries_tb.sv', 'run_weight_line_boundaries.py',
                     'test_weight_line_boundaries.py'):
            source = HERE / name
            run.pin(source)
            shutil.copyfile(source, inputs / name)
            run.pin(inputs / name, digest(source))
        run.pin(sys.executable)
        code, text = run.run([sys.executable, '-B', '-m', 'unittest', '-v',
                              'test_weight_line_boundaries'], 'unit-tests', 30, cwd=inputs)
        require(code == 0 and '\nOK\n' in text, 'Checker unit tests failed')
        previous, vcs = prior_audit(run)
        write(out / 'prior-audit-global-fatals.json', previous)
        dut = inputs / DUT.name
        shutil.copyfile(DUT, dut)
        run.pin(dut, DUT_SHA)
        build = out / 'build'
        build.mkdir()
        image = build / 'simv'
        code, text = run.run([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
                              '-assert', 'svaext', '+lint=TFIPC-L', dut,
                              inputs / 'qbs_weight_line_boundaries_tb.sv',
                              '-top', 'qbs_weight_line_boundaries_tb',
                              '-Mdir=' + str(build / 'csrc'), '-o', image], 'compile', 180)
        require(code == 0, 'VCS compilation failed')
        clean_log(text)
        run.pin(image)
        for directory in (build / 'simv.daidir', build / 'csrc'):
            for path in sorted(directory.rglob('*.so')):
                run.pin(path)
        code, text = run.run([image, '-no_save'], 'normal', 60)
        measured = check_normal(code, text)
        negative = {}
        for width in WIDTHS:
            code, text = run.run([image, '-no_save', '+NEGATIVE=overflow', '+WIDTH=' + str(width)],
                                  'reject-overflow-' + str(width), 30)
            negative[str(width)] = contract_rejection(code, text, dut, 'overflow')
        run.verify()
        require(sum(row['label'] == 'compile' for row in run.commands) == 1, 'Not one compile')
        report.update(state='WEIGHT_LINE_BOUNDARIES_COMPONENT_PASS', measured=measured,
                      prior_audit=str(AUDIT), prior_audit_sha256=AUDIT_SHA,
                      prior_global_fatal_checks=previous, original_worker_relabelled=False,
                      dut_sha256=DUT_SHA, image=str(image), image_sha256=digest(image),
                      overflow_rejections=negative, compile_count=1, normal_runs=1, negative_runs=4,
                      unit_tests_passed=True,
                      limitations=['Standalone per-bank sequential-prefix boundary tests only',
                                   'No native profile steering, SoC/SDK/model or SRAM/PPA acceptance'])
    except BaseException as exc:
        report.update(state='FAIL', error=repr(exc))
        raise
    finally:
        write(out / 'source-pins.json', run.pins)
        write(out / 'path-identities.json', run.identities)
        write(out / 'commands.json', run.commands)
        report['source_pins_sha256'] = digest(out / 'source-pins.json')
        report['artifacts'] = {str(p): digest(p) for p in sorted(out.rglob('*'))
                               if p.is_file() and p.name != 'result.json'}
        write(out / 'result.json', report)
        print(json.dumps({k: v for k, v in report.items() if k != 'artifacts'}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY / 'verification/out'),
            'Use a fresh sole-verification output directory')
    out.mkdir(parents=True, exist_ok=False)
    execute(out)


if __name__ == '__main__':
    main()
