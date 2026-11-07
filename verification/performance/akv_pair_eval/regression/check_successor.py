#!/usr/bin/env python3
"""Separate raw-evidence audit; the original failed worker remains unchanged."""
from collections import Counter
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('smol_original_check', HERE/'check.py')
original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(original)
require, sha = original.require, original.sha


def launch_banner(log_path, build):
    work = Path(log_path).resolve().parent
    record = json.loads((work/'console.command.json').read_text())
    argv = record['argv']
    require(isinstance(argv, list) and argv and sha(argv[0]) == original.contract.FIXED_IMAGE_SHA,
            'Not the accepted executable')
    expected = [argv[0], '-no_save', '-l', str(work/'run.vcs.log'),
                '+PRELOAD='+build['elf'], '+TESTCASE=akv_pair_regression', '+NO_FSDB',
                '+NO_INSTR_TRACE', '+VECTOR_TRACE='+str(work/'vector_trace.csv'),
                '+COMMIT_TRACE='+str(work/'commit.csv'), '+AKV_PERF', '+AKV_SUMMARY',
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
    require(argv == expected and record['cwd'] == str(work) and
            type(record['timeout_seconds']) is int and 1 <= record['timeout_seconds'] <= 10800,
            'Unexpected launch command/cwd/timeout')
    return 'Command: '+' '.join(expected)


def check_hardware_work(text, banner):
    expected, rows, summaries, totals, banners = original.expected_commands(), [], [], Counter(), 0
    for line in text.splitlines():
        require('QBS_PERF' not in line, 'Unrelated QBS work in regression')
        if line.startswith('Command: '):
            require(line == banner and banners == 0, 'Unexpected/duplicate launch banner')
            banners += 1
        elif '[AKV_PERF]' in line:
            require(line.startswith('[AKV_PERF] '), 'Malformed native work prefix')
            row = original.parse_fields(line[len('[AKV_PERF] '):], original.PERF_FIELDS)
            index = len(rows)
            require(index < len(expected) and row['seq'] == index+1 and
                    all(row[k] == v for k, v in expected[index].items()), 'Native command order/work mismatch')
            require(row['success'] == 1 and row['busy_cycles'] > 0 and
                    all(row[k] == 0 for k in ('fault', 'validation_fault', 'validation_error',
                                             'read_fault', 'v2_rejected')), 'Native fault/rejection')
            require(row['context_ready'] == int(row['command'] != 3) and
                    row['read_payload_bytes'] == row['q_external_bytes']+row['kv_external_bytes']+
                    (64 if row['v2_full'] else 0), 'Lifecycle/reader payload mismatch')
            for k in original.SUMMARY_FIELDS-{'records', 'success_records', 'fault_records', 'validation_fault_records'}:
                totals[k] = max(totals[k], row[k]) if k == 'read_outstanding_max' else totals[k]+row[k]
            rows.append(row)
        elif '[AKV_PERF_SUMMARY]' in line:
            require(line.startswith('[AKV_PERF_SUMMARY] '), 'Malformed native summary prefix')
            summaries.append(original.parse_fields(line[len('[AKV_PERF_SUMMARY] '):], original.SUMMARY_FIELDS))
        else:
            require('AKV_PERF' not in line, 'Unknown/malformed native work record')
    require(banners == 1 and len(rows) == len(expected) == 602, 'Missing banner/native work')
    summary = dict(totals, records=602, success_records=602, fault_records=0, validation_fault_records=0)
    require(summaries == [summary], 'Missing/duplicate/inconsistent hardware summary')
    sizes, calls, offset = [209, 92, 92, 209], [], 0
    for t, size in enumerate(sizes):
        batch = rows[offset:offset+size]
        calls.append(dict(trial=t, arm=original.contract.ORDER[t], commands=size,
            busy_cycles=sum(r['busy_cycles'] for r in batch), full=1, refill=0, release=1,
            k_single_commands=64 if original.contract.ORDER[t] else 192,
            k_panel4_commands=16 if original.contract.ORDER[t] else 0,
            v_row_d64_commands=10 if original.contract.ORDER[t] else 15))
        offset += size
    return dict(commands=602, per_call_commands=sizes, calls=calls, totals=summary)


def check_run(log_path, build_dir):
    path, directory = Path(log_path).resolve(), Path(build_dir).resolve()
    build = original.verify_build(directory)
    text = path.read_text()
    result = original.check_log(text, Path(build['golden']['captured']).read_bytes(),
        Path(build['golden']['native_tile64']).read_bytes(), build['memory_expected'])
    work = check_hardware_work(text, launch_banner(path, build))
    require(all(c['busy_cycles'] <= elapsed for c, elapsed in zip(work['calls'], result['measured_total_cycles'])),
            'Native busy work exceeds complete-call ROI')
    result.update(state='PASS', work=work, full_call_count=4, order=original.contract.ORDER,
        scope='Separate post-run raw audit of the real SmolLM2 D64/H3/T5 group; original worker stays FAIL',
        provenance=build['provenance'], image_contract=build['image_contract'],
        fixed_image_sha256=build['fixed_image_sha256'], build_sha256=sha(directory/'build.json'),
        elf_sha256=build['elf_sha256'], source_pins_sha256=build['source_pins_sha256'],
        log_sha256=sha(path), independent_vector_work_checked=False, independent_protocol_checked=False,
        checker_correction='Exactly one identity-checked VCS command banner is not a performance record')
    return result


def check_vector_workcounts(path, build_dir):
    return original.check_vector_workcounts(path, build_dir)
