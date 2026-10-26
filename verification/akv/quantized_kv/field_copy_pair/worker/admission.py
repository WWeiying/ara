"""Read-only consumer of preparation's native receipt and pure layout replay."""
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


def checked_pair(receipt, helpers):
    report = s.read_json(receipt)
    receipt_flags(report)
    directory = receipt.parent
    prep = worker.PAIR/'prepare'
    worker.load('layout', prep/'layout.py', helpers[str(prep/'layout.py')])
    producer = worker.load('field_copy_pair_preparation', prep/'build.py', helpers[str(prep/'build.py')])
    s.require(producer.VERSIONS == worker.REVISIONS, 'Preparation revisions differ')
    artifacts, inputs = report['artifacts'], report['input_pins']
    required = [directory/n for n in ('commands.json', 'dependencies.json', 'versions.json',
                'slots.json', 'layout.json', 'input-pins-before.json', 'input-pins-after.json')]
    s.require(all(artifacts.get(str(p)) == s.digest(p) for p in required), 'Incomplete preparation artifacts')
    s.require(inputs == s.read_json(directory/'input-pins-before.json') ==
              s.read_json(directory/'input-pins-after.json'), 'Preparation pre/post inputs differ')
    pins = dict(inputs)
    s.merge_pins(pins, artifacts)
    s.merge_pins(pins, helpers)
    s.verify_pins(pins)
    elf_reader = Path(producer.ELF_READER)
    Elf = worker.load('field_copy_pair_elf', elf_reader, pins[str(elf_reader)]).Elf
    versions = s.read_json(directory/'versions.json')
    s.require(set(versions) == set(worker.SIDES) and set(report['programs']) == set(worker.SIDES), 'Missing pair side')
    main_bytes = (producer.BASE/'attention_threeway_untimed.c').read_bytes()
    for side in worker.SIDES:
        row = versions[side]
        s.require(row['commit'] == worker.REVISIONS[side] and Path(row['tree']) == directory/side/'source' and
                  Path(row['main']) == directory/side/'source/main.c' and
                  Path(row['main']).read_bytes() == main_bytes and
                  row['main_sha256'] == s.digest(Path(row['main'])), 'Snapshot/main source identity differs')
        for relative, sha in row['files'].items():
            p = Path(row['tree'])/relative
            s.require(p.resolve().is_relative_to(Path(row['tree'])) and pins.get(str(p)) == sha == s.digest(p),
                      'Snapshot source inventory differs')
    old, new = (versions[side]['files'] for side in worker.SIDES)
    s.require(set(new)-set(old) == {producer.NEW} and not set(old)-set(new) and
              {p for p in old if old[p] != new[p]} == producer.CHANGED and
              report['historical_header_translation_only'] == sorted(producer.CHANGED), 'Unexpected software delta')
    proofs = s.read_json(directory/'dependencies.json')
    s.require(len(proofs) == 17 and sum(p['rebuilt'] is True for p in proofs) == 3 and
              all(type(p['rebuilt']) is bool for p in proofs), 'Wrong affected/reused object scope')
    rebuilt_sources = {Path(p['original_source']).name for p in proofs if p['rebuilt']}
    s.require('runtime.c' in rebuilt_sources and 'runtime_strided.c' in rebuilt_sources and
              any(Path(p['original_object']) == producer.BASE/'main.o' and p['rebuilt'] for p in proofs),
              'Need main, contiguous runtime and strided runtime rebuilds')
    objects = {side: [] for side in worker.SIDES}
    for proof in proofs:
        original = Path(proof['original_object'])
        s.require(pins.get(str(original)) == proof['original_sha256'] == s.digest(original), 'Original object differs')
        recipe, _ = producer.compile_record(original)
        for side in worker.SIDES:
            row = proof['sides'][side]
            obj = Path(row['object'])
            s.require(pins.get(str(obj)) == row['object_sha256'] == s.digest(obj), 'Prepared object differs')
            expected = list(recipe)
            tree = Path(versions[side]['tree'])
            if proof['rebuilt']:
                s.require(obj.is_relative_to(directory/side) and obj != original, 'Rebuild reused historical object')
                src = tree/'main.c' if original == producer.BASE/'main.o' else tree/Path(proof['original_source']).relative_to(worker.ROOT)
                expected[expected.index('-c')+1] = str(src)
                expected[expected.index('-o')+1] = str(obj)
                expected.insert(1, '-I'+str(tree))
            else:
                s.require(obj == original, 'Unreviewed reused-object substitution')
            s.require(row['compile_argv'] == expected, 'Compiler/FP flags differ from original recipe')
            deps = row['dependencies']
            s.require(deps and all(pins.get(p) == sha for p, sha in deps.items()), 'Missing dependency pins')
            if not proof['rebuilt']:
                s.require(not any(Path(p).is_relative_to(worker.ROOT) and
                    Path(p).relative_to(worker.ROOT).as_posix() in producer.CHANGED | {producer.NEW} for p in deps),
                    'Changed header consumer was reused')
            if original == producer.BASE/'main.o':
                s.require(all(str(tree/producer.QDIR/n) in deps for n in
                    ('ggml_decode.h', 'q8_0_value.h', 'online.h', 'selection.h')) and
                    ((str(tree/producer.NEW) in deps) == (side == 'candidate')), 'Missing mapper/admission/V rebuild')
            objects[side].append(obj)
    commands = s.read_json(directory/'commands.json')
    s.require(commands and all(type(r['exit_code']) is int and r['exit_code'] == 0 and
              r['timeout_seconds'] == 120 and r['cwd'] == str(directory) and
              artifacts.get(r['log']) == s.digest(Path(r['log'])) for r in commands), 'GNU stage evidence differs')
    for proof in proofs:
        for side in worker.SIDES:
            argv = proof['sides'][side]['compile_argv']
            for expected in ([argv] if proof['rebuilt'] else [])+[producer.deps_command(argv)]:
                s.require(sum(r['argv'] == expected for r in commands) == 1, 'Missing/duplicate dependency or compile command')
    table = producer.layout.slots(objects, Elf)
    s.require(table == s.read_json(directory/'slots.json'), 'Common section slots differ')
    programs = {}
    for side in worker.SIDES:
        entry = report['programs'][side]
        elf, build = directory/side/'attention.elf', directory/side/'build.json'
        worker.fields(entry, dict(elf=str(elf), elf_sha256=s.digest(elf), build_receipt=str(build),
                                 build_receipt_sha256=s.digest(build)), 'program receipt references')
        side_report = s.read_json(build)
        worker.fields(side_report, dict(state='GNU_BUILT_NOT_EXECUTED', side=side, commit=worker.REVISIONS[side],
            elf=str(elf), elf_sha256=entry['elf_sha256'], workload=report['workload'], sources=versions[side]), 'side build')
        s.require((directory/side/'link.ld').read_text() == producer.layout.script(
                  (producer.BASE/'link.ld').read_text(), objects[side], table), 'Paired linker script differs')
        programs[side] = dict(elf=str(elf), elf_sha256=entry['elf_sha256'],
            golden=str(worker.accepted.GOLD), golden_sha256=s.digest(worker.accepted.GOLD))
    parsed = [Elf(Path(programs[side]['elf'])) for side in worker.SIDES]
    layout = producer.layout.compare(*parsed, Elf(producer.BASE/'threeway_attention.elf'),
                                     s.read_json(producer.BASE/'layout-review.json'), table)
    s.require(layout == report['layout'] == s.read_json(directory/'layout.json'), 'Actual layout/payload review differs')
    s.require(all(p.payload('attention_golden', 6144) == worker.accepted.GOLD.read_bytes() for p in parsed),
              'Linked original capture gold differs')
    s.require(programs['baseline']['elf_sha256'] != programs['candidate']['elf_sha256'], 'Same ELF on both sides')
    s.verify_pins(pins)
    return dict(programs=programs), pins, report


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
