#!/usr/bin/env python3
"""Declaration-order-only successor of the sealed, failed seed preparation.

Reuse the original gate/checkers through isolated function namespaces. Never
modify its module globals, files, failed worker or prepared receipt. Preparing
does not launch VCS; execution still requires an explicitly reviewed SHA.
"""
import argparse
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
FIRST = RUNS / 'e2e_balanced_seed_20261106_01'
OUT = RUNS / 'e2e_balanced_seed_20261106_02'
OWNED = ('balanced_seed_gate_v2.py', 'test_balanced_seed_gate_v2.py')
PREPARED = 'BALANCED_SEED_V2_INPUTS_PREPARED_NOT_EXECUTED'
ORIGINAL_HELPER_SHA = '4409d71f612780a71731d29cb0846e728529b09fab51b37504bdfca237c19681'
ORIGINAL_TEST_SHA = '8e48882d7475604a83408fabc46c0afbac2c0f843685316e588b4736c366ecfc'
FIRST_PREPARED_SHA = 'd160199e86e7f69cf4132cbdc8a17af750fd1c631d6d43e89ea4301061d29e7e'
FIRST_FAILED_SHA = '95be78ad6b3242c000647813112f8614ec9f084a147cb22c2cfbbac4d267a6ad'
FIRST_TB_SHA = '5d4ee04281016660ab5e984cae3c77e8574e43315ced5bc8d0783cae1445af3b'
FUNCTION_SHAS = {
    'bench_source': '5c19da0eed7acb4ad2c28d37ee0b6ac06f28ed40e99d590640da29d1d90f7324',
    'prepare': '5ce8ed4bcfac4a884007abfdcb100f75e6ca0b9648bf5dab054dad1779fa8599',
    'execute': '60193465bc3e877f136c357837f01894ff0604a34036589227811632d2db3c76',
    'ownership': 'f93e20e8a314886226f9f564d6e79ce0e4e7608c5c96988ca657cacc70c7796e',
}
PROOF_PINS = {
    HERE / 'balanced_seed_gate.py': ORIGINAL_HELPER_SHA,
    HERE / 'test_balanced_seed_gate.py': ORIGINAL_TEST_SHA,
    FIRST / 'result.json': FIRST_PREPARED_SHA,
    FIRST / 'source-pins.json': '4523681cb078b0d7166e807449e21b78dbfd75e811dc4043853cdaac0e40e082',
    FIRST / 'qbs_balanced_seed_tb.sv': FIRST_TB_SHA,
    FIRST / 'vectors-balanced.txt': 'bde09d21fde96bcbe1d3b55d55c302fd30d6cde1ec22303e0e354af4feafc1e5',
    FIRST / 'worker/result.json': FIRST_FAILED_SHA,
    FIRST / 'worker/source-pins.json': 'fd3362252d0c06570761d37b72feaca1d8543aa5e32104f165cb621125e80f50',
    FIRST / 'worker/commands.json': 'd9cb0f5b3fb3eb7fd3cda195934af9b31b0605c67e986b75d13cbccb666aa952',
    FIRST / 'worker/compile.log': '70562b5446804ad1aa82f12dd9009a5d25d2ea28dc9319f49ff1930da62f0981',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def verify_original_helpers():
    for path in (HERE / 'balanced_seed_gate.py', HERE / 'test_balanced_seed_gate.py'):
        require(digest(path) == PROOF_PINS[path], 'Sealed original helper/test changed')


def admit_failure(record, commands, log):
    expected = dict(state='BALANCED_SEED_GATE_FAIL', child_pid=None, target_executed=False,
                    rtl_compiled=False, post_pins_match=True, first_failure_preserved=True,
                    prepared_result_sha256=FIRST_PREPARED_SHA,
                    error="ValueError('First failure preserved: compile')")
    require(all(key in record and type(record[key]) is type(value) and record[key] == value
                for key, value in expected.items()), 'Only the exact original compile failure is admissible')
    require(len(commands) == 1 and commands[0]['label'] == 'compile' and commands[0]['returncode'] == 255,
            'Original worker attempted more than its one failed compile')
    require(re.findall(r'^Error-\[[^]]+\]', log, re.M) == ['Error-[IND]'] and
            log.count("Identifier 'bsg_k' has not been declared yet.") == 1 and
            'qbs_balanced_seed_tb.sv, 113\n' in log and '\n1 error\n' in log,
            'Original diagnostic is not the known declaration-order failure')


def validate_declaration_order(text):
    declaration = text.index('  int bsg_case=-1,bsg_k=0,bsg_m=0,bsg_n=0,bsg_kb=0;')
    task = text.index('  task automatic continue_after_prefix;')
    require(declaration < task < text.index('    bsg_k++;'), 'Observer declaration must precede original task use')
    require(text.index('  task automatic bsg_checkpoint;') < task,
            'Checkpoint observer must precede its inherited caller')
    for name in ('bsg_case', 'bsg_k', 'bsg_m', 'bsg_n', 'bsg_kb', 'bsg_requests', 'bsg_fmas',
                 'bsg_seeds', 'bsg_checkpoints', 'bsg_nonzero', 'bsg_normal'):
        first = re.search(r'\b' + name + r'\b', text)
        require(first is not None and declaration <= first.start() < task,
                'Observer variable referenced before declaration: ' + name)


def relocate_observers(original, block):
    require(sha(original) == FIRST_TB_SHA and block and original.count(block) == 1,
            'Exact sealed original TB and observation block required')
    anchor = '  task automatic continue_after_prefix;'
    require(original.count(anchor) == 1, 'Continuation task anchor count')
    fixed = original.replace(block, '', 1).replace(anchor, block + anchor, 1)
    old_location = "\n  qbs_compute_engine_balanced #(.SeedRestoreEnable(1'b1),"
    require(fixed.count(old_location) == 1 and fixed.replace(block, '', 1).replace(
        old_location, block + old_location, 1) == original, 'Observer movement must restore the entire original TB')
    require(fixed.replace(block, '', 1) == original.replace(block, '', 1), 'Non-observer TB content changed')
    validate_declaration_order(fixed)
    return fixed


def patch_function(source, name, replacements):
    require(sha(source) == FUNCTION_SHAS[name], 'Original function SHA: ' + name)
    text, edits = source, []
    for before, after in replacements:
        require(text.count(before) == 1, 'Exact successor function anchor: ' + name)
        text = text.replace(before, after, 1)
        edits.append(dict(before=before, after=after))
    restored = text
    for edit in reversed(edits):
        require(restored.count(edit['after']) == 1, 'Ambiguous successor inverse')
        restored = restored.replace(edit['after'], edit['before'], 1)
    require(restored == source, 'Function repair not reversible')
    return text, edits


def build():
    for path, expected in PROOF_PINS.items():
        require(digest(path) == expected, 'Original failure/input identity changed: ' + str(path))
    failure, commands = read(FIRST / 'worker/result.json'), read(FIRST / 'worker/commands.json')
    admit_failure(failure, commands, (FIRST / 'worker/compile.log').read_text())
    require(commands[0]['argv'] == read(FIRST / 'compile-command.json')['argv'] and
            commands[0]['cwd'] == str(FIRST / 'worker'), 'Original actual compile recipe mismatch')
    parent = importlib.import_module('balanced_seed_gate')
    require(Path(parent.__file__).resolve() == (HERE / 'balanced_seed_gate.py').resolve(), 'Original module root')
    sources = {name: inspect.getsource(getattr(parent, name)) for name in FUNCTION_SHAS}
    insertion = "    edit('checkpoint-proof',"
    added = '''    edit('observers-before-original-tasks', '  task automatic continue_after_prefix;',
         OBSERVATIONS + '  task automatic continue_after_prefix;')
'''
    bench, bench_edits = patch_function(sources['bench_source'], 'bench_source', [
        ('         OBSERVATIONS + "\\n  qbs_compute_engine_balanced',
         '         "\\n  qbs_compute_engine_balanced'),
        (insertion, added + insertion),
    ])
    try_anchor = "    try:\n        pin(PARENT / 'result.json', PARENT_SHA)"
    new_try = '''    try:
        for path, expected in SUCCESSOR_PINS.items():
            pin(path, expected)
        write(out / 'declaration-order-fix.json', DECLARATION_FIX)
        write(out / 'successor-functions.json', SPECIALIZED_FUNCTIONS)
        pin(out / 'declaration-order-fix.json')
        pin(out / 'successor-functions.json')
        pin(PARENT / 'result.json', PARENT_SHA)'''
    import_anchor = "        tests = __import__('test_balanced_seed_gate')"
    module_anchor = "            if path and Path(path).resolve().parent == HERE and Path(path).name not in OWNED:"
    prepare, prepare_edits = patch_function(sources['prepare'], 'prepare', [
        (try_anchor, new_try),
        (import_anchor, "        tests = __import__('test_balanced_seed_gate_v2')"),
        (module_anchor, module_anchor[:-1] + ' and str(Path(path).resolve()) not in pins:'),
    ])
    for name in ('execute', 'ownership'):
        require(sha(sources[name]) == FUNCTION_SHAS[name], 'Unchanged worker/ownership function SHA')
    specialized = dict(bench_source=bench, prepare=prepare, execute=sources['execute'], ownership=sources['ownership'])
    report = dict(state='DECLARATION_ORDER_ONLY_SEED_SUCCESSOR_PREPARED',
        original_helper_sha256=ORIGINAL_HELPER_SHA, original_test_sha256=ORIGINAL_TEST_SHA,
        original_prepared_result_sha256=FIRST_PREPARED_SHA, original_worker_result_sha256=FIRST_FAILED_SHA,
        original_compile_log_sha256=PROOF_PINS[FIRST / 'worker/compile.log'],
        original_failure_relabelled=False, original_worker_modified=False,
        original_tb_sha256=FIRST_TB_SHA, physical_weight_bits=128,
        correction='Move the identical OBSERVATIONS block before continue_after_prefix',
        rtl_vectors_checker_fault_and_goldens_unchanged=True,
        original_checker_and_vector_functions_reused=True,
        compile_budget=1, simulation_modes=['unsplit', 'split'], performance_measured=False,
        bench_function_edits=bench_edits, preparation_function_edits=prepare_edits,
        function_sha256={name: sha(text) for name, text in specialized.items()})
    namespace = dict(vars(parent), __file__=str(Path(__file__).resolve()), OUT=OUT, OWNED=OWNED,
                     PREPARED=PREPARED, SUCCESSOR_PINS=PROOF_PINS, DECLARATION_FIX=report,
                     SPECIALIZED_FUNCTIONS=specialized)
    for name in ('bench_source', 'ownership', 'prepare', 'execute'):
        exec(compile(specialized[name], str(Path(__file__).resolve()), 'exec'), namespace)
    template, helper = parent.TB.read_text(), parent.CONTINUATION.read_text()
    original_bench, _ = parent.bench_source(template, helper)
    expected = relocate_observers(original_bench, parent.OBSERVATIONS)
    actual, _ = namespace['bench_source'](template, helper)
    require(actual == expected, 'Specialized generator changed more than observer placement')
    report['generated_tb_sha256'] = sha(actual)
    return namespace, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--execute-reviewed', action='store_true')
    parser.add_argument('--prepared-sha256')
    args = parser.parse_args()
    namespace, _ = build()
    result = namespace['execute'](args.output, args.prepared_sha256) if args.execute_reviewed else namespace['prepare'](args.output)
    print(json.dumps(dict(state=result['state'], output=str(args.output))))
    return 0 if result['state'] in (PREPARED, namespace['SUCCESS']) else 1


if __name__ == '__main__':
    sys.exit(main())
