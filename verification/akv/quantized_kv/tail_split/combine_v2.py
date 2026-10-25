#!/usr/bin/env python3
"""Profile-bound four-tail receipt; immutable raw checker and prior failures retained."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split.scope import HERE, ROOT, command_count
from verification.akv.quantized_kv.tail_split import query_reference_v2 as ref

spec = importlib.util.spec_from_file_location('_tail_combine_v2_legacy', HERE / 'combine.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
s = legacy.s
old_checked_run = legacy.checked_run
CAPTURE = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01'
QUANTIZER = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/quants.c')
QUANT_OBJECT = ROOT / 'verification/out/akv-quantkv-rvv-primitives-20261024-01/ggml_rvv_quants.o'
FUNCTION_SHA = '33d366787ae6e0650d15914975085c2292e6b2fe1e6981802da5b39228384153'
LEGACY_SHA = '925404c1d09368c46695989ebcf00693a5aa35b1ea0970dfa67242facc965df0'
OWN = [HERE / name for name in ('combine_v2.py', 'test_combine_v2.py', 'query_reference_v2.py')]
SCHEMA = 'TAIL_QUERY_CAPTURE_BINDING_V2'
REFERENCE = 'FINITE_NORMAL_F32_RNE_Q8_0_SIX_HEADS_NO_FFLAGS_PROOF'


def query_path(kind):
    s.require(kind in ('q4_0', 'q8_0'), 'Unknown profile')
    return CAPTURE / ('capture-k-' + kind + '-v-q8_0/decode/block/attn_q_input-0.bin')


def joined_query(record):
    queries = record.get('query_hex')
    s.require(type(queries) is dict and set(queries) == {str(i) for i in range(6)} and
              all(type(q) is str and re.fullmatch('[0-9a-f]{272}', q) for q in queries.values()),
              'Missing complete Query identity')
    return b''.join(bytes.fromhex(queries[str(i)]) for i in range(6))


def strict_fields(record, wanted, message):
    s.require(type(record) is dict and all(type(record.get(k)) is type(v) and record[k] == v
                                         for k, v in wanted.items()), message)


def validate_binding(record):
    binding = record.get('query_binding')
    kind = record['kind']
    strict_fields(binding, dict(schema=SCHEMA, kind=kind, capture_query=str(query_path(kind)),
                  capture_bytes=6144, selected_heads=[0, 1, 2, 3, 4, 5], selected_bytes=3072,
                  quantized_bytes=816, reference=REFERENCE, independent_fflags=False,
                  quantizer_source=str(QUANTIZER), quantizer_function_sha256=FUNCTION_SHA,
                  quantizer_object=str(QUANT_OBJECT)), 'Wrong profile Query binding')
    for name in ('capture_sha256', 'selected_sha256', 'elf_query_sha256',
                 'quantizer_source_sha256', 'quantizer_object_sha256', 'quantized_sha256',
                 'capture_receipt_sha256'):
        s.require(type(binding.get(name)) is str and re.fullmatch('[0-9a-f]{64}', binding[name]),
                  'Missing binding digest: ' + name)
    s.require(binding['capture_sha256'] == binding['elf_query_sha256'] and
              binding['quantized_sha256'] == ref.digest(joined_query(record)), 'Query binding mismatch')
    identity = record.get('run_identity')
    s.require(type(identity) is dict and set(identity) == {'directory', 'result_sha256', 'status_sha256',
                                                         'source_pins_sha256', 'elf_sha256'},
              'Missing original run identity')
    s.require(type(identity['directory']) is str and Path(identity['directory']).is_absolute(),
              'Nonabsolute run identity')
    for name in ('result_sha256', 'status_sha256', 'source_pins_sha256', 'elf_sha256'):
        s.require(type(identity[name]) is str and re.fullmatch('[0-9a-f]{64}', identity[name]),
                  'Missing run identity digest')
    s.require(identity['elf_sha256'] == record.get('elf_sha256') and
              identity['source_pins_sha256'] == record.get('source_pins_sha256'), 'Run identity mismatch')


def checked_run(directory):
    s.require(s.digest(HERE / 'combine.py') == LEGACY_SHA, 'Legacy checker changed')
    result, build, pins = old_checked_run(directory)
    result = dict(result)  # Never modify a terminal receipt on disk.
    kind = result['kind']
    path = query_path(kind)
    metadata = path.with_suffix('.json')
    receipt = CAPTURE / 'result.json'
    captured = s.read_json(receipt)['captures'][kind]['file_sha256']
    for file in (path, metadata, receipt, QUANTIZER, QUANT_OBJECT):
        s.require(pins.get(str(file)) == s.digest(file), 'Missing/drifting Query provenance: ' + str(file))
    for file in (path, metadata):
        s.require(captured.get(str(file)) == s.digest(file), 'Capture/profile pin mismatch')
    strict_fields(s.read_json(metadata), dict(type='f32', shape=[128, 1, 12, 1],
                  strides=[4, 512, 512, 6144], nbytes=6144), 'Unexpected capture Query layout')
    source = QUANTIZER.read_bytes()
    start, end = b'void quantize_row_q8_0(', b'void quantize_row_q8_1('
    s.require(source.count(start) == source.count(end) == 1, 'Ambiguous production quantizer')
    s.require(ref.digest(source[source.index(start):source.index(end)]) == FUNCTION_SHA,
              'Production quantizer semantics changed')
    commands = s.read_json(Path(result['build']) / 'commands.json')
    links = [r['argv'] for r in commands if '-nostdlib' in r['argv']]
    s.require(len(links) == 1 and links[0].count(str(QUANT_OBJECT)) == 1, 'Unbound production quantizer object')
    capture = path.read_bytes()
    elf = Path(build['elf']).read_bytes()
    s.require(ref.digest(elf) == build['elf_sha256'] == result['elf_sha256'], 'ELF identity mismatch')
    embedded = ref.elf_query(elf)
    s.require(embedded == capture, 'ELF Query is not the profile capture')
    quantized = ref.reconstruct(capture)
    s.require(quantized == joined_query(result), 'Captured F32 to exported Query reconstruction differs')
    result['query_binding'] = dict(schema=SCHEMA, kind=kind, capture_query=str(path),
        capture_bytes=6144, selected_heads=[0, 1, 2, 3, 4, 5], selected_bytes=3072,
        capture_sha256=ref.digest(capture), selected_sha256=ref.digest(capture[:3072]),
        elf_query_sha256=ref.digest(embedded), quantized_bytes=816, quantized_sha256=ref.digest(quantized),
        quantizer_source=str(QUANTIZER), quantizer_source_sha256=s.digest(QUANTIZER),
        quantizer_function_sha256=FUNCTION_SHA, quantizer_object=str(QUANT_OBJECT),
        quantizer_object_sha256=s.digest(QUANT_OBJECT), capture_receipt_sha256=s.digest(receipt),
        reference=REFERENCE, independent_fflags=False)
    directory = directory.resolve(strict=True)
    result['run_identity'] = dict(directory=str(directory), result_sha256=s.digest(directory / 'result.json'),
        status_sha256=s.digest(directory / 'status.json'), source_pins_sha256=result['source_pins_sha256'],
        elf_sha256=result['elf_sha256'])
    validate_binding(result)
    s.merge_pins(pins, s.hashes(OWN))
    s.verify_pins(pins)
    return result, build, pins


def validate_matrix(records):
    s.require(type(records) is list and len(records) == 4, 'All four split runs required')
    matrix = {}
    for result in records:
        prefixes = result.get('prefixes')
        s.require(type(prefixes) is list and len(prefixes) == 1 and
                  type(prefixes[0]) is int and prefixes[0] in (5, 33), 'Wrong prefix scope')
        key = result.get('kind'), prefixes[0]
        s.require(key[0] in ('q4_0', 'q8_0') and key not in matrix, 'Duplicate/unknown split')
        strict_fields(result, dict(state='PASS', post_pins_match=True, independent_protocol_checked=True,
                      simulator_exit_code=0, commands=command_count(key[1]), native_calls=2,
                      outputs_per_trial=768), 'Incomplete independently checked split')
        s.require(type(result.get('trials')) is list and len(result['trials']) == 3, 'Wrong trial count')
        validate_binding(result)
        matrix[key] = result
    s.require(set(matrix) == {(k, v) for k in ('q4_0', 'q8_0') for v in (5, 33)}, 'Incomplete matrix')
    s.require(len({r['run_identity']['directory'] for r in records}) == 4, 'Duplicated original run')
    for kind in ('q4_0', 'q8_0'):
        a, b = matrix[kind, 5], matrix[kind, 33]
        s.require(a['query_hex'] == b['query_hex'] and a['query_binding'] == b['query_binding'],
                  'Query/provenance differs within profile')
    # There is deliberately no cross-profile equality OR inequality condition.
    return dict(state='PASS', acceptance='TAIL_SPLIT_COMBINED_PASS_V2', schema_version=2,
                query_binding_schema=SCHEMA, split_runs=4, profiles=['q4_0', 'q8_0'], prefixes=[5, 33],
                trials=12, commands=24, native_calls=8, outputs_per_trial=768,
                original_timeout_reclassified=False, performance=False, whole_model=False,
                query_reference=REFERENCE, independent_query_fflags=False,
                query_bindings={k: matrix[k, 5]['query_binding'] for k in ('q4_0', 'q8_0')},
                run_identities=[matrix[k, v]['run_identity'] for k in ('q4_0', 'q8_0') for v in (5, 33)],
                records=records)


legacy.checked_run = checked_run
legacy.validate_matrix = validate_matrix


def combine(runs, out):
    # The unchanged implementation retains all original TIMEOUT identities and
    # performs its normal image/prerequisite comparison and pre/post pin checks.
    return legacy.combine(runs, out)


def checked_combined(out):
    out = out.resolve(strict=True)
    result = s.read_json(out / 'result.json')
    strict_fields(result, dict(state='PASS', acceptance='TAIL_SPLIT_COMBINED_PASS_V2', schema_version=2,
                  post_pins_match=True), 'Not a V2 combined receipt')
    s.require(result.get('source_pins_sha256') == s.digest(out / 'source-pins.json'), 'Combined receipt drift')
    pins = s.read_json(out / 'source-pins.json')
    for path in [*OWN, HERE / 'combine.py', HERE / 'check.py', HERE / 'run.py']:
        s.require(pins.get(str(path)) == s.digest(path), 'Missing/drifting combined implementation pin')
    s.verify_pins(pins)
    runs = result.get('runs')
    s.require(type(runs) is list and len(runs) == len(set(runs)) == 4, 'Wrong original run inventory')
    records, builds = [], []
    for name in runs:
        directory = Path(name).resolve(strict=True)
        s.require(str(directory) == name, 'Noncanonical run path')
        for filename in ('result.json', 'status.json', 'source-pins.json'):
            path = directory / filename
            s.require(pins.get(str(path)) == s.digest(path), 'Missing original run identity pin')
        record, build, inherited = checked_run(directory)
        s.require(all(pins.get(k) == v for k, v in inherited.items()), 'Combined omitted consumed run pins')
        records.append(record)
        builds.append(build)
    expected = validate_matrix(records)
    strict_fields(result, expected, 'Combined schema/bindings differ from original runs')
    s.require(json.dumps({k: result[k] for k in expected}, sort_keys=True) ==
              json.dumps(expected, sort_keys=True), 'Combined nested types/records differ')
    s.require(all(b['accepted_image_pins'] == builds[0]['accepted_image_pins'] for b in builds) and
              all(r['prerequisite'] == records[0]['prerequisite'] for r in records), 'Mixed image/prerequisite')
    originals = []
    for kind in ('q4', 'q8'):
        directory = ROOT / f'verification/out/akv-quantkv-tail-attention-{kind}-20261024-01'
        old, status = s.read_json(directory / 'result.json'), s.read_json(directory / 'status.json')
        s.require(old.get('state') == status.get('state') == 'TIMEOUT' and status.get('child_pid') is None,
                  'Original TIMEOUT identity changed')
        evidence = s.hashes([directory / name for name in
                             ('result.json', 'status.json', 'source-pins.json', 'work/run.vcs.log')])
        s.require(all(pins.get(k) == v for k, v in evidence.items()), 'Missing original TIMEOUT pin')
        originals.append(dict(directory=str(directory), state='TIMEOUT', prior_only=True, evidence_sha256=evidence))
    s.require(result.get('original_timeouts') == originals, 'Original failures reclassified or omitted')
    s.verify_pins(pins)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--runs', type=Path, nargs=4, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    combine(args.runs, args.output)
