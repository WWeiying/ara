"""Reviewed producer admission: ordinary linking, natural layout differences."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as worker

s = worker.s


def receipt_flags(report):
    worker.fields(report, dict(schema='quant_field_copy_pair_prepare_v1',
        state='GNU_PAIR_STATIC_PASS_NOT_EXECUTED', versions=worker.REVISIONS,
        post_pins_match=True, rebuilt_object_count=3, reused_object_count=14,
        numerical_execution_checked=False, simulations_launched=0,
        performance_claim=False, historical_timing_reused=False), 'preparation receipt')
    worker.fields(report['workload'], dict(kind='q4_0', value_kind='q8_0',
        trial_order=[0, 1, 2, 2, 1, 0], trials=6, outputs_per_trial=768, total_outputs=4608,
        expected_commands=16, heads=6, head_dim=128, visible_tokens=128, kv_head=0,
        key_token_stride=144, value_token_stride=272, mapping_timed=True, admission_timed=True,
        gather_timed=True, workspace_bytes=13120, rvv_value_decode=True, rvv_baseline_decode=True,
        original_checks_preserved=True, timeout_seconds=10800), 'complete workload')


def normalized_flags(prepared, report):
    worker.fields(prepared, dict(report['workload'], schema='quantkv_field_copy_pair_prepared_v1',
        state='FIELD_COPY_PAIR_STATIC_PASS_NOT_EXECUTED', execution='NOT_RUN', revisions=worker.REVISIONS,
        matching_compiler_flags=True, matching_fp_policy=True, matching_input_payloads=True,
        affected_objects_rebuilt=True, layout_reviewed=True, post_pins_match=True,
        simulations_launched=0, performance_measured=False), 'producer normalized report')


def checked_pair(receipt, helpers):
    report = s.read_json(receipt)
    receipt_flags(report)
    pins = dict(report['input_pins'])
    s.merge_pins(pins, report['artifacts'])
    s.merge_pins(pins, helpers)
    s.verify_pins(pins)
    prep = worker.PAIR/'prepare'
    producer = worker.load('field_copy_pair_preparation', prep/'build.py', helpers[str(prep/'build.py')])
    s.require(producer.VERSIONS == worker.REVISIONS and producer.WORKLOAD == report['workload'],
              'Preparation revisions/workload differ')
    # Producer owns source/Git, dependency, compile, ELF, tensor, linker and CFG replay.
    prepared, consumed = producer.checked_pair(receipt)
    normalized_flags(prepared, report)
    s.merge_pins(pins, consumed)
    s.require(consumed.get(str(receipt)) == s.digest(receipt), 'Producer did not close receipt identity')
    directory = receipt.parent
    versions = s.read_json(directory/'versions.json')
    s.require(set(versions) == set(worker.SIDES), 'Missing version side')
    old, new = (versions[side]['files'] for side in worker.SIDES)
    s.require(set(new)-set(old) == {producer.NEW} and not set(old)-set(new) and
              {p for p in old if old[p] != new[p]} == producer.CHANGED and
              report['historical_header_translation_only'] == sorted(producer.CHANGED), 'Unexpected software delta')
    worker.fields(report['layout'], dict(matched_addresses_claim=False, historical_elf_layout_claim=False),
                  'natural layout review')
    scripts = [directory/side/'link.ld' for side in worker.SIDES]
    s.require(scripts[0].read_bytes() == scripts[1].read_bytes(), 'Ordinary linker rules differ across sides')
    s.require(set(prepared['programs']) == set(worker.SIDES), 'Need two fresh programs')
    for side in worker.SIDES:
        program, raw = prepared['programs'][side], report['programs'][side]
        worker.fields(program, dict(revision=worker.REVISIONS[side], fresh_build=True,
            elf=raw['elf'], elf_sha256=raw['elf_sha256'], build_receipt=raw['build_receipt'],
            build_receipt_sha256=raw['build_receipt_sha256'], golden=str(worker.accepted.GOLD),
            golden_sha256=s.digest(worker.accepted.GOLD)), 'prepared program')
        for key, sha_key in (('elf', 'elf_sha256'), ('build_receipt', 'build_receipt_sha256'),
                             ('golden', 'golden_sha256')):
            path = worker.path(program[key])
            s.require(pins.get(str(path)) == program[sha_key] == s.digest(path), 'Program/payload receipt drift')
    a, b = (prepared['programs'][side] for side in worker.SIDES)
    s.require(a['elf'] != b['elf'] and a['elf_sha256'] != b['elf_sha256'], 'Same ELF on both sides')
    s.verify_pins(pins)
    return prepared, pins, report


def prepare_inputs(args):
    review_path = worker.path(args.review)
    s.require(s.digest(review_path) == args.review_sha256, 'Parent review SHA differs')
    review = s.read_json(review_path)
    worker.fields(review, dict(schema='field_copy_pair_parent_review_v1', preparation_reviewed=True,
        same_inputs_flags_schedule=True, affected_objects_rebuilt=True, historical_timings_used=False), 'parent review')
    runtime = review['runtime_environment']
    s.require(type(runtime) is dict and set(runtime) == {'LD_LIBRARY_PATH'} and
              (runtime['LD_LIBRARY_PATH'] is None or type(runtime['LD_LIBRARY_PATH']) is str), 'Unreviewed loader environment')
    helpers = review['input_pins']
    required = [*worker.HERE.glob('*.py'), worker.HERE/'README.md', worker.PAIR/'PLAN.md']
    required += [p for p in (worker.PAIR/'prepare').iterdir() if p.is_file() and
                 (p.suffix == '.py' or p.name in ('README.md', '.gitignore'))]
    s.require(all(helpers.get(str(p)) == s.digest(p) for p in required), 'Incomplete frozen helper/parent-plan review')
    s.verify_pins(helpers)
    receipt = worker.path(review['prepared_pair'])
    s.require(s.digest(receipt) == review['prepared_pair_sha256'], 'Prepared receipt SHA differs')
    prepared, pins, report = checked_pair(receipt, helpers)
    soc, canonical_pins, image = worker.accepted.canonical.checked_soc(worker.path(args.soc_build), worker.accepted.SOC_SHA)
    worker.fields(report, dict(canonical_build=str(args.soc_build), canonical_build_sha256=worker.accepted.SOC_SHA,
                               image_pins=image), 'same actual canonical image')
    for group in (canonical_pins, image, worker.own_pins(), s.hashes([review_path, receipt, worker.accepted.GOLD])):
        s.merge_pins(pins, group)
    s.verify_pins(pins)
    return prepared, soc, pins, image, review
