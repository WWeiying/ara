#!/usr/bin/env python3
"""Prepare a GNU recipe; --build executes GNU only, never a simulator."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRODUCER = ROOT / 'verification/akv/quantized_kv/field_copy_pair/prepare/build.py'
PRODUCER_SHA = 'ed1943dc6cdedcc425bb99dad0a3000b74de4730d4af4fb4a05c281f80df1eb9'
PRIOR = PRODUCER.parent / 'out/build-gnu-06/build.json'
PRIOR_SHA = 'ddbe521cdcd0157cbed04096a8825d4a9569233905777e6de6e58ec186c95cfc'
QDIR = Path('software/akv/experimental/quantized_kv')
# Set only after Agent2's API/TU FP policy is reviewed; never infer flags.
# Entries: (SDK-relative C filename, "fast" or "off").
NEW_TUS = ()


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def reviewed_producer():
    require(sha(PRODUCER) == PRODUCER_SHA, 'Frozen producer changed')
    spec = importlib.util.spec_from_file_location('grouped_pair_frozen_gnu_helpers', PRODUCER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def historical_pins(prior, directory):
    """Old artifacts stay immutable; SDK input identity moves only to exact blobs."""
    pins = dict(prior['artifacts'])
    translations = {}
    for name, expected in prior['input_pins'].items():
        path = Path(name)
        if path.is_relative_to(ROOT / QDIR):
            archived = directory / 'candidate/source' / path.relative_to(ROOT)
            require(archived.is_file() and sha(archived) == expected, 'No exact historical SDK blob: ' + name)
            translations[name] = str(archived)
            path = archived
        require(str(path) not in pins or pins[str(path)] == expected, 'Historical pin collision')
        pins[str(path)] = expected
    for name, expected in pins.items():
        require(sha(name) == expected, 'Historical artifact/input drift: ' + name)
    pins[str(PRIOR)] = PRIOR_SHA
    return pins, translations


def prepare(output):
    output = Path(output).absolute()
    require(output == output.resolve() and not output.exists() and output.is_relative_to(HERE / 'out'),
            'Use fresh pair/out directory')
    adapter = HERE / 'sdk_adapter.h'
    require(adapter.is_file(), 'SDK API not landed/reviewed: sdk_adapter.h missing; no build was launched')
    require(sha(PRIOR) == PRIOR_SHA, 'Accepted field-copy receipt changed')
    prior = json.loads(PRIOR.read_text())
    require(prior['state'] == 'GNU_PAIR_STATIC_PASS_NOT_EXECUTED', 'Wrong historical program scope')
    pins, translations = historical_pins(prior, PRIOR.parent)
    producer = reviewed_producer()
    sdk_files = sorted(p for p in (ROOT / QDIR).iterdir() if p.suffix in ('.c', '.h'))
    require({p.name for p in sdk_files if p.suffix == '.c'} ==
            {'runtime.c', 'runtime_strided.c'} | {name for name, _ in NEW_TUS},
            'New SDK C units need explicit reviewed NEW_TUS FP policy')
    require(all(fp in ('fast', 'off') and Path(name).name == name for name, fp in NEW_TUS), 'Invalid new TU policy')
    output.mkdir(parents=True)
    tree = output / 'source'
    copied = {}

    def copy(source, relative):
        data = source.read_bytes()
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        value = hashlib.sha256(data).hexdigest()
        pins[str(source)] = pins[str(target)] = value
        copied[str(source)] = dict(copy=str(target), sha256=value)

    for path in sdk_files:
        copy(path, path.relative_to(ROOT))
    for relative in producer.VFILES:
        copy(ROOT / relative, Path(relative))
    copy(HERE / 'main.c', Path('main.c'))
    copy(adapter, Path('sdk_adapter.h'))
    for p in sorted(p for p in HERE.iterdir() if p.is_file()):
        pins[str(p)] = sha(p)
    pins[str(Path(sys.executable).resolve())] = sha(Path(sys.executable).resolve())
    pins[str(PRODUCER)] = PRODUCER_SHA
    pins[str(PRODUCER.parent / 'layout.py')] = sha(PRODUCER.parent / 'layout.py')
    original_link = next(r['argv'] for r in json.loads((producer.BASE / 'commands.json').read_text()) if r['label'] == 'link')
    objects = [Path(p) for p in original_link if p.endswith('.o')]
    commands, replacements = [], {}
    runtime_template = None
    for index, obj in enumerate(objects):
        argv, recipe = producer.compile_record(obj)
        source = Path(argv[argv.index('-c') + 1])
        pins[str(recipe)] = sha(recipe)
        if obj != producer.BASE / 'main.o' and source.name not in ('runtime.c', 'runtime_strided.c'):
            continue
        if source.name == 'runtime.c':
            runtime_template = list(argv)
        target = output / ('object-' + str(index) + '.o')
        argv = list(argv)
        argv[argv.index('-c') + 1] = str(tree / 'main.c' if obj == producer.BASE / 'main.o' else tree / source.relative_to(ROOT))
        argv[argv.index('-o') + 1] = str(target)
        argv.insert(1, '-I' + str(tree))
        replacements[str(obj)] = str(target)
        commands += [dict(kind='dependencies', argv=producer.deps_command(argv)), dict(kind='compile', argv=argv)]
    require(len(replacements) == 3 and runtime_template is not None, 'Missing dependent object rebuild')
    new_objects = []
    for name, fp in NEW_TUS:
        argv = list(runtime_template)
        argv[argv.index('-c') + 1] = str(tree / QDIR / name)
        target = output / (name + '.o')
        argv[argv.index('-o') + 1] = str(target)
        argv = ['-ffp-contract=' + fp if x.startswith('-ffp-contract=') else x for x in argv]
        argv.insert(1, '-I' + str(tree))
        new_objects.append(str(target))
        commands += [dict(kind='dependencies', argv=producer.deps_command(argv)), dict(kind='compile', argv=argv)]
    ld = output / 'link.ld'
    ld.write_text(producer.layout.script((producer.BASE / 'link.ld').read_text()))
    elf = output / 'grouped_attention.elf'
    link = [replacements.get(x, x) for x in original_link]
    link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = new_objects
    link[link.index('-o') + 1] = str(elf)
    link[link.index('-T') + 1] = str(ld)
    link = ['-Wl,-Map=' + str(output / 'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
    commands.append(dict(kind='link', argv=link))
    commands.append(dict(kind='disassemble', argv=[str(Path(link[0]).with_name('riscv64-unknown-elf-objdump')), '-d', str(elf)]))
    save(output / 'planned-commands.json', commands)
    save(output / 'source-pins.json', pins)
    producer.verify(pins)
    golden = ROOT / ('verification/out/akv-quantkv-host-capture-20261024-01/'
                     'capture-k-q4_0-v-q8_0/decode/block/kqv_out-0.bin')
    require(pins.get(str(golden)) == sha(golden), 'Original capture golden missing from pins')
    result = dict(state='RECIPE_PREPARED_NOT_COMPILED', simulations_launched=0, commands_executed=0,
        compiler_invoked=False, elf=str(elf), elf_exists=elf.exists(), same_sdk_both_arms=True,
        trial_order=[0, 1, 1, 0], trials=4, outputs_per_trial=768, expected_qbs_commands=32,
        golden=str(golden), golden_sha256=sha(golden),
        historical_elf=prior['programs']['candidate']['elf'],
        current_sdk_copies=copied, historical_translation=translations,
        input_pins=pins, planned_commands_sha256=sha(output / 'planned-commands.json'), linker_sha256=sha(ld),
        post_pins_match=True, build_acceptance=False, numerical_execution_checked=False,
        required_postbuild=['actual GNU dependency checks', 'all original tensor/golden payloads',
                            'grouped RVV body/admission proof', 'main timer CFG/drain', 'canonical checked_soc'])
    save(output / 'prepare.json', result)
    return result


def reused_dependencies(prior, pins):
    """Bind unchanged objects to the accepted dependency proof, not names alone."""
    proof_path = PRIOR.parent / 'dependencies.json'
    require(prior['artifacts'].get(str(proof_path)) == sha(proof_path), 'Dependency archive identity')
    proofs = json.loads(proof_path.read_text())
    require(len(proofs) == 17 and sum(p['rebuilt'] for p in proofs) == 3, 'Original object inventory')
    reused = []
    for proof in proofs:
        if proof['rebuilt']:
            continue
        row = proof['sides']['candidate']
        require(row['object'] == proof['original_object'] and
                row['object_sha256'] == proof['original_sha256'] == sha(row['object']), 'Reused object identity')
        require(row['dependencies'], 'Empty reused dependency inventory')
        for name, digest in row['dependencies'].items():
            require(not Path(name).is_relative_to(ROOT / QDIR), 'Affected SDK dependency reused')
            require(pins.get(name) == digest == sha(name), 'Unproven reused dependency: ' + name)
        reused.append(row)
    require(len(reused) == 14, 'Need fourteen unchanged objects')
    return reused


def linked_review(producer, elf_path, disassembly):
    Elf = producer.load('grouped_pair_elf', producer.ELF_READER).Elf
    elf = Elf(elf_path)
    main = elf.symbols['main']
    rows = []
    for line in disassembly.splitlines():
        match = re.fullmatch(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)', line)
        if match and main['address'] <= int(match[1], 16) < main['address'] + main['size']:
            rows.append(dict(pc=int(match[1], 16), encoding=match[2], text=match[3]))
    cycles = [r for r in rows if re.match(r'rdcycle\s', r['text'])]
    require(len(cycles) == 2 and all(int(r['encoding'], 16) & 0xfffff07f == 0xc0002073 for r in cycles),
            'Need exact rdcycle boundaries')
    cfg = producer.layout.timed_cfg(rows, cycles)
    apis = ('akv_quant_strided_execute', 'akv_quant_strided_execute_grouped_pv')
    for name in apis:
        require(name in elf.symbols and any('<' + name + '>' in r['text'] for r in cfg['calls']),
                'Missing timed linked API call: ' + name)
    end_index = rows.index(cycles[1])
    require(any(r['text'].startswith('fence') for r in rows[max(0, end_index-8):end_index]) and
            any('vmv.x.s' in r['text'] for r in rows[max(0, end_index-8):end_index]), 'End drain ordering')
    require('strided_value_decode' in elf.symbols and 'vfmacc.vf' in disassembly, 'Missing RVV primitives')
    # Match actual model data, not compiler-generated pools or code placement.
    mapping = producer.layout.compare(elf, elf, Elf(producer.BASE / 'threeway_attention.elf'),
                                       json.loads((producer.BASE / 'layout-review.json').read_text()))
    return dict(rdcycle_sites=cycles, timed_cfg=cfg, main_instructions=rows,
                api_ids={str(i): name for i, name in enumerate(apis)}, layout=mapping,
                linked_api_calls=True, source_no_retry_contract=True,
                dynamic_selection_checked=False, manual_linked_body_review_required=True)


def build(output, recipe):
    """Fresh objects include mapper/Q8 V decoder and both current SDK schedulers."""
    output = Path(output).absolute()
    producer = reviewed_producer()
    pins, records = dict(recipe['input_pins']), []
    for name in ('link.ld', 'planned-commands.json', 'prepare.json', 'source-pins.json'):
        pins[str(output / name)] = sha(output / name)
    try:
        reused = reused_dependencies(json.loads(PRIOR.read_text()), pins)
        plans = json.loads((output / 'planned-commands.json').read_text())
        dependencies = []
        disassembly = None
        for index, command in enumerate(plans):
            argv = command['argv']
            require(str(Path(argv[0])) in pins, 'Tool not in accepted inventory')
            log = producer.run_command(argv, output, f'{index:02d}-{command["kind"]}', pins, records)
            if command['kind'] == 'dependencies':
                deps = producer.parse_deps(log.read_text())
                require(deps, 'Empty GNU dependencies')
                for path in deps:
                    require(not path.is_relative_to(ROOT / QDIR), 'Live SDK leaked into snapshot build')
                    require(pins.get(str(path)) == sha(path), 'Unknown GNU dependency: ' + str(path))
                dependencies.append(dict(argv=argv, files={str(p): sha(p) for p in deps}))
            elif command['kind'] == 'disassemble':
                disassembly = log
        require(len(dependencies) == 3 and disassembly is not None, 'Incomplete rebuild')
        all_deps = {p for row in dependencies for p in row['files']}
        require(all(str(output / 'source' / QDIR / name) in all_deps for name in
                    ('ggml_decode.h', 'q8_0_value.h', 'online.h', 'grouped_pv.h', 'selection_strided.h')),
                'Missing affected inline rebuild')
        elf = Path(recipe['elf'])
        review = linked_review(producer, elf, disassembly.read_text())
        save(output / 'linked-review.json', review)
        save(output / 'dependencies.json', dict(rebuilt=dependencies, reused=reused))
        producer.verify(pins)
        save(output / 'input-pins-before.json', pins)
        producer.verify(pins)
        save(output / 'input-pins-after.json', pins)
        result = dict(schema='grouped_pv_pair_build_v1', state='GNU_BUILT_NOT_EXECUTED',
            elf=str(elf), elf_sha256=sha(elf), input_pins=pins,
            artifacts={str(p): sha(p) for p in output.rglob('*') if p.is_file() and p.name != 'worker.log'},
            trial_order=[0, 1, 1, 0], outputs_per_trial=768, expected_qbs_commands=32,
            rebuilt_objects=3, reused_objects=14, api_evidence=review,
            same_sdk_both_arms=True, golden=recipe['golden'], golden_sha256=recipe['golden_sha256'],
            post_pins_match=True, simulations_launched=0, numerical_execution_checked=False)
        save(output / 'build.json', result)
        return result
    except BaseException as exc:
        save(output / 'build.json', dict(state='FAIL', error=repr(exc), simulations_launched=0))
        raise


def checked_build(receipt):
    receipt = Path(receipt).resolve(strict=True)
    result = json.loads(receipt.read_text())
    require(result['schema'] == 'grouped_pv_pair_build_v1' and result['state'] == 'GNU_BUILT_NOT_EXECUTED' and
            result['trial_order'] == [0, 1, 1, 0] and result['outputs_per_trial'] == 768 and
            result['expected_qbs_commands'] == 32 and result['post_pins_match'] is True and
            result['simulations_launched'] == 0, 'Invalid grouped build receipt')
    pins = dict(result['input_pins'])
    for name, digest in result['artifacts'].items():
        require(name not in pins or pins[name] == digest, 'Conflicting pin')
        pins[name] = digest
    producer = reviewed_producer()
    producer.verify(pins)
    root = receipt.parent
    require(json.loads((root / 'input-pins-before.json').read_text()) ==
            json.loads((root / 'input-pins-after.json').read_text()) == result['input_pins'], 'Input maps differ')
    commands = json.loads((root / 'commands.json').read_text())
    plans = json.loads((root / 'planned-commands.json').read_text())
    require(len(commands) == len(plans) == 8 and all(c['exit_code'] == 0 and c['argv'] == p['argv']
            for c, p in zip(commands, plans)), 'Incomplete GNU ledger')
    require(sha(result['elf']) == result['elf_sha256'] and sha(result['golden']) == result['golden_sha256'],
            'ELF/golden identity')
    review = linked_review(producer, Path(result['elf']), Path(commands[-1]['log']).read_text())
    require(review == result['api_evidence'] == json.loads((root / 'linked-review.json').read_text()),
            'Linked replay mismatch')
    reused = reused_dependencies(json.loads(PRIOR.read_text()), pins)
    require(reused == json.loads((root / 'dependencies.json').read_text())['reused'], 'Dependency replay mismatch')
    pins[str(receipt)] = sha(receipt)
    return result, pins


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build', action='store_true', help='Execute bounded GNU commands, never VCS')
    args = parser.parse_args()
    recipe = prepare(args.output)
    print((build(args.output, recipe) if args.build else recipe)['state'])
