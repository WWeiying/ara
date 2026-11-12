#!/usr/bin/env python3
"""Continue the frozen capability gate using the existing CVXIF-only UVM class."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREVIOUS_NAME = 'optimization_extension_capability_20261111_04'
TEST = 'ara_cvxif_smoke_test'


def base():
    spec = importlib.util.spec_from_file_location('capability_immutable_base', HERE / 'capability_run.py')
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    c.require(c.sha(HERE / 'capability_run.py') ==
              'b6a763954f541d6888c089d75a8d780255e74d6885f261cf610c28fedaa50a0f', 'Immutable base identity')
    return c


def command(image, elf, work, expected):
    return list(map(str, [image['simv'], '-no_save', '-l', work / 'run.vcs.log',
        '+PRELOAD=' + str(elf), '+TESTCASE=optimization_extension_capability_' + str(expected),
        '+UVM_TESTNAME=' + TEST, '+NO_FSDB', '+NO_INSTR_TRACE',
        '+VECTOR_TRACE=' + str(work / 'vector.csv'), '+COMMIT_TRACE=' + str(work / 'commit.csv'),
        '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']))


def checked_class(c, directory):
    source = directory / 'source/verification/uvm/ara_cvxif_uvm_pkg.sv'
    text = source.read_text()
    selected = text.split('class ' + TEST + ' extends uvm_test;', 1)[1].split('endclass', 1)[0]
    normal = text.split('class ara_cvxif_dut_test extends uvm_test;', 1)[1].split('endclass', 1)[0]
    c.require('cvxif_env #(64, 4) env;' in selected and
              'uvm_config_db#(virtual ara_cvxif_if #(64, 4))::get' in selected and
              '@(posedge vif.clk_i iff vif.smoke_done);' in selected and
              'backend_alloc_count' not in selected and 'VID/NO_TRAFFIC' in normal,
              'Unrecognized compiled CVXIF-only test selection')
    bind = directory / 'source/verification/uvm/ara_cvxif_dut_bind.sv'
    c.require('assign cvxif.smoke_done = test_done_i;' in bind.read_text() and
              'assign cvxif.smoke_pass = test_pass_i;' in bind.read_text(), 'Not the real SoC completion binding')
    return dict(selected_test=TEST, same_passive_env=True, real_soc_binding=True,
                backend_activity_required=False, core_success_independently_required=True)


def prepare(c, out):
    previous = c.OUT / PREVIOUS_NAME
    terminal = c.read(previous / 'result.json')
    proof = c.read(previous / 'native_expect0/protocol.json')
    c.require(terminal['state'] == 'FAIL' and terminal['error'] == "ValueError('protocol returncode=1')" and
              len(terminal['host_reuse']) == 8 and all(r['returncode'] == 0 for r in terminal['host_reuse']) and
              [r['qbs_enable'] for r in terminal['package']] == [0, 1] and
              all(r['state'] == 'PASS' for r in terminal['package']) and
              proof['status'] == 'FAIL' and len(proof['issues']) == 3 and
              'VID/NO_TRAFFIC' in proof['issues'][0], 'Unknown predecessor failure; no dispatch')
    c.native_check((previous / 'native_expect0/run.vcs.log').read_text(), 0)
    c.require(not out.exists(), 'Preserve every prior output')
    pins = c.read(previous / 'source-pins.json')
    c.require(c.sha(previous / 'source-pins.json') == terminal['source_pins_sha256'], 'Predecessor review differs')
    c.verify(pins)
    compiler = c.read(previous / 'compiler-input-pins.json')
    c.verify(compiler)
    pins.update(compiler)
    for mode in (0, 1):
        package = previous / ('package_qbs' + str(mode))
        packagepins = c.read(package / 'image-pins.json')
        c.verify(packagepins)
        pins.update(packagepins)
        text = (package / 'run.log').read_text()
        c.require(text.count('EXT_LEGACY_PACKAGE_PASS old_words=255 widths=64 policies=2') == 1 and
                  text.count('EXT_CAPABILITY_PASS widths=64 policies=2 old_words_unchanged=1') == 1,
                  'Predecessor package pass evidence differs')
        for name in ('compile.log', 'run.log', 'image-pins.json'):
            c.pin(pins, package / name)
    commands = c.read(previous / 'commands.json')
    c.require(len([r for r in commands if r['returncode'] != 0]) == 1 and
              commands[-1]['label'] == 'protocol' and commands[-1]['returncode'] == 1,
              'Unexpected predecessor command failure')
    for row in commands:
        c.require(c.sha(row['log']) == row['log_sha256'], 'Predecessor command log changed')
        c.pin(pins, Path(row['log']))
    for mode in ('gcc', 'ubsan'):
        c.require('QBS_COOPERATIVE_CAPABILITY_PASS combinations=32' in
                  (previous / (mode + '-32combo.log')).read_text(), 'Predecessor sanitizer/host evidence')
        c.pin(pins, previous / ('cooperative-' + mode))
    for name in ('result.json', 'source-pins.json', 'commands.json', 'compiler-input-pins.json',
                 'native_expect0/protocol.json', 'native_expect0/run.vcs.log'):
        c.pin(pins, previous / name)
    classes = {}
    for name, directory in (('old', c.OLD), ('new', c.NEW)):
        _, imagepins = c.checked_image(directory)
        pins.update(imagepins)
        classes[name] = checked_class(c, directory)
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    for name in ('capability_native_run.py', 'capability_native_test.py', 'capability_run.py', 'capability_test.py'):
        c.copy(pins, HERE / name, inputs / name)
    for path in (previous / 'inputs/verification').rglob('*.py'):
        c.copy(pins, path, inputs / 'verification' / path.relative_to(previous / 'inputs/verification'))
    for mode in (0, 1):
        c.copy(pins, previous / ('capability%d.elf' % mode), inputs / ('capability%d.elf' % mode))
    env = c.read(previous / 'plan.json')['environment']
    env['PYTHONPATH'] = str(inputs / 'verification')
    c.save(out / 'plan.json', dict(previous=str(previous), environment=env, classes=classes,
        inherited_host=terminal['host_reuse'], inherited_package=terminal['package'],
        inherited_gcc_combinations=32, inherited_ubsan_combinations=32,
        previous_native_attempt='FAIL; preserved without relabeling', automatic_retry=False,
        change='Select existing compiled CVXIF-only test via UVM_TESTNAME; no image/checker/ELF edits'))
    c.pin(pins, out / 'plan.json')
    c.verify(pins)
    c.save(out / 'source-pins.json', pins)
    review = c.sha(out / 'source-pins.json')
    c.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=review))
    cmd = c.service(out, review)
    cmd[cmd.index(str(inputs / 'capability_run.py'))] = str(inputs / 'capability_native_run.py')
    c.save(out / 'launch-command.json', cmd)
    print(json.dumps(dict(output=str(out), review_sha256=review, command=cmd)), flush=True)
    return cmd


def execute(c, out, review):
    c.require(Path(__file__).resolve() == out / 'inputs/capability_native_run.py' and
              c.sha(out / 'source-pins.json') == review and not (out / 'attempt.json').exists(), 'Frozen one-attempt continuation required')
    group = Path('/proc/self/cgroup').read_text()
    pid = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', c.unit(out), '-p', 'MainPID', '--value'], text=True).strip()
    c.require('/' + c.unit(out) in group and pid == str(os.getpid()), 'Direct service MainPID required')
    c.save(out / 'attempt.json', dict(main_pid=os.getpid(), unit=c.unit(out), cgroup=group, review_sha256=review))
    pins, plan = c.read(out / 'source-pins.json'), c.read(out / 'plan.json')
    artifacts, commands = {}, []
    report = dict(state='FAIL', source_pins_sha256=review, automatic_retry=False, native=[],
        inherited_host=plan['inherited_host'], inherited_package=plan['inherited_package'],
        gcc_combinations=32, ubsan_combinations=32, original_worker_relabelled=False,
        scope='Minimal capability admission only, no arithmetic/model/performance/FPGA acceptance')

    def run(label, argv, work):
        c.verify(pins)
        log = work / (label + '.log')
        argv = list(map(str, argv))
        row = dict(label=label, argv=argv, cwd=str(work), environment=plan['environment'])
        commands.append(row)
        c.save(out / 'commands.json', commands)
        with log.open('x') as stream:
            proc = subprocess.Popen(argv, cwd=work, env=plan['environment'], stdout=stream, stderr=subprocess.STDOUT)
            c.save(out / 'status.json', dict(state=label, worker_pid=os.getpid(), child_pid=proc.pid, command=argv))
            try:
                code = proc.wait()
            except BaseException:
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise
        row.update(returncode=code, log=str(log), log_sha256=c.sha(log))
        c.save(out / 'commands.json', commands)
        c.pin(artifacts, log)
        c.require(code == 0, label + ' returncode=' + str(code))
        c.verify(pins)

    try:
        run('unit-tests', ['/usr/bin/python3', '-B', HERE / 'capability_native_test.py'], out)
        run('inherited-unit-tests', ['/usr/bin/python3', '-B', HERE / 'capability_test.py'], out)
        for expected, directory in ((0, c.OLD), (1, c.NEW)):
            image, identity = c.checked_image(directory)
            work = out / ('native_expect%d' % expected)
            work.mkdir()
            elf = HERE / ('capability%d.elf' % expected)
            run('console', command(image, elf, work, expected), work)
            text = (work / 'run.vcs.log').read_text()
            c.require(text.count('[RNTST] Running test ' + TEST + '...') == 1, 'Wrong effective UVM class')
            native = c.native_check(text, expected)
            raw = {str(p): c.sha(p) for p in work.iterdir() if p.is_file()}
            run('protocol', ['/usr/bin/python3', '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--log', work / 'run.vcs.log', '--simv', image['simv'], '--elf', elf,
                '--output', work / 'protocol.json'], work)
            proof = c.read(work / 'protocol.json')
            c.protocol_check(proof, image, elf, work / 'run.vcs.log')
            with (work / 'vector.csv').open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            c.require(len(rows) == 1 and rows[0]['event'] == 'config' and rows[0]['nr_lanes'] == '4' and
                      rows[0]['vlen_bits'] == '1024', 'Unexpected independent backend trace')
            c.save(work / 'numerical.json', native)
            c.verify(raw)
            c.verify(identity)
            c.verify(pins)
            artifacts.update({str(p): c.sha(p) for p in work.iterdir() if p.is_file()})
            report['native'].append(dict(state='PASS', directory=str(work), elf_sha256=c.sha(elf),
                simv_sha256=c.sha(image['simv']), cvxif_requests=proof['contract_counts']['requests'], **native))
            c.save(out / 'progress.json', report)
        a, b = report['native']
        c.require(all(a[k] == b[k] for k in ('info0', 'info1', 'old_words', 'old_words_hash')), 'Cross-image old-word mismatch')
        c.pin(artifacts, out / 'commands.json')
        c.verify(pins)
        c.verify(artifacts)
        c.save(out / 'artifact-pins.json', artifacts)
        report.update(state='PASS', post_pins_match=True, post_image_match=True, post_artifacts_match=True,
            artifact_pins_sha256=c.sha(out / 'artifact-pins.json'), old_words_cross_image_equal=True,
            backend_allocations=0, vlsu_axi_transactions=0, uvm_test=TEST)
    except BaseException as exc:
        report['error'] = repr(exc)
    c.save(out / 'result.json', report)
    c.save(out / 'status.json', dict(state=report['state'], worker_pid=os.getpid(), child_pid=None))
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare-launch', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    c = base()
    out = c.output(args.output)
    if args.action == 'prepare-launch':
        subprocess.run(prepare(c, out), check=True)
        return 0
    return execute(c, out, args.review_sha256)


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(main())
