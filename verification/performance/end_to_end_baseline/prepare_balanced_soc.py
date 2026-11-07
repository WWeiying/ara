#!/usr/bin/env python3
"""Gated, isolated full-processor build; no production RTL or old image edits."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from balanced_engine_source import engine, vlsu, EXPERIMENT_DEFINE
from prepare_wide_soc import HERE, ROOT, RUNS, WARNING, emit

PREPARED = RUNS / 'e2e_physical_wide_soc_inputs_20261106_01'
PREPARED_SHA = 'dad1e64aaa814f3fa4c5cf2d2bf3bb1ea105ca12aa1448ec3e8f0ae310942e29'
REFERENCE = RUNS / 'e2e_physical_wide_soc256_20261106_01'
REFERENCE_SHA = 'f406f967a87c2c198656fe4aa933d34330aaf40fd230adfa331f70347f5c93bd'
COMPONENT = RUNS / 'e2e_balanced_compute_20261106_01'
COMPONENT_SHA = 'a7ccf4376c736101c76659330999b633eed9985c943bc5cd5516bbc465a88b0d'
CLONES = tuple(name + '.sv' for name in (
    'qbs_dot_array_balanced', 'qbs_profile_decoder_balanced',
    'qbs_profile_engine_int_balanced', 'qbs_fp_accumulator_balanced',
    'qbs_compute_engine_balanced', 'qbs_mixed_scale', 'qbs_fp16_f32_scale'))
ENGINE_REL = 'hardware/src/vlsu/qbs/qbs_engine.sv'
VLSU_REL = 'hardware/src/vlsu/vlsu.sv'
ADDITION_REL = 'hardware/src/vlsu/qbs/experimental/balanced_soc'
STATES = {
    'controller': 'BALANCED_COMPLETE_CONTROLLER_ATOMIC_CONTEXT_AND_DISABLED_PASS',
    'seed': 'BALANCED_NONZERO_SEED_CONTINUATION_CANCEL_RECOVERY_FUNCTIONAL_PASS',
}


def graph(text, old, new, enabled):
    require(type(enabled) is int and enabled in (0, 1), 'Explicit binary feature selection')
    require(old.is_absolute() and new.is_absolute() and old != new, 'Independent absolute snapshot roots')
    lines = text.splitlines()
    require(not any(EXPERIMENT_DEFINE in line for line in lines), 'Feature already present')
    for flag in ('+define+ARA_QBS_WIDE_MATRIX_DOT=1',
                 '+define+ARA_EXPERIMENT_AXI_DATA_WIDTH=256',
                 '+define+ARA_QBS_WIDE_WEIGHT_INGRESS=1'):
        require(lines.count(flag) == 1, 'Wrong accepted physical platform: ' + flag)
    anchor = str(old / VLSU_REL)
    require(lines.count(anchor) == 1, 'Unique VLSU source required')
    additions = [str(new / ADDITION_REL / name) for name in (*CLONES, 'qbs_engine_balanced.sv')]
    result = ['+define+' + EXPERIMENT_DEFINE + '=' + str(enabled)]
    for line in lines:
        if line.startswith('+define+') or not line:
            result.append(line)
            continue
        prefix = '+incdir+' if line.startswith('+incdir+') else ''
        path = Path(line[len(prefix):])
        require(path.is_absolute() and path.is_relative_to(old), 'External source graph input: ' + line)
        if line == anchor:
            result.extend(additions)
        result.append(prefix + str(new / path.relative_to(old)))
    restored = [line.replace(str(new) + '/', str(old) + '/') for line in result[1:]
                if line not in additions]
    require(restored == lines, 'Unexpected source graph edit')
    return '\n'.join(result) + '\n'


def diagnostic_check(text, argv, original, old, new):
    require(not re.search(r'(?m)^Error-|\bFatal:|Assertion[^\n]*failed', text), 'Compiler error')
    require('CPU time:' in text and 'to compile' in text, 'Missing compiler completion')
    header = []
    for line in text.splitlines(keepends=True):
        header.append(line)
        if not line.endswith('\\\n'):
            break
    require(''.join(header).startswith('Command: ') and
            shlex.split(''.join(header)[len('Command: '):].replace('\\\n', '')) == ['vcs', *argv[1:]],
            'Actual compiler command differs')
    expected = re.findall(WARNING, original)
    actual = re.findall(WARNING, text)
    require(expected and Counter(actual) == Counter(
        block.replace(str(old) + '/', str(new) + '/') for block in expected),
        'New, changed or missing diagnostic; preserve and review compile output')
    return dict(exact_original_diagnostics_retained=True, known_diagnostic_count=len(expected))


def receipt(directory, expected, state, pins):
    require(directory == directory.resolve() and directory.is_relative_to(RUNS), 'Verification evidence root')
    path = directory / 'result.json'
    require(digest(path) == expected, 'Receipt identity: ' + str(path))
    value = json.loads(path.read_text())
    require(value['state'] == state and value.get('post_pins_match'), 'Unaccepted prerequisite: ' + str(path))
    inventory = directory / 'source-pins.json'
    require(digest(inventory) == value['source_pins_sha256'], 'Prerequisite source inventory')
    additions = {**json.loads(inventory.read_text()), **value.get('artifacts', {}),
                 str(path): expected, str(inventory): digest(inventory)}
    verify_pins(additions)
    for name, sha in additions.items():
        require(name not in pins or pins[name] == sha, 'Conflicting prerequisite identities')
        pins[name] = sha
    return value


def seed_sources(worker, pins, expected):
    """Bind candidate modules to the executed seed compile, not inherited copies."""
    commands_path = worker / 'commands.json'
    planned_path = worker.parent / 'compile-command.json'
    for path in (commands_path, planned_path):
        require(pins.get(str(path)) == digest(path), 'Unbound seed compiler record: ' + str(path))
    commands = json.loads(commands_path.read_text())
    compiled = [row for row in commands if row['label'] == 'compile']
    planned = json.loads(planned_path.read_text())
    require(len(compiled) == 1 and compiled[0]['returncode'] == 0 and
            compiled[0]['argv'] == planned['argv'] and
            compiled[0]['cwd'] == planned['cwd'] == str(worker), 'Seed executed compiler recipe differs')
    argv = compiled[0]['argv']
    sources = [Path(arg) for arg in argv if arg.endswith('.sv')]
    require(set(expected) == set(CLONES), 'Complete candidate module inventory required')
    result = {}
    for name, sha in expected.items():
        local = worker.parent / 'source' / name
        require([path for path in sources if path.name == name] == [local] and
                local == local.resolve(strict=True) and pins.get(str(local)) == sha and digest(local) == sha,
                'Seed did not compile the exact bound local module: ' + name)
        result[name] = dict(path=str(local), sha256=sha)
    return result


def prepare(output, controller, controller_sha, seed, seed_sha):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification output')
    out.mkdir(parents=True, exist_ok=False)
    pins = {}
    result = dict(state='FAIL', synthesis_run=False, simulations_launched=0, compiles_launched=0,
                  production_source_changed=False, performance_measured=False)

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        sha = digest(path)
        require(expected is None or sha == expected, 'Input identity: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == sha, 'Input conflict')
        pins[str(path)] = sha

    try:
        ctl = receipt(controller, controller_sha, STATES['controller'], pins)
        require(ctl['default_off_exact'] and ctl['original_and_candidate_read_work_equal'],
                'Complete controller must retain original/off behavior and traffic')
        receipt(seed, seed_sha, STATES['seed'], pins)
        controller_pins = json.loads((controller / 'source-pins.json').read_text())
        receipt(COMPONENT, COMPONENT_SHA,
                'BALANCED_COMPUTE_ORDER_FLAGS_WORK_DISABLED_AND_FAULTS_PASS', pins)
        reference = receipt(REFERENCE, REFERENCE_SHA, 'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED', pins)
        pin(PREPARED / 'result.json', PREPARED_SHA)
        prior = json.loads((PREPARED / 'result.json').read_text())
        pin(PREPARED / 'source-pins.json', prior['source_pins_sha256'])
        identities = json.loads((PREPARED / 'source-pins.json').read_text())
        verify_pins(identities)
        old = Path(prior['source_root'])
        require(old == PREPARED / 'source' and reference['source_root'] == str(old) and
                reference['prepared_sha256'] == PREPARED_SHA and reference['width'] == 256,
                'Accepted physical platform mismatch')
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):
                pin(path)
        pin(HERE / 'test_prepare_balanced_soc.py')
        pin(Path(__file__))
        pin(sys.executable)
        tree = out / 'source'
        selected = []
        for source in sorted(old.rglob('*')):
            if not source.is_file():
                continue
            require(not source.is_symlink() and str(source) in identities, 'Unpinned snapshot input')
            pin(source, identities[str(source)])
            target = tree / source.relative_to(old)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.relative_to(old).as_posix() == VLSU_REL:
                changed, transform = vlsu(source.read_text())
                target.write_text(changed)
            else:
                shutil.copyfile(source, target)
            pin(target)
            selected.append(dict(relative=target.relative_to(tree).as_posix(), original_sha256=digest(source),
                                 generated_sha256=digest(target)))
        require(len(selected) == prior['selected_count'] + 1, 'Incomplete snapshot including memory probe')
        addition = tree / ADDITION_REL
        addition.mkdir(parents=True)
        component_pins = json.loads((COMPONENT / 'source-pins.json').read_text())
        seed_binding = seed_sources(seed, pins,
            {name: component_pins[str(COMPONENT / 'source' / name)] for name in CLONES})
        for name in CLONES:
            source = COMPONENT / 'source' / name
            pin(source, component_pins[str(source)])
            require(digest(source) == controller_pins.get(str(controller / 'tree/balanced' / name)) and
                    digest(source) == seed_binding[name]['sha256'],
                    'Controller and seed gates must cover identical candidate modules: ' + name)
            target = addition / name
            shutil.copyfile(source, target)
            pin(target)
        text, ctl_transform = engine((tree / ENGINE_REL).read_text())
        target = addition / 'qbs_engine_balanced.sv'
        target.write_text(text)
        pin(target)
        require(digest(target) == controller_pins.get(str(controller / 'tree/balanced/qbs_engine_balanced.sv')),
                'Generated controller differs from full-controller acceptance')
        filelist = PREPARED / 'sources256.f'
        pin(filelist, identities[str(filelist)])
        lists = {}
        for mode in (0, 1):
            target = out / f'sources{mode}.f'
            target.write_text(graph(filelist.read_text(), old, tree, mode))
            pin(target)
            lists[str(mode)] = str(target)
        recipe = [arg.replace(str(old) + '/', str(tree) + '/') for arg in prior['recipe']]
        require(recipe.count('{filelist}') == 1 and recipe.count('-f') == 1 and
                recipe[-2:] == ['-l', 'comp.vcs.log'], 'Inherited compiler recipe')
        for name, value in (('selection.json', selected),
                            ('transforms.json', dict(vlsu=transform, controller=ctl_transform)),
                            ('seed-compiled-sources.json', seed_binding)):
            emit(out / name, value)
            pin(out / name)
        verify_pins(pins)
        result.update(state='BALANCED_SOC_INPUTS_PREPARED', post_pins_match=True, source_root=str(tree),
                      recipe=recipe, filelists=lists, selected_count=len(selected), width=256,
                      nr_lanes=4, vlen=1024, l2_bytes=16777216, modes=[0, 1],
                      prerequisites=dict(controller_sha256=controller_sha, seed_sha256=seed_sha,
                                         component_sha256=COMPONENT_SHA, reference_sha256=REFERENCE_SHA),
                      limits=['Isolated build inputs, not a new SoC or software acceptance',
                              'Actual generic 16 MiB RAM, not an external DDR bandwidth claim',
                              'Balanced M4 QBS/AKV/RVV handoff and actual SDK timing remain required'])
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        emit(out / 'source-pins.json', pins)
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        emit(out / 'result.json', result)


def compile_soc(prepared, expected, mode, output):
    pins = {}
    info = receipt(prepared, expected, 'BALANCED_SOC_INPUTS_PREPARED', pins)
    require(type(mode) is int and mode in info['modes'], 'Unknown mode')
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification compile output')
    out.mkdir(parents=True, exist_ok=False)
    sim = out / 'sim'
    sim.mkdir()
    (sim / 'incremental_db').mkdir()
    argv = [arg.replace('{filelist}', info['filelists'][str(mode)]) for arg in info['recipe']]
    result = dict(state='COMPILE', child_pid=None, mode=mode, width=256, simulations_launched=0,
                  performance_measured=False, synthesis_run=False, production_source_changed=False,
                  prepared=str(prepared), prepared_sha256=expected, source_root=info['source_root'])

    def save():
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')

    try:
        emit(out / 'source-pins.json', pins)
        emit(out / 'compile-command.json', dict(argv=argv, cwd=str(sim), timeout_seconds=7200))
        env = {k: v for k, v in os.environ.items() if k not in (
            'LD_PRELOAD', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'COMPILER_PATH',
            'GCC_EXEC_PREFIX', 'LIBRARY_PATH')}
        verify_pins(pins)
        with (out / 'compile.stdout.log').open('xb') as stream:
            child = subprocess.Popen(argv, cwd=sim, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            result['child_pid'] = child.pid
            save()
            try:
                code = child.wait(timeout=7200)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
        result['child_pid'] = None
        require(code == 0, 'Compiler failed; original log retained')
        lint = diagnostic_check((sim / 'comp.vcs.log').read_text(), argv,
            (REFERENCE / 'sim/comp.vcs.log').read_text(),
            Path(json.loads((REFERENCE / 'result.json').read_text())['source_root']), Path(info['source_root']))
        images = [sim / 'simv', *sorted((sim / 'simv.daidir').rglob('*.so'))]
        require(len(images) > 1 and images[0].is_file(), 'Incomplete simulator image')
        config = dict(json.loads((REFERENCE / 'result.json').read_text())['config'],
                      qbs_balanced_matrix_dot=str(mode))
        (sim / 'simulator.conf').write_text(''.join(k + '=' + v + '\n' for k, v in sorted(config.items())))
        verify_pins(pins)
        result.update(state='BALANCED_SOC_BUILT_NOT_EXECUTED', post_pins_match=True,
                      simv=str(images[0]), image_pins={str(p): digest(p) for p in images},
                      config=config, lint=lint)
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        save()
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in (
            out / 'compile-command.json', out / 'source-pins.json', out / 'compile.stdout.log',
            sim / 'comp.vcs.log', sim / 'simulator.conf') if p.is_file()}
        emit(out / 'result.json', result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare')
    for name in ('controller', 'seed'):
        a.add_argument('--' + name, type=Path, required=True)
        a.add_argument('--' + name + '-sha', required=True)
    a.add_argument('--output', type=Path, required=True)
    a = sub.add_parser('compile')
    a.add_argument('--prepared', type=Path, required=True)
    a.add_argument('--prepared-sha', required=True)
    a.add_argument('--mode', type=int, choices=(0, 1), required=True)
    a.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.action == 'prepare':
        prepare(args.output, args.controller, args.controller_sha, args.seed, args.seed_sha)
    else:
        compile_soc(args.prepared, args.prepared_sha, args.mode, args.output)
