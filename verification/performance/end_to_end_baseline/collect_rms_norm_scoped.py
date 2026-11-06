#!/usr/bin/env python3
"""Successor audit of a pinned RMSNorm run with no architectural vector stores.

Keep the original worker FAIL. Replay the unchanged independent checker on the
same logs, omitting only an inapplicable positive vector-write coverage demand.
No simulation, compilation, production integration or checker modification.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
ROOT = VERIFY / 'verification/out/e2e_rms_norm_vcs_20261106_01'
BUILD = VERIFY / 'verification/out/e2e_rms_norm_completed_build_20261106_01'
OUTPUT = VERIFY / 'verification/out/e2e_rms_norm_scoped_audit_20261106_01'
WORKER_SHA = '5d3223be21a094c03bbd87ae611d09268fbf94ab120eb48bcfab4684d45087c9'
PINS_SHA = '094f13f5107c05f99f244c36818091bfe7abe82202f5767232d65166ddc73ed8'
PROTOCOL_SHA = '163df253cdebf4ba8ea3a686442adca8bfc490e278dabc531df61a76890aefe7'
ELF_SHA = '6853d59f059a08b2f37e80029f1258218f1fc782bd1c91f0c13cb3015a53a38e'
ISSUE = 'real DUT UVM observed no complete Ara AXI write traffic'
FUNCTIONS = tuple(prefix + '_ggml_compute_forward_rms_norm_mul_fused'
                  for prefix in ('original', 'candidate', 'strict_original', 'strict_candidate'))


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


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def vector_store(word):
    return word & 0x7f == 0x27 and (word >> 12) & 7 in (0, 5, 6, 7)


def disassembly_work(text):
    """Classify instruction encodings, not a mnemonic substring like 'vse'."""
    rows, functions, name = [], set(), None
    for line in text.splitlines():
        label = re.fullmatch(r'\s*[0-9a-fA-F]+ <([^>]+)>:\s*', line)
        if label:
            name = label[1]
            functions.add(name)
        match = re.match(r'^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{4}|[0-9a-fA-F]{8})\s+(\S+)', line)
        if match:
            address, code, mnemonic = match.groups()
            word = int(code, 16)
            require(not vector_store(word), 'Actual ELF contains a vector store at ' + address)
            rows.append(dict(address=int(address, 16), word=word, mnemonic=mnemonic, function=name))
    require(rows and all(name in functions for name in FUNCTIONS), 'Missing fused-function ELF disassembly')
    stores = {}
    for function in FUNCTIONS:
        stores[function] = [dict(address=hex(row['address']), instruction=f'{row["word"]:08x}')
                            for row in rows if row['function'] == function and
                            row['word'] & 0x7f == 0x27 and (row['word'] >> 12) & 7 == 2]
        require(stores[function], 'Fused output function has no scalar FSW: ' + function)
    return rows, stores


def trace_work(text, instruction_words):
    reader = csv.DictReader(io.StringIO(text))
    require(reader.fieldnames is not None and
            {'cycle', 'event', 'insn', 'nr_lanes', 'vlen_bits'} <= set(reader.fieldnames),
            'Missing independent trace fields')
    config, opcodes, seen, max_cycle = [], Counter(), set(), 0
    for row in reader:
        max_cycle = max(max_cycle, int(row['cycle']))
        if row['event'] == 'config':
            config.append((int(row['nr_lanes']), int(row['vlen_bits'])))
        if row['event'] != 'alloc':
            continue
        word = int(row['insn'], 16)
        require(not vector_store(word), 'Independent trace contains vector-store work')
        require(word in instruction_words, 'Trace instruction absent from actual ELF')
        opcodes[word & 0x7f] += 1
        seen.add(word)
    require(config == [(4, 1024)] and opcodes == Counter({0x57: 649, 0x07: 288}),
            'Independent RMSNorm work differs from pinned scope')
    return dict(allocations=sum(opcodes.values()), vector_loads=opcodes[0x07],
                vector_arithmetic_and_moves=opcodes[0x57], vector_stores=0,
                max_cycle=max_cycle, unique_instruction_words=len(seen), nr_lanes=4, vlen_bits=1024)


def original_protocol_scope(report):
    require(report['status'] == 'FAIL' and report['issues'] == [ISSUE],
            'Original has an issue outside the narrowly permitted coverage mismatch')
    require(report['contract_counts']['protocol_errors'] == 0 and
            report['contract_counts']['requests'] == report['contract_counts']['responses'] == 1974 and
            report['contract_counts']['outstanding'] == 0, 'CVXIF contract work/error differs')
    require(report['backend_counts']['allocations'] == report['backend_counts']['completions'] == 937 and
            report['backend_counts']['aborted'] == 0, 'Backend work differs')
    require(report['axi_read_counts']['ar'] == report['axi_read_counts']['completed'] == 313 and
            report['axi_read_counts']['r_beats'] == 7838 and
            report['axi_read_counts']['pending'] == report['axi_read_counts']['aborted'] == 0,
            'AXI read work differs')
    require(all(value == 0 for value in report['axi_write_counts'].values()),
            'Nonzero AXI write work invalidates the scoped exception')


def scoped_command(original, destination):
    argv = list(original)
    for flag in ('--require-events', '--require-backend', '--require-axi', '--require-axi-write', '--output'):
        require(argv.count(flag) == 1, 'Missing/duplicate original checker requirement: ' + flag)
    require(argv[1:4] == ['-B', '-m', 'ara_verify.uvm_dut'] and
            '--expect-reset-abort' not in argv, 'Unexpected checker identity or reset scope')
    argv.remove('--require-axi-write')
    argv[argv.index('--output')+1] = str(destination)
    return argv


def compare_protocol(original, scoped):
    original_protocol_scope(original)
    require(scoped.get('status') == 'PASS' and scoped.get('issues') == [], 'Scoped protocol did not pass cleanly')
    require(set(original) == set(scoped), 'Independent checker schema changed')
    require(all(original[k] == scoped[k] for k in original if k not in ('status', 'issues')),
            'Protocol events, accounting, logs, ELF or images changed')


class Audit:
    def __init__(self, out):
        self.out, self.pins, self.paths, self.commands = out, {}, {}, []

    def pin(self, path, expected=None):
        path = Path(path).absolute()
        actual = digest(path)
        require(expected is None or actual == expected, 'Pinned identity differs: ' + str(path))
        require(str(path) not in self.pins or self.pins[str(path)] == actual, 'Input drift: ' + str(path))
        self.pins[str(path)] = actual
        self.paths[str(path)] = str(path.resolve(strict=True))
        return actual

    def adopt(self, pins):
        for name, value in pins.items():
            require(re.fullmatch(r'[0-9a-f]{64}', value) and Path(name).is_absolute(), 'Malformed inherited pin')
            require(name not in self.pins or self.pins[name] == value, 'Inherited pin conflict')
            self.pins[name] = value
            self.paths[name] = str(Path(name).resolve(strict=True))

    def verify(self):
        for path, expected in self.pins.items():
            require(str(Path(path).resolve(strict=True)) == self.paths[path], 'Path drift: ' + path)
            require(digest(path) == expected, 'Input drift: ' + path)

    def run(self, argv, label, cwd=None, timeout=120, environment=None):
        argv = list(map(str, argv))
        self.pin(argv[0])
        row = dict(label=label, argv=argv, cwd=str(cwd or self.out), timeout=timeout,
                   environment_overrides=environment or {})
        self.commands.append(row)
        write(self.out / 'commands.json', self.commands)
        env = dict(os.environ)
        env.update(environment or {})
        proc = subprocess.run(argv, cwd=cwd or self.out, env=env, capture_output=True, timeout=timeout)
        (self.out / (label+'.stdout')).write_bytes(proc.stdout)
        (self.out / (label+'.stderr')).write_bytes(proc.stderr)
        row['returncode'] = proc.returncode
        write(self.out / 'commands.json', self.commands)
        require(proc.returncode == 0, label + ' failed; see retained output')
        return proc.stdout.decode()


def collect(out):
    audit = Audit(out)
    result = dict(state='CHECKING', original_worker=str(ROOT), original_worker_state='FAIL',
                  original_worker_relabelled=False, whole_model=False, rtl_changed=False,
                  production_library_changed=False, simulations_launched=0,
                  new_performance_measurement=False, hardware_performance_measured=False)
    try:
        audit.pin(ROOT/'result.json', WORKER_SHA)
        audit.pin(ROOT/'source-pins.json', PINS_SHA)
        audit.pin(ROOT/'work/uvm_result.json', PROTOCOL_SHA)
        worker = read(ROOT/'result.json')
        require(worker['state'] == 'FAIL' and worker['error'] == "ValueError('PROTOCOL_CHECK returned 1')" and
                worker['wide'] == 0 and not worker['performance_measured'], 'Wrong original failure')
        inherited = read(ROOT/'source-pins.json')
        audit.adopt(inherited)
        old = read(ROOT/'work/uvm_result.json')
        original_protocol_scope(old)
        for filename, key in (('run.vcs.log', 'log_sha256'), ('vector_trace.csv', 'vector_trace_sha256')):
            audit.pin(ROOT/'work'/filename, old[key])
        for filename in ('status.json', 'work/checker.command.json', 'work/checker.log',
                         'work/console.command.json', 'work/console.log'):
            audit.pin(ROOT/filename)
        status = read(ROOT/'status.json')
        require(status['state'] == 'FAIL' and status['running_exit_code'] == 0 and
                status['protocol_check_exit_code'] == 1, 'Original execution status differs')
        program = read(BUILD/'build.json')
        require(inherited[str(BUILD/'build.json')] == digest(BUILD/'build.json') and
                program['state'] == 'REAL_QWEN3_FUSED_RMS_NORM_ABBA_BUILT_NOT_EXECUTED' and
                program['trials'] == 8 and program['outputs_checked'] == 40960 and
                program['boundary_cases'] == 53 and program['sum_cases'] == 10 and
                program['rows'] == [1, 4] and program['width'] == 2048 and program['order'] == [0, 1, 1, 0] and
                program['boundary_rounding_math'] and program['captured_output_replay_bitwise'] and
                program['timing_includes_csr_completion'] and not program['rtl_changed'] and
                not program['production_library_changed'], 'Software build contract differs')
        audit.pin(BUILD/'source-pins.json', program['source_pins_sha256'])
        elf = Path(status['elf'])
        simv = Path(status['simv'])
        require(str(elf) == program['elf'] and program['elf_sha256'] == old['elf_sha256'] == ELF_SHA,
                'Actual ELF binding differs')
        audit.pin(elf, ELF_SHA)
        require(old['simv_sha256'] == old['sim_image_sha256'][str(simv)], 'Simulator identity differs')
        image_files = {str(simv)} | {str(p) for p in Path(str(simv)+'.daidir').rglob('*.so')}
        require(image_files == set(old['sim_image_sha256']), 'Actual image inventory differs')
        for path, expected in old['sim_image_sha256'].items():
            require(inherited.get(path) == expected, 'Image not pinned by original worker')
            audit.pin(path, expected)
        source_snapshot = out/'sources'
        source_snapshot.mkdir()
        for name in ('collect_rms_norm_scoped.py', 'test_rms_norm_scoped.py', 'audit.py',
                     'check_rms_norm.py', 'check_projection_native.py', 'rms_norm_completion.py', 'rms_norm_native.cpp'):
            source = HERE/name
            audit.pin(source, inherited.get(str(source)))
            shutil.copyfile(source, source_snapshot/name)
            audit.pin(source_snapshot/name, digest(source))
        # Bind the actual package imported by the child, including its relative imports.
        for name in ('__init__.py', 'uvm_dut.py', 'contract.py', 'artifacts.py'):
            source = VERIFY/'verification/ara_verify'/name
            expected = inherited.get(str(source)) or inherited.get(str(HERE.parents[2]/'verification/ara_verify'/name))
            require(expected is not None, 'Checker dependency lacks original pin')
            audit.pin(source, expected)
        audit.verify()
        audit.run([sys.executable, '-B', '-m', 'unittest', '-v', 'test_rms_norm_scoped'],
                  'unit-tests', cwd=source_snapshot, timeout=30)
        objdump = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-objdump')
        audit.pin(objdump, inherited[str(objdump)])
        disassembly = audit.run([objdump, '-d', elf], 'actual-elf-disassembly')
        rows, scalar_stores = disassembly_work(disassembly)
        trace = trace_work((ROOT/'work/vector_trace.csv').read_text(), {row['word'] for row in rows})
        audit.pin(BUILD/'disassembly.log', inherited[str(BUILD/'disassembly.log')])
        require(rows == disassembly_work((BUILD/'disassembly.log').read_text())[0], 'Actual and build disassembly differ')
        from check_rms_norm import check, check_activity
        from rms_norm_completion import completed_caller
        require(Path(program['completed_caller']).read_text() == completed_caller((HERE/'rms_norm_native.cpp').read_text()),
                'CSR-completed timer source differs')
        data = Path(program['data'])
        require(inherited[str(data/'data.json')] == digest(data/'data.json'), 'Data provenance differs')
        data_report = read(data/'data.json')
        for path, expected in data_report['artifacts'].items():
            require(inherited.get(path) == expected, 'Data artifact not originally pinned')
            audit.pin(path, expected)
        measured = check((ROOT/'work/run.vcs.log').read_text(), (data/'expected_f32.bin').read_bytes(),
                         (data/'decode_expected_f32.bin').read_bytes())
        activity = check_activity((ROOT/'work/vector_trace.csv').read_text())
        old_command = read(ROOT/'work/checker.command.json')['argv']
        expected = ['/usr/bin/python3', '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                    '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace',
                    str(ROOT/'work/vector_trace.csv'), '--log', str(ROOT/'work/run.vcs.log'),
                    '--simv', str(simv), '--elf', str(elf), '--output', str(ROOT/'work/uvm_result.json')]
        require(old_command == expected, 'Original protocol command differs')
        command = scoped_command(old_command, out/'uvm_result.json')
        audit.run(command, 'independent-protocol', environment={
            'PYTHONPATH': str(VERIFY/'verification'), 'PYTHONDONTWRITEBYTECODE': '1', 'LC_ALL': 'C'})
        scoped = read(out/'uvm_result.json')
        compare_protocol(old, scoped)
        audit.verify()
        require({str(simv)} | {str(p) for p in Path(str(simv)+'.daidir').rglob('*.so')} == image_files,
                'Post-audit simulator image inventory differs')
        write(out/'expected-work.json', dict(actual_elf_sha256=ELF_SHA, instruction_count=len(rows),
              scalar_output_stores=scalar_stores, trace=trace, activity=activity,
              vector_write_coverage='Not applicable: actual ELF and trace contain no vector stores',
              old_issue=ISSUE, requirement_delta=['Omit positive --require-axi-write coverage only'],
              axi_write_protocol_accounting_checked=True))
        result.update(state='REAL_QWEN3_FUSED_RMS_NORM_SCOPED_REAUDITED',
                      independent_protocol_checked=True, scoped_acceptance=True,
                      vector_write_coverage_required=False, axi_write_protocol_accounting_checked=True,
                      all_other_protocol_fields_unchanged=True, pre_post_pins_match=True,
                      software_performance_replayed=True, measured=measured, activity=activity, expected_work=trace,
                      elf=str(elf), elf_sha256=ELF_SHA, simv=str(simv), image_pins=old['sim_image_sha256'],
                      original_worker_result_sha256=WORKER_SHA, original_protocol_result_sha256=PROTOCOL_SHA,
                      original_source_pins_sha256=PINS_SHA, inherited_input_count=len(inherited),
                      log_sha256=old['log_sha256'], vector_trace_sha256=old['vector_trace_sha256'],
                      protocol_sha256=digest(out/'uvm_result.json'), unit_tests_passed=True,
                      limitations=['Original worker remains FAIL; only this explicitly scoped successor is accepted',
                                   'No architectural vector-write coverage is claimed',
                                   'Existing full fused-call software timings only, not whole-model or hardware speedup',
                                   'No simulation, rebuild, checker edit, RTL edit, production promotion or PPA acceptance'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        write(out/'source-pins.json', audit.pins)
        write(out/'path-identities.json', audit.paths)
        write(out/'commands.json', audit.commands)
        result['source_pins_sha256'] = digest(out/'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in sorted(out.rglob('*'))
                               if p.is_file() and p.name != 'result.json'}
        write(out/'result.json', result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('artifacts', 'image_pins')}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'), 'Fresh sole-verification output')
    out.mkdir(parents=True, exist_ok=False)
    collect(out)


if __name__ == '__main__':
    main()
