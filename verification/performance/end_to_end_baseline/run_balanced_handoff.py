#!/usr/bin/env python3
"""M4 handoff on the isolated balanced SoC; retain the existing protocol worker."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import re
import sys

from audit import digest, require
import balanced_soc_handoff as program
import run_wide_soc_smoke as parent
from check_projection_native import fields
from collect_projection_native import PHASES

sys.path.insert(0, str(parent.ROOT / 'verification/akv'))
import run_refill_overlap_probe as akv_parser

PARENT_SHA = '6f820de6360d9ca9ed3ec513855d4786d683fdf7f81576c2aeae2d0878e047e3'
PROGRAM_HELPER_SHA = 'fa4aeb618867fa64132bc873e67343e8210a99d3d13c20f09801e7a0f4ced350'
PROGRAM = program.OUTPUT / 'host-finalize-02'
PROGRAM_SHA = '190eadea36bb1aaa2d8573ab6dcef804701986667e1cd103fdfcbacb11083690'
PREPARED_SHA = 'fe7d388a120d95e2b159e7f823f91f90689c0ed0bcbea9d757a4294d7473e5b2'
STATE = 'BALANCED_SOC_M4_HANDOFF_RTL_PROTOCOL_PASS'


def check_program(text, kind):
    require(kind == 'handoff', 'Balanced worker requires M4 handoff')
    require([line for line in text.splitlines() if 'Core Test' in line] ==
            ['Core Test *** SUCCESS *** (tohost = 0)'], 'Exact core completion required')
    uart = '\n'.join(line for line in text.replace('\r', '').splitlines()
                     if line.startswith(('BALANCED_M4_HANDOFF_', 'Balanced M4 QBS/AKV handoff smoke:')))
    checked = program.check_log(uart)
    require(not re.search(r'mismatch|unexpected trap|\btrapped\b', text, re.I), 'Runtime mismatch or trap')
    qbs = [fields(line, '[QBS_PERF]') for line in text.splitlines() if line.startswith('[QBS_PERF] ')]
    require(len(qbs) == 4, 'All four actual M4 commands required')
    for i, row in enumerate(qbs):
        expected = dict(seq=i + 1, m=4, n=3, vlen=1024, lanes=4, success=1, fault=0,
                        validation_fault=0, read_fault=0, useful_pairs=3072, dot_active_cycles=32,
                        weight_bytes=432, activation_bytes=1168, payload_bytes=1616,
                        activation_access=0, read_ranges=8, r_beats=92, accumulator_updates=12,
                        fp_uop_issue=72, commit_groups=16)
        require(all(row.get(key) == value for key, value in expected.items()) and
                row['busy_cycles'] >= row['r_beats'] and row['ar'] >= row['read_ranges'] and
                sum(row['phase_' + phase + '_cycles'] for phase in PHASES) == row['busy_cycles'],
                'Actual M4 compute, read or completion work differs')
    akv = [akv_parser.numeric_fields(line[len('[AKV_PERF] '):], akv_parser.PERF_FIELDS)
           for line in text.splitlines() if line.startswith('[AKV_PERF] ')]
    joint = [('QBS' if line.startswith('[QBS_PERF] ') else 'AKV') for line in text.splitlines()
             if line.startswith(('[QBS_PERF] ', '[AKV_PERF] '))]
    require(joint == ['QBS', 'QBS', *(['AKV'] * 10), 'QBS', 'QBS'],
            'Actual QBS/AKV ownership handoff order differs')
    require(len(akv) == 10 and [row['command'] for row in akv] == [4, 2, 3, 4, 2, 2, 2, 3, 4, 3],
            'Actual AKV ownership sequence differs')
    require(all(row['seq'] == i + 1 and row['success'] == 1 and row['fault'] == 0 and
                row['validation_fault'] == row['validation_error'] == row['read_fault'] == row['v2_rejected'] == 0 and
                row['context_ready'] == int(row['command'] != 3) and row['busy_cycles'] > 0 and row['id'] < 8 and
                row['v2_full'] == int(row['command'] == 4) and
                row['load'] == row['v2_row_load'] == int(row['command'] == 2) and
                row['release'] == int(row['command'] == 3) for i, row in enumerate(akv)),
            'AKV fault or missing completion')
    return dict(checked, actual_m4_commands=4, actual_akv_commands=10,
                balanced_dot_issue_counts=[row['dot_active_cycles'] for row in qbs],
                all_four_rows_and_zero_tails_checked_on_target=True, architectural_traps=0)


def specialize():
    require(digest(parent.__file__) == PARENT_SHA and digest(program.__file__) == PROGRAM_HELPER_SHA,
            'Sealed worker/program helper identity differs')
    source = inspect.getsource(parent.run)
    edits = [
        ("'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED'", "'BALANCED_SOC_BUILT_NOT_EXECUTED'"),
        ("soc['width'] in (128, 256)",
         "soc['width'] == 256 and soc['mode'] == 1 and soc['prepared_sha256'] == PREPARED_SHA and\n"
         "                soc['config']['qbs_balanced_matrix_dot'] == '1'"),
        ("'WIDE_SOC_HANDOFF_SMOKE_ELF_BUILT_NOT_EXECUTED'",
         "'BALANCED_SOC_M4_HANDOFF_HOST_SCOPED_BUILD_ACCEPTED_NOT_EXECUTED'"),
        ("'Wrong ELF kind')", "'Wrong ELF kind')\n"
         "        require(program['expected_runtime_checks'] == M4.EXPECTED_CHECKS and\n"
         "                program['required_scope'] == M4.SCOPE and program['required_terminal'] == M4.PASS and\n"
         "                program['skip_is_not_acceptance'], 'Wrong M4 program contract')"),
        ("HERE / 'test_wide_soc_smoke.py'", "HERE / 'test_wide_soc_smoke.py',\n"
         "                     HERE / 'test_run_balanced_handoff.py', Path(M4.__file__), Path(AKV_PARSER.__file__)"),
        ("'+VECTOR_TRACE=' + str(work / 'vector_trace.csv')", "'+AKV_PERF', '+VECTOR_TRACE=' + str(work / 'vector_trace.csv')"),
        ("'PHYSICAL_WIDE_SOC_SMOKE_PASS'", repr(STATE)),
    ]
    text = source
    for before, after in edits:
        require(text.count(before) == 1, 'Unique handoff worker adaptation: ' + before)
        text = text.replace(before, after, 1)
    restored = text
    for before, after in reversed(edits):
        require(restored.count(after) == 1, 'Ambiguous worker inverse')
        restored = restored.replace(after, before, 1)
    require(restored == source, 'Worker adaptation changed unrelated checks')
    namespace = dict(vars(parent), __file__=str(Path(__file__).resolve()),
                     M4=program, AKV_PARSER=akv_parser,
                     PREPARED_SHA=PREPARED_SHA, check_program=check_program)
    exec(compile(text, str(Path(__file__).resolve()), 'exec'), namespace)
    return namespace['run'], dict(original_sha256=PARENT_SHA,
        original_function_sha256=hashlib.sha256(source.encode()).hexdigest(),
        generated_function_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_reversible=True, numerical_or_protocol_checks_removed=False,
        image_and_program_admission_specialized=True, edits=[dict(before=a, after=b) for a, b in edits])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--soc', type=Path, required=True)
    parser.add_argument('--soc-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=2700)
    args = parser.parse_args()
    args.program, args.program_sha, args.kind = PROGRAM, PROGRAM_SHA, 'handoff'
    require(digest(PROGRAM / 'result.json') == PROGRAM_SHA, 'Scoped handoff receipt changed')
    worker, _ = specialize()
    worker(args)
