#!/usr/bin/env python3
"""Fail-closed four-run prerequisite; original TIMEOUTs remain prior failures."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split.scope import HERE, PARENT, ROOT, command_count
from verification.akv.quantized_kv.tail_split.run import s, checked_build, checked_model, oracle_inputs
from verification.akv.quantized_kv.tail_split.check import check_log


def validate_matrix(records):
    s.require(len(records) == 4, 'All four split runs are required')
    matrix = {}
    for result in records:
        prefixes = result.get('prefixes')
        s.require(type(prefixes) is list and len(prefixes) == 1, 'Wrong prefix scope')
        visible = prefixes[0]
        count = command_count(visible)
        key = (result.get('kind'), visible)
        s.require(key[0] in ('q4_0', 'q8_0') and key not in matrix, 'Duplicate/unknown split')
        s.require(result.get('state') == 'PASS' and result.get('post_pins_match') is True and
                  result.get('independent_protocol_checked') is True and
                  result.get('simulator_exit_code') == 0 and
                  result.get('commands') == count and result.get('native_calls') == 2 and
                  result.get('outputs_per_trial') == 768 and len(result.get('trials', [])) == 3,
                  'Split is not a complete independently checked PASS')
        queries = result.get('query_hex', {})
        s.require(set(queries) == {str(i) for i in range(6)} and all(
            type(q) is str and len(q) == 272 and all(c in '0123456789abcdef' for c in q)
            for q in queries.values()), 'Missing complete Query identity')
        matrix[key] = result
    s.require(set(matrix) == {(k, p) for k in ('q4_0', 'q8_0') for p in (5, 33)}, 'Incomplete scope')
    first_queries = records[0]['query_hex']
    s.require(all(r['query_hex'] == first_queries for r in records), 'Query differs across prefix/profile')
    return dict(state='PASS', acceptance='TAIL_SPLIT_COMBINED_PASS', split_runs=4,
                profiles=['q4_0', 'q8_0'], prefixes=[5, 33], trials=12, commands=24,
                native_calls=8, outputs_per_trial=768, original_timeout_reclassified=False,
                performance=False, whole_model=False)


def checked_run(directory):
    directory = directory.resolve(strict=True)
    result = s.read_json(directory / 'result.json')
    status = s.read_json(directory / 'status.json')
    s.require(result.get('state') == status.get('state') == 'PASS' and
              status.get('child_pid') is None and result.get('post_pins_match') is True and
              result.get('independent_protocol_checked') is True and result.get('simulator_exit_code') == 0,
              'Split worker did not finish PASS')
    receipt = directory / 'source-pins.json'
    s.require(result.get('source_pins_sha256') == s.digest(receipt), 'Worker pins receipt drift')
    pins = s.read_json(receipt)
    s.merge_pins(pins, result['evidence_sha256'])
    build = Path(result['build']).resolve(strict=True)
    report, build_pins, gold = checked_build(build)
    s.require(status.get('build') == str(build) and result.get('kind') == report['kind'] and
              result.get('elf_sha256') == report['elf_sha256'], 'Worker/build association differs')
    s.require(all(pins.get(path) == sha for path, sha in build_pins.items()), 'Worker omitted build pins')
    prior = Path(result['prerequisite']).resolve(strict=True)
    prerequisite_pins = {}
    checked_model(prior, prerequisite_pins)
    oracle = oracle_inputs(prerequisite_pins)
    s.require(all(pins.get(path) == sha for path, sha in prerequisite_pins.items()), 'Worker omitted prerequisite/oracle pins')
    log, trace = directory / 'work/run.vcs.log', directory / 'work/vector_trace.csv'
    uvm_path = directory / 'work/uvm_result.json'
    for path in (log, trace, uvm_path, receipt):
        s.require(result['evidence_sha256'].get(str(path)) == s.digest(path), 'Missing/drifting raw evidence')
    key = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
        'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block/attn_k_input-0.bin'
    rtl = ROOT / 'hardware/src/vlsu/vlsu.sv'
    for path in (key, rtl, HERE / 'check.py', HERE / 'run.py', HERE / 'scope.py'):
        s.require(pins.get(str(path)) == s.digest(path), 'Missing semantic input pin')
    s.verify_pins(pins)
    raw = check_log(log.read_text(), int(report['kind'] == 'q4_0'), gold, rtl.read_text(),
                    key.read_bytes(), oracle, report['prefixes'][0])
    for name, value in raw.items():
        if name not in ('state', 'independent_protocol_checked'):
            s.require(result.get(name) == value, 'Raw split evidence disagrees: ' + name)
    s.check_result(uvm_path, report['elf_sha256'], report['accepted_image_pins'])
    uvm = s.read_json(uvm_path)
    s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
              'UVM was checked against different input')
    s.merge_pins(pins, s.hashes([directory / 'result.json', directory / 'status.json', receipt]))
    return result, report, pins


def combine(runs, output):
    out = output.resolve()
    s.require(len(runs) == 4 and len({p.resolve() for p in runs}) == 4, 'Four distinct run directories required')
    s.require(all(not out.is_relative_to(p.resolve()) for p in runs), 'Independent output required')
    results, builds, pins = [], [], {}
    for path in runs:
        result, build, extra = checked_run(path)
        results.append(result)
        builds.append(build)
        s.merge_pins(pins, extra)
    result = validate_matrix(results)
    s.require(all(b['accepted_image_pins'] == builds[0]['accepted_image_pins'] for b in builds), 'Mixed images')
    s.require(all(r['prerequisite'] == results[0]['prerequisite'] for r in results), 'Mixed model prerequisites')
    # Record, but never upgrade, the two original incomplete runs.
    originals = []
    for kind in ('q4', 'q8'):
        old = ROOT / f'verification/out/akv-quantkv-tail-attention-{kind}-20261024-01'
        old_result, old_status = s.read_json(old / 'result.json'), s.read_json(old / 'status.json')
        s.require(old_result.get('state') == old_status.get('state') == 'TIMEOUT' and
                  old_status.get('child_pid') is None, 'Original TIMEOUT identity differs')
        evidence = s.hashes([old / 'result.json', old / 'status.json', old / 'source-pins.json',
                             old / 'work/run.vcs.log'])
        s.merge_pins(pins, evidence)
        originals.append(dict(directory=str(old), state='TIMEOUT', prior_only=True, evidence_sha256=evidence))
    own = [Path(__file__), HERE / 'test_split.py', Path(sys.executable).resolve()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                own.append(path)
    s.merge_pins(pins, s.hashes(own))
    s.verify_pins(pins)
    out.mkdir(parents=True, exist_ok=False)
    s.atomic_json(out / 'source-pins.json', pins)
    result.update(runs=[str(p.resolve()) for p in runs], original_timeouts=originals,
                  source_pins_sha256=s.digest(out / 'source-pins.json'), post_pins_match=True)
    s.verify_pins(pins)
    s.atomic_json(out / 'result.json', result)
    return result


def checked_combined(directory):
    """Continuation admission API: receipt identity, not a substring PASS check."""
    directory = directory.resolve(strict=True)
    result = s.read_json(directory / 'result.json')
    wanted = dict(state='PASS', acceptance='TAIL_SPLIT_COMBINED_PASS', split_runs=4,
                  profiles=['q4_0', 'q8_0'], prefixes=[5, 33], trials=12, commands=24,
                  native_calls=8, outputs_per_trial=768, original_timeout_reclassified=False,
                  performance=False, whole_model=False, post_pins_match=True)
    s.require(all(type(result.get(k)) is type(v) and result[k] == v for k, v in wanted.items()),
              'Not the complete combined tail prerequisite')
    s.require(result.get('source_pins_sha256') == s.digest(directory / 'source-pins.json'), 'Combined receipt drift')
    pins = s.read_json(directory / 'source-pins.json')
    for path in (HERE / 'combine.py', HERE / 'check.py', HERE / 'run.py'):
        s.require(pins.get(str(path)) == s.digest(path), 'Combined checker identity differs')
    s.verify_pins(pins)
    records = []
    for name in result['runs']:
        path = Path(name) / 'result.json'
        s.require(pins.get(str(path)) == s.digest(path), 'Combined run omitted from pins')
        records.append(s.read_json(path))
    validate_matrix(records)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, nargs=4, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    combine(args.runs, args.output)
