#!/usr/bin/env python3
"""Fixed two-version GNU preparation. Never invokes a simulator or EDA tool."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from types import FunctionType, SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
layout_spec = importlib.util.spec_from_file_location('field_copy_pair_layout', HERE / 'layout.py')
layout = importlib.util.module_from_spec(layout_spec)
sys.modules[layout_spec.name] = layout
layout_spec.loader.exec_module(layout)

BASE = ROOT / 'verification/out/q4-untimed-verify-fixed-layout-20261025-01'
VERSIONS = dict(baseline='839a03622130dba7299155f1ccd55c004a6b676a',
                candidate='083d4ed84f47905a675566cc4c459d2e70549ac0')
QDIR = 'software/akv/experimental/quantized_kv/'
CHANGED = {QDIR + n for n in ('ggml_decode.h', 'online.h', 'q8_0_value.h',
                              'selection.h', 'selection_strided.h')}
NEW = QDIR + 'field_copy.h'
VFILES = ['verification/akv/quantized_kv/' + n for n in
          ('threeway_strided_primitives.h', 'attention_main.c', 'shared_rvv_qk.h', 'fast_hex/hex32.h')]
CONSUMER = ROOT / 'verification/akv/quantized_kv/canonical_q4_hsb/run.py'
CONSUMER_SHA = '715dfe948977163c993e6bc0b587c62cec5d15d13f1191e6d8104da41b2bcf79'
ELF_READER = ROOT / 'verification/akv/quantized_kv/phase_diagnostic/prepare/elf.py'
WORKLOAD = dict(kind='q4_0', value_kind='q8_0', trial_order=[0, 1, 2, 2, 1, 0], trials=6,
                outputs_per_trial=768, total_outputs=4608, expected_commands=16, heads=6,
                head_dim=128, visible_tokens=128, kv_head=0, key_token_stride=144,
                value_token_stride=272, mapping_timed=True, admission_timed=True, gather_timed=True,
                workspace_bytes=13120, rvv_value_decode=True, rvv_baseline_decode=True,
                original_checks_preserved=True, timeout_seconds=10800)
GENERATED = {
    'attention-data.S': '0274c283c97aca05e3d8547aacfafce5861f4c5ff7865ed6e6afe265a011f36e',
    'mask.S': '65a5983e0dc81930da92c7b2486b37972c4da4dcea322e373d0764461de365ae',
    'strided-data.S': '61c12daa13f9f3fb5507a9401abf66ffe4d990c2d398a0772ec6d79623fd4e0f',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def verify(pins):
    for p, h in pins.items():
        require(sha(p) == h, 'Input drift: ' + p)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def git(*args):
    return subprocess.check_output(['/usr/bin/git', '-C', str(ROOT), *args], timeout=30)


def blob(version, path):
    return git('show', version + ':' + path)


def translated(pins, baseline):
    result = {}
    for name, expected in pins.items():
        p = Path(name)
        rel = p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else ''
        target = baseline / rel if rel in CHANGED else p
        require(sha(target) == expected, 'Historical pin drift: ' + name)
        result[str(target)] = expected
    return result


def historical(consumer, baseline):
    # Only this private function's verifier changes. Imported modules stay intact.
    namespace = dict(vars(consumer.s))
    namespace['verify_pins'] = lambda pins: verify(translated(pins, baseline))
    globals_ = dict(consumer.checked_program.__globals__, s=SimpleNamespace(**namespace))
    fn = FunctionType(consumer.checked_program.__code__, globals_, 'checked_historical_program')
    report, pins = fn()
    return report, translated(pins, baseline)


def compile_record(obj):
    path = obj.parent / ('predecessor-commands.json' if obj == BASE / 'main.o' else 'commands.json')
    records = json.loads(path.read_text())
    matches = [r['argv'] for r in records if '-c' in r['argv'] and '-o' in r['argv'] and
               (r['argv'][r['argv'].index('-o') + 1] == str(obj) or
                (obj == BASE / 'main.o' and r.get('label') == 'compile'))]
    require(len(matches) == 1, 'Ambiguous compile recipe: ' + str(obj))
    return matches[0], path


def deps_command(cc):
    require(cc.count('-c') == cc.count('-o') == 1, 'Invalid compile argv')
    drop = {cc.index('-c'), cc.index('-o'), cc.index('-o') + 1}
    return [x for i, x in enumerate(cc) if i not in drop] + ['-M', '-MT', 'object']


def parse_deps(text):
    require(text.startswith('object:'), 'Unexpected dependency output')
    return [Path(p).resolve(strict=True) for p in shlex.split(text.replace('\\\n', ' ').split(':', 1)[1])]


def check_dependency(path, tree, inventory, pins):
    if path.is_relative_to(tree):
        require(str(path) in pins and sha(path) == pins[str(path)], 'Unknown overlay dependency')
        return
    rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else ''
    require(not rel.startswith(QDIR) and rel not in VFILES, 'Live header leaked into private build: ' + str(path))
    require(inventory.get(str(path)) == sha(path), 'Unproven original dependency: ' + str(path))
    pins[str(path)] = sha(path)


def generated_inputs(source, obj, inventory, pins):
    require(source.name in GENERATED and sha(source) == GENERATED[source.name], 'Generated source identity')
    receipt = obj.parent / 'build.json'
    report = json.loads(receipt.read_text())
    artifacts = report['artifact_sha256']
    require(artifacts.get(str(obj)) == sha(obj) and artifacts.get(str(source)) == GENERATED[source.name],
            'Original data artifact binding')
    pins[str(receipt)] = sha(receipt)
    inventory.update(artifacts)
    # GNU -M does not report assembler .incbin inputs.
    for name in re.findall(r'^\.incbin "([^"]+)"$', source.read_text(), re.M):
        require(inventory.get(name) == sha(name), 'Original incbin binding: ' + name)
        pins[name] = sha(name)


def run_command(argv, output, label, pins, records):
    verify(pins)
    before = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()
    env = dict(os.environ, PATH='/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
    for key in ('GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH',
                'CPLUS_INCLUDE_PATH', 'LD_PRELOAD', 'DEPENDENCIES_OUTPUT', 'SUNPRO_DEPENDENCIES'):
        env.pop(key, None)
    log = output / (label + '.log')
    with log.open('x') as stream:
        done = subprocess.run(argv, cwd=output, env=env, stdout=stream, stderr=subprocess.STDOUT,
                              timeout=120, check=False)
    records.append(dict(argv=argv, cwd=str(output), timeout_seconds=120, exit_code=done.returncode,
                        log=str(log), verified_input_map_sha256=before))
    save(output / 'commands.json', records)
    require(done.returncode == 0, 'GNU command failed: ' + label)
    verify(pins)
    return log


def snapshots(output):
    pins, versions = {}, {}
    for side, version in VERSIONS.items():
        tree = output / side / 'source'
        names = git('ls-tree', '-r', '--name-only', version, '--', QDIR).decode().splitlines()
        names = [n for n in names if n.endswith(('.c', '.h'))] + VFILES
        rows = {}
        for name in names:
            data = blob(version, name)
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            rows[name] = sha(path)
            pins[str(path)] = sha(path)
            if side == 'candidate':
                require((ROOT / name).read_bytes() == data, 'Candidate not current committed bytes: ' + name)
                pins[str(ROOT / name)] = sha(ROOT / name)
        main = tree / 'main.c'
        main.write_bytes((BASE / 'attention_threeway_untimed.c').read_bytes())
        pins[str(main)] = sha(main)
        versions[side] = dict(commit=version, tree=str(tree), files=rows, main=str(main), main_sha256=sha(main))
    aa, bb = versions['baseline']['files'], versions['candidate']['files']
    require(set(bb) - set(aa) == {NEW} and not set(aa) - set(bb) and
            {n for n in aa if aa[n] != bb[n]} == CHANGED, 'Unexpected software delta')
    return versions, pins


def prepare(output):
    output = output.absolute()
    require(output == output.resolve() and output.is_relative_to(HERE / 'out') and not output.exists(),
            'Use a fresh owned prepare/out directory')
    output.mkdir(parents=True)
    try:
        versions, pins = snapshots(output)
        require(sha(CONSUMER) == CONSUMER_SHA, 'Historical consumer changed')
        consumer = load('field_pair_original_consumer', CONSUMER)
        Elf = load('field_pair_elf_reader', ELF_READER).Elf
        report, oldpins = historical(consumer, Path(versions['baseline']['tree']))
        pins.update(oldpins)
        records = json.loads((BASE / 'commands.json').read_text())
        links = [r['argv'] for r in records if r['label'] == 'link']
        require(len(links) == 1, 'Ambiguous link recipe')
        link = links[0]
        oldobjects = [Path(x) for x in link if x.endswith('.o')]
        require(len(oldobjects) == 17 and len(set(oldobjects)) == 17 and
                {str(p): sha(p) for p in oldobjects if p != BASE / 'main.o'} ==
                report['original_16_object_identity_map'], 'Original objects differ')
        cc_main, _ = compile_record(BASE / 'main.o')
        require('-ffp-contract=fast' in cc_main and '-fno-fast-math' in cc_main and
                '-fno-builtin' in cc_main and '-mno-relax' in cc_main and '-Werror' in cc_main,
                'Changed main compile policy')
        tools = [Path(cc_main[0]), Path(cc_main[0]).with_name('riscv64-unknown-elf-objdump')]
        # Historical main inventory already pins GCC subtools, libc, libm and libgcc.
        require(all(str(t) in oldpins for t in tools), 'Tools absent from historical inventory')
        for module in tuple(sys.modules.values()):
            p = getattr(module, '__file__', None)
            if p and Path(p).is_file() and Path(p).resolve().is_relative_to(ROOT):
                pins[str(Path(p).resolve())] = sha(p)
        for p in [*HERE.glob('*.py'), HERE / 'README.md', HERE / '.gitignore', Path(sys.executable).resolve(),
                  HERE.parent / 'PLAN.md', Path('/usr/bin/git')]:
            pins[str(p)] = sha(p)
        soc = json.loads((consumer.SOC_BUILD / 'result.json').read_text())
        require(sha(consumer.SOC_BUILD / 'result.json') == consumer.SOC_SHA, 'Canonical image receipt drift')
        image = {str(p): sha(p) for p in consumer.s.image_files(Path(soc['simv']))}
        verify(image)
        pins[str(consumer.SOC_BUILD / 'result.json')] = consumer.SOC_SHA
        inventory = json.loads((BASE / 'input-pins-before.json').read_text())
        objects = dict(baseline=[], candidate=[])
        proofs, commands = [], []
        for index, obj in enumerate(oldobjects):
            cc, command_path = compile_record(obj)
            pins[str(command_path)] = sha(command_path)
            source = Path(cc[cc.index('-c') + 1])
            rebuilt = obj == BASE / 'main.o' or source.name in ('runtime.c', 'runtime_strided.c')
            local_inventory = dict(inventory)
            source_map = obj.parent / 'source-pins.json'
            if source_map.exists():
                pins[str(source_map)] = sha(source_map)
                local_inventory.update(json.loads(source_map.read_text()))
            if source.name in GENERATED:
                generated_inputs(source, obj, local_inventory, pins)
            proof = dict(original_object=str(obj), original_sha256=sha(obj), original_source=str(source),
                         rebuilt=rebuilt, sides={})
            for side in VERSIONS:
                tree = Path(versions[side]['tree'])
                newobj = output / side / (str(index) + '.o') if rebuilt else obj
                argv = list(cc)
                if rebuilt:
                    private_source = tree / 'main.c' if obj == BASE / 'main.o' else tree / source.relative_to(ROOT)
                    argv[argv.index('-c') + 1] = str(private_source)
                    argv[argv.index('-o') + 1] = str(newobj)
                    argv.insert(1, '-I' + str(tree))
                # Unchanged reused objects are scanned too, not trusted just by basename.
                log = run_command(deps_command(argv), output, f'{side}-{index}-deps', pins, commands)
                deps = parse_deps(log.read_text())
                if rebuilt:
                    for p in deps:
                        check_dependency(p, tree, local_inventory, pins)
                else:
                    for p in deps:
                        require(not (p.is_relative_to(ROOT) and p.relative_to(ROOT).as_posix() in CHANGED | {NEW}),
                                'Affected object would be reused: ' + str(obj))
                        require(local_inventory.get(str(p)) == sha(p), 'Reused object dependency drift: ' + str(p))
                        pins[str(p)] = sha(p)
                depspins = {str(p): sha(p) for p in deps}
                if rebuilt:
                    run_command(argv, output, f'{side}-{index}-compile', pins, commands)
                proof['sides'][side] = dict(object=str(newobj), object_sha256=sha(newobj),
                                           compile_argv=argv, dependencies=depspins)
                objects[side].append(newobj)
            proofs.append(proof)
        require(sum(p['rebuilt'] for p in proofs) == 3, 'Unexpected rebuild scope')
        mainproof = next(p for p in proofs if p['original_object'] == str(BASE / 'main.o'))
        for side in VERSIONS:
            depnames = mainproof['sides'][side]['dependencies']
            tree = Path(versions[side]['tree'])
            require(all(str(tree / QDIR / n) in depnames for n in
                        ('ggml_decode.h', 'q8_0_value.h', 'online.h', 'selection.h')),
                    'Missing mapping/admission/V decoder rebuild')
            require((str(tree / NEW) in depnames) == (side == 'candidate'), 'Wrong field-copy header admission')
        save(output / 'dependencies.json', proofs)
        programs = {}
        for side in VERSIONS:
            directory = output / side
            ld = directory / 'link.ld'
            ld.write_text(layout.script((BASE / 'link.ld').read_text()))
            pins[str(ld)] = sha(ld)
            elf = directory / 'attention.elf'
            replace = {str(a): str(b) for a, b in zip(oldobjects, objects[side])}
            argv = [replace.get(x, x) for x in link]
            argv[argv.index('-o') + 1] = str(elf)
            argv[argv.index('-T') + 1] = str(ld)
            argv = ['-Wl,-Map=' + str(directory / 'link.map') if x.startswith('-Wl,-Map=') else x for x in argv]
            run_command(argv, output, side + '-link', pins, commands)
            disasm = run_command([str(tools[1]), '-d', str(elf)], output, side + '-disassembly', pins, commands)
            parsed = Elf(elf)
            main = parsed.symbols['main']
            instructions = []
            for line in disasm.read_text().splitlines():
                match = re.fullmatch(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)', line)
                if match and main['address'] <= int(match[1], 16) < main['address'] + main['size']:
                    instructions.append(dict(pc=int(match[1], 16), encoding=match[2], text=match[3]))
            cycles = [i for i in instructions if re.match(r'rdcycle\s', i['text'])]
            require(len(cycles) == 2 and all((int(i['encoding'], 16) & 0xfffff07f) == 0xc0002073 for i in cycles),
                    'Changed timer sites')
            require('strided_value_decode' in parsed.symbols and any('fence' in i['text'] for i in instructions),
                    'Missing decoder/drain')
            cfg = layout.timed_cfg(instructions, cycles)
            save(directory / 'timed-cfg.json', dict(cfg=cfg, main_instructions=instructions))
            receipt = dict(state='GNU_BUILT_NOT_EXECUTED', side=side, commit=VERSIONS[side], elf=str(elf),
                           elf_sha256=sha(elf), workload=WORKLOAD, sources=versions[side], rdcycle_sites=cycles, timed_cfg=cfg,
                           rebuilt_objects=[p['sides'][side]['object'] for p in proofs if p['rebuilt']],
                           reused_objects={str(p): sha(p) for p in oldobjects if p in objects[side]})
            save(directory / 'build.json', receipt)
            programs[side] = dict(elf=str(elf), elf_sha256=sha(elf), build_receipt=str(directory / 'build.json'),
                                  build_receipt_sha256=sha(directory / 'build.json'))
        mapping = layout.compare(Elf(Path(programs['baseline']['elf'])), Elf(Path(programs['candidate']['elf'])),
                                 Elf(BASE / 'threeway_attention.elf'),
                                 json.loads((BASE / 'layout-review.json').read_text()))
        save(output / 'layout.json', mapping)
        save(output / 'versions.json', versions)
        pins.update(image)
        verify(pins)
        save(output / 'input-pins-before.json', pins)
        verify(pins)
        save(output / 'input-pins-after.json', pins)
        artifacts = {str(p): sha(p) for p in output.rglob('*') if p.is_file() and p.name != 'worker.log'}
        result = dict(schema='quant_field_copy_pair_prepare_v1', state='GNU_PAIR_STATIC_PASS_NOT_EXECUTED',
                      programs=programs, input_pins=pins, artifacts=artifacts, workload=WORKLOAD,
                      versions=VERSIONS, layout=mapping, image_pins=image, canonical_build=str(consumer.SOC_BUILD),
                      canonical_build_sha256=consumer.SOC_SHA, post_pins_match=True,
                      historical_header_translation_only=sorted(CHANGED), rebuilt_object_count=3,
                      reused_object_count=14, numerical_execution_checked=False, simulations_launched=0,
                      performance_claim=False, historical_timing_reused=False)
        save(output / 'build.json', result)
        return result
    except BaseException as exc:
        save(output / 'build.json', dict(state='FAIL', error=repr(exc), simulations_launched=0))
        raise


def checked_pair(receipt):
    """Offline worker interface, with raw build/ELF/dependency reconstruction."""
    receipt = Path(receipt).resolve(strict=True)
    result = json.loads(receipt.read_text())
    require(result['schema'] == 'quant_field_copy_pair_prepare_v1' and
            result['state'] == 'GNU_PAIR_STATIC_PASS_NOT_EXECUTED' and result['workload'] == WORKLOAD and
            result['versions'] == VERSIONS and result['simulations_launched'] == 0 and
            result['post_pins_match'] is True and result['performance_claim'] is False,
            'Wrong prepared receipt')
    pins = dict(result['input_pins'])
    for path, digest in result['artifacts'].items():
        require(path not in pins or pins[path] == digest, 'Conflicting artifact pin')
        pins[path] = digest
    verify(pins)
    require(json.loads((receipt.parent / 'input-pins-before.json').read_text()) ==
            json.loads((receipt.parent / 'input-pins-after.json').read_text()) == result['input_pins'],
            'Input maps differ')
    pins[str(receipt)] = sha(receipt)
    Elf = load('field_pair_checked_elf_reader', ELF_READER).Elf
    proofs = json.loads((receipt.parent / 'dependencies.json').read_text())
    require(len(proofs) == 17 and sum(p['rebuilt'] for p in proofs) == 3, 'Rebuild inventory')
    versions = json.loads((receipt.parent / 'versions.json').read_text())
    commands = json.loads((receipt.parent / 'commands.json').read_text())
    require(len(commands) == 44 and all(r['exit_code'] == 0 for r in commands), 'Incomplete GNU command ledger')
    programs, objects = {}, dict(baseline=[], candidate=[])
    for side, revision in VERSIONS.items():
        tree = Path(versions[side]['tree'])
        require(versions[side]['commit'] == revision, 'Version identity')
        for rel, expected in versions[side]['files'].items():
            require(hashlib.sha256(blob(revision, rel)).hexdigest() == expected == sha(tree / rel),
                    'Source is not pristine revision')
        require((tree / 'main.c').read_bytes() == (BASE / 'attention_threeway_untimed.c').read_bytes(),
                'Six-call source changed')
        for proof in proofs:
            row = proof['sides'][side]
            require(sha(row['object']) == row['object_sha256'], 'Object mismatch')
            verify(row['dependencies'])
            if proof['rebuilt']:
                original_argv, _ = compile_record(Path(proof['original_object']))
                original_source = Path(original_argv[original_argv.index('-c') + 1])
                private_source = tree / 'main.c' if Path(proof['original_object']) == BASE / 'main.o' else tree / original_source.relative_to(ROOT)
                expected = list(original_argv)
                expected[expected.index('-c') + 1] = str(private_source)
                expected[expected.index('-o') + 1] = row['object']
                expected.insert(1, '-I' + str(tree))
                require(row['compile_argv'] == expected, 'Original compile/FP policy changed')
                require(sum(c['argv'] == row['compile_argv'] for c in commands) == 1 and
                        Path(row['object']).is_relative_to(receipt.parent / side), 'Missing actual rebuild')
                require(all(not Path(p).is_relative_to(ROOT / QDIR) for p in row['dependencies']),
                        'Live quantized header in rebuild')
            else:
                require(row['object'] == proof['original_object'] and row['object_sha256'] == proof['original_sha256'] and
                        all(not (Path(p).is_relative_to(ROOT) and Path(p).relative_to(ROOT).as_posix() in CHANGED | {NEW})
                            for p in row['dependencies']), 'Affected reused object')
            objects[side].append(Path(row['object']))
        program = result['programs'][side]
        require(sha(program['elf']) == program['elf_sha256'] and
                sha(program['build_receipt']) == program['build_receipt_sha256'], 'Program receipt binding')
        sub = json.loads(Path(program['build_receipt']).read_text())
        require(sub['state'] == 'GNU_BUILT_NOT_EXECUTED' and sub['workload'] == WORKLOAD and sub['commit'] == revision,
                'Program scope mismatch')
        gold = ROOT / ('verification/out/akv-quantkv-host-capture-20261024-01/'
                       'capture-k-q4_0-v-q8_0/decode/block/kqv_out-0.bin')
        require(str(gold) in pins and sha(gold) == pins[str(gold)], 'Golden pin missing')
        programs[side] = dict(program, revision=revision, fresh_build=True, golden=str(gold), golden_sha256=sha(gold))
    mapping = layout.compare(Elf(Path(programs['baseline']['elf'])), Elf(Path(programs['candidate']['elf'])),
                             Elf(BASE / 'threeway_attention.elf'),
                             json.loads((BASE / 'layout-review.json').read_text()))
    require(mapping == result['layout'] == json.loads((receipt.parent / 'layout.json').read_text()), 'Layout proof differs')
    for side in VERSIONS:
        ld = receipt.parent / side / 'link.ld'
        require(ld.read_text() == layout.script((BASE / 'link.ld').read_text()), 'Link script drift')
        sub = json.loads(Path(programs[side]['build_receipt']).read_text())
        timed = json.loads((receipt.parent / side / 'timed-cfg.json').read_text())
        require(layout.timed_cfg(timed['main_instructions'], sub['rdcycle_sites']) == timed['cfg'] == sub['timed_cfg'],
                'Timed CFG differs')
    normalized = dict(WORKLOAD, schema='quantkv_field_copy_pair_prepared_v1',
        state='FIELD_COPY_PAIR_STATIC_PASS_NOT_EXECUTED', execution='NOT_RUN', revisions=VERSIONS,
        programs=programs, matching_compiler_flags=True, matching_fp_policy=True, matching_input_payloads=True,
        affected_objects_rebuilt=True, layout_reviewed=True, post_pins_match=True,
        simulations_launched=0, performance_measured=False)
    verify(pins)
    return normalized, pins


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    print(prepare(parser.parse_args().output)['state'])
