#!/usr/bin/env python3
"""Reviewed software builds and identity checks for the experimental PV SoC."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


accepted = load(HERE.parents[1]/'akv_pair_eval/integration/check.py', 'pv_soc_accepted')
contract = accepted.contract
require, sha = contract.require, contract.sha
BASE = contract.OUT/'akv_pair_integration_build_20261107_01'
BASE_SHA = 'd4ff1a1d1d250ccba7b24dd86d5816004158df78d80652d7133286ae7f42c042'
SOC_HELPER = HERE.parent/'soc_build/build.py'
SOC_HELPER_SHA = 'd40f3dff74a411d75ee189338008b5eb91176d00210563d79cb208e56044afd4'
ANCHORS = {
    HERE.parent/'pv_prepare/prepare.S': '8d039dd90da0b00497429be90483d0ed9f3576c1400f458889e9e8cd380968be',
    HERE.parent/'rotation/pv_rotation.S': '42cae9574432604db17e5ef9a30f7b074dbd009c3cc25594e741707a564c863f',
    HERE.parent/'rotation/main.c': '5187bd4757bf51a6779b2b320a6c6efa10efcb5df52c6344cf6072b4725d90ce',
    SOC_HELPER: SOC_HELPER_SHA,
}
OWN = ('experiment.py', 'test_experiment.py', 'README.md', 'main.c', 'pv.S',
       'smoke.c', 'test_wrapper.py', 'check_resident.py', 'test_check_resident.py')
SCHEMA = 'resident-pv-soc-eval-build-v1'
KINDS = ('smoke', 'abba')
SYMBOL = 'akv_experimental_pv_f16_pair'
OBJECTS = ('main', 'pv', 'prepare', 'strong_control')
STRONG_FLAGS = (
    '-D__wrap_akv_experimental_pv_f16_pair=resident_pv_rotation_body',
    '-Dresident_pv_rotation_selected=resident_pv_rotation_always',
)
RUN_PLUSARGS = ['+RESIDENT_PV_PERF', '+RESIDENT_PV_WATCHDOG']
LEGACY_CLASSIFICATION = 'Legacy uvm_coverage akv_column includes f7=2; not PV semantic acceptance'


def merge(pins, extra):
    for path, digest in extra.items():
        path = str(path)
        require(path not in pins or pins[path] == digest, 'Conflicting input pin: '+path)
        pins[path] = digest


def soc_contract():
    require(sha(SOC_HELPER) == SOC_HELPER_SHA, 'Sealed SoC build helper drift')
    return load(SOC_HELPER, 'pv_soc_build_contract')


def checked_soc(directory):
    """Accept only the new successful build-only receipt, never an old gate."""
    b = soc_contract()
    out = b.output_path(Path(directory))
    m = json.loads((out/'build.json').read_text())
    require(m.get('state') == 'RESIDENT_PV_SOC_BUILT_NOT_EXECUTED' and
            m.get('execution') == 'NOT_RUN' and m.get('post_pins_match') is True and
            m.get('post_image_match') is True, 'No completed resident PV SoC build')
    require(all(m.get(k) is False for k in ('performance_measured', 'soc_acceptance',
                'fpga_acceptance', 'capability_advertised')) and
            m.get('experimental_direct_wrapper_only') is True and
            m.get('dependencies_from_accepted_snapshot') is True and
            m.get('baseline') == str(b.ADMITTED) and m.get('configuration') == b.CONFIG and
            m.get('image_contract') == b.IMAGE_CONTRACT, 'Wrong experimental image policy')
    pinfile = out/'source-pins.json'
    require(sha(pinfile) == m['source_pins_sha256'], 'SoC pin inventory drift')
    pins = json.loads(pinfile.read_text())
    b.verify(pins)
    _, command, baseline_graph, extras, mandatory = b.baseline()
    require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing admitted predecessor pin')
    source = out/'source'
    mapped_extras = [source/p.relative_to(b.FROZEN) if p.is_relative_to(b.FROZEN)
                     else out/'inputs'/p.name for p in extras]
    selection = dict(schema_version=1, configuration=b.CONFIG, image_contract=b.IMAGE_CONTRACT,
        baseline=str(b.BASE), admitted=str(b.ADMITTED), parent_review_required=True,
        timeout_seconds=7200, execution='NOT_RUN', snapshot_root=str(source),
        extras=list(map(str, mapped_extras)))
    require(json.loads((out/'selection.json').read_text()) == selection, 'SoC selection drift')
    text = (out/'sources.f').read_text()
    require(text == b.rewrite_filelist((b.BASE/'sources.f').read_text(), b.FROZEN, source) and
            json.loads((out/'command.json').read_text()) == b.map_command(command, out),
            'Not the reviewed frozen filelist/compile recipe')
    _, _, defines = b.entries(text, source)
    b.configuration(defines, b.map_command(command, out), True)
    graph = json.loads((out/'closure.json').read_text())
    b.verify_closure(graph, text, source, mapped_extras)
    require(all(pins.get(p) == h for p, h in graph['files'].items()), 'Unpinned compiler closure')
    for name, digest in baseline_graph['files'].items():
        path = Path(name)
        dest = source/path.relative_to(b.FROZEN) if path.is_relative_to(b.FROZEN) else out/'inputs'/path.name
        if path.is_relative_to(b.FROZEN) and str(path.relative_to(b.FROZEN)) in b.OVERLAY:
            continue
        require(pins.get(str(dest)) == digest, 'Frozen dependency/testbench replacement')
    overlay = []
    for relative in (*b.OVERLAY, *b.NEW_RTL):
        original, dest = b.ROOT/relative, source/relative
        require(pins.get(str(original)) == sha(dest) and pins.get(str(dest)) == sha(dest),
                'Unpinned explicit RTL overlay')
        overlay.append(dict(path=relative, source=str(original), sha256=sha(dest),
            baseline_sha256=baseline_graph['files'].get(str(b.FROZEN/relative)),
            kind='replacement' if relative in b.OVERLAY else 'new'))
    require(json.loads((out/'overlay.json').read_text()) == dict(overlay=overlay,
        bender_audit_only=True, live_inputs_excluded=['hardware/tb', 'hardware/deps', 'software', 'apps'],
        baseline_testbench_sha256=baseline_graph['files'][str(b.FROZEN/'hardware/tb/ara_tb.sv')]),
        'Wrong 13+6 overlay inventory')
    b.overlay_invariants(source, (out/'inputs/audit/Bender.yml').read_text())
    require(sha(out/'inputs/build.py') == SOC_HELPER_SHA, 'Different frozen SoC compiler harness')
    require(json.loads((out/'sim/vcs_source_manifest.json').read_text()) ==
            b.source_manifest(text, source, out/'sources.f', mapped_extras, pins), 'Source manifest drift')
    require((out/'sim/simulator.conf').read_text() == ''.join(f'{k}={v}\n' for k, v in b.CONFIG.items()),
            'Simulator configuration drift')
    require(json.loads((out/'prepared.json').read_text()) == dict(state='PREPARED_NOT_BUILT',
        parent_review_required=True, source_pins_sha256=sha(pinfile), overlay_files=19,
        source_files=len(graph['files']), execution='NOT_RUN', capability=0), 'Prepared receipt drift')
    simv, daidir = out/'sim/simv', out/'sim/simv.daidir'
    require(m['simv'] == str(simv) and simv.is_file() and os.access(simv, os.X_OK) and daidir.is_dir(),
            'Missing executable/full image directory')
    members = [p for p in daidir.rglob('*') if p.is_file()]
    require(members and all(not p.is_symlink() for p in [simv, *daidir.rglob('*')]), 'Incomplete/linked image')
    image = {str(p): sha(p) for p in [simv, *members]}
    require(image == m['image_pins'] == json.loads((out/'image-pins.json').read_text()), 'Image inventory drift')
    require(all((out/p).is_file() for p in ('compile.log', 'tests.log', 'sim/comp.vcs.log')) and
            m['artifacts'] == b.artifact_pins(out, pins), 'Incomplete/stale SoC artifacts')
    merge(pins, m['artifacts'])
    merge(pins, image)
    merge(pins, {str(p): sha(p) for p in (pinfile, out/'build.json', SOC_HELPER)})
    b.verify(pins)
    return m, pins


def shapes(kind):
    require(kind in KINDS, 'Unknown experiment kind')
    return [dict(dimension=128, heads=2, tokens=t) for t in (64, 64, 9)*(1 if kind == 'smoke' else 2)]


def work_expectation(kind):
    s = shapes(kind)
    return dict(shapes=s, legacy_akv_perf=100 if kind == 'smoke' else 674,
        resident_pv_perf=len(s), vector_akv_allocations=99 if kind == 'smoke' else 664,
        opcode='0485705b', opcode_allocations=len(s), candidate_fma_per_lane_per_call=2192,
        source_words_per_command=96, source_words_per_lane=24,
        result_words_per_command=64, final_acks_per_command=64,
        legacy_classification=LEGACY_CLASSIFICATION)


def check_resident_work(vector_path, log_text, kind):
    # This is a supplement only. No numerical/protocol acceptance is implied.
    checker = load(HERE/'check_resident.py', 'pv_soc_resident_work')
    return checker.check_successful_pv(vector_path, log_text, shapes(kind))


def baseline():
    require(sha(BASE/'build.json') == BASE_SHA, 'Accepted software base receipt drift')
    contract.verify({str(p): h for p, h in ANCHORS.items()})
    meta = accepted.verify_build(BASE)
    pins = json.loads((BASE/'source-pins.json').read_text())
    merge(pins, meta['artifacts'])
    merge(pins, {str(BASE/'build.json'): BASE_SHA})
    merge(pins, ANCHORS)
    merge(pins, {str(HERE/name): sha(HERE/name) for name in OWN})
    contract.verify(pins)
    return meta, pins


def recipes(output, kind):
    shapes(kind)
    output = Path(output)
    require(sha(BASE/'build.json') == BASE_SHA, 'Accepted software base drift')
    cmds = json.loads((BASE/'commands.json').read_text())
    result = []
    for obj, source, template, flags in (
        ('main', HERE/('smoke.c' if kind == 'smoke' else 'main.c'), 'compile-00_main', ()),
        ('pv', HERE/'pv.S', 'compile-14_akv_v2_attention_rvv', ()),
        ('prepare', HERE.parent/'pv_prepare/prepare.S', 'compile-14_akv_v2_attention_rvv', ()),
        ('strong_control', HERE.parent/'rotation/pv_rotation.S', 'compile-14_akv_v2_attention_rvv', STRONG_FLAGS)):
        argv = list(next(c for c in cmds if c['label'] == template)['argv'])
        for flag, value in (('-c', source), ('-o', output/(obj+'.o')), ('-MF', output/(obj+'.d'))):
            argv[argv.index(flag)+1] = str(value)
        result.append(dict(label='compile-'+obj, argv=argv+list(flags)))
    link = list(next(c for c in cmds if c['label'] == 'link')['argv'])
    link[link.index(str(BASE/'00_main.o'))] = str(output/'main.o')
    link[link.index('-Wl,-Map='+str(BASE/'link.map'))] = '-Wl,-Map='+str(output/'link.map')
    link[link.index('-o')+1] = str(output/'resident_pv.elf')
    at = link.index('-Wl,--gc-sections')
    link[at:at] = [str(output/(obj+'.o')) for obj in OBJECTS[1:]]+[
        '-Wl,--wrap='+SYMBOL, '-Wl,--undefined=akv_attention_execute_v2_native']
    result.append(dict(label='link', argv=link))
    for label in ('disassembly', 'segments'):
        argv = [str(output/'resident_pv.elf') if x == str(BASE/contract.ELF_NAME) else x
                for x in next(c for c in cmds if c['label'] == label)['argv']]
        if label == 'disassembly':
            argv[1:1] = ['-M', 'no-aliases,numeric']
        result.append(dict(label=label, argv=argv))
    return result


def environment():
    return dict(PATH='/usr/bin:/bin', HOME=os.environ.get('HOME', '/home/wangwy'),
                LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')


def dependencies(output, pins, kind):
    old, _ = contract.sealed_modules()
    require({p.name for p in output.glob('*.d')} == {n+'.d' for n in OBJECTS}, 'Missing compiler dependencies')
    for name in OBJECTS:
        paths = set(old.dependency_inputs(output/(name+'.d')))
        require(paths and all(pins.get(str(p)) == sha(p) for p in paths), 'Unreviewed/drifting compiler input')
        require(not any(p.is_relative_to(contract.ROOT/'software') or
                        p.is_relative_to(contract.ROOT/'hardware') for p in paths), 'Live SDK/RTL dependency')
        expected = recipes(output, kind)[OBJECTS.index(name)]['argv']
        require(Path(expected[expected.index('-c')+1]) in paths, 'Compiler source dependency missing')


def fields(output, kind, meta):
    b = soc_contract()
    return dict(schema=SCHEMA, kind=kind, state='BUILT_NOT_EXECUTED', target_executed=False,
        rtl_executed=False, performance_measured=False, soc_acceptance=False,
        baseline_build=str(BASE), baseline_build_sha256=BASE_SHA, sdk_new=meta['sdk_new'],
        image_contract=meta['image_contract'], shape=meta['shape'], golden=meta['golden'],
        memory_expected=meta['memory_expected'],
        elf=str(output/'resident_pv.elf'), baseline_arm='strong rotating RVV',
        candidate_arm='sealed preparation + resident PV 0x0485705b',
        objects_reused=[x for x in meta['objects'] if Path(x).name != '00_main.o'],
        objects_recompiled=[str(output/(n+'.o')) for n in OBJECTS],
        work_expectation=work_expectation(kind), required_run_plusargs=RUN_PLUSARGS,
        watchdog_lease_cycles=32768, first_execution='smoke_only', automatic_abba=False,
        soc_binding='PENDING_EXPLICIT_RUNTIME_PAIRING', required_soc_configuration=b.CONFIG,
        required_soc_state='RESIDENT_PV_SOC_BUILT_NOT_EXECUTED',
        resident_checker=dict(path=str(HERE/'check_resident.py'),
            function='check_successful_pv(vector_path, log_text, shapes)',
            numerical_checked=False, protocol_checked=False),
        run_implemented=False)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def build(output, kind, parent_reviewed=False):
    require(parent_reviewed, 'Explicit parent review required before software compilation')
    output = Path(output).resolve()
    require(output.parent == contract.OUT.resolve() and
            re.fullmatch(r'resident_pv_soc_eval_[A-Za-z0-9_-]+', output.name) and not output.exists(),
            'Fresh owned direct signoff output required')
    meta, pins = baseline()
    recipe = recipes(output, kind)
    output.mkdir()
    commands, env = [], environment()
    for command in recipe:
        contract.verify(pins)
        proc = subprocess.run(command['argv'], cwd=output, env=env, text=True,
                              capture_output=True, timeout=180)
        log = output/(command['label']+'.log')
        log.write_text(proc.stdout+proc.stderr)
        commands.append(dict(command, returncode=proc.returncode, cwd=str(output), env=env, log=str(log)))
        # Keep failed command evidence; a failed build is never reusable.
        (output/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        require(proc.returncode == 0, 'Compile/link failed: '+str(log))
    dependencies(output, pins, kind)
    contract.verify(pins)
    pinfile = output/'source-pins.json'
    save(pinfile, pins)
    result = dict(fields(output, kind, meta), elf_sha256=sha(output/'resident_pv.elf'),
        source_pins_sha256=sha(pinfile), artifacts={str(p): sha(p) for p in output.rglob('*') if p.is_file()})
    save(output/'build.json', result)
    return verify_build(output)


def verify_build(output):
    output = Path(output).resolve(strict=True)
    meta, mandatory = baseline()
    m = json.loads((output/'build.json').read_text())
    expected = fields(output, m['kind'], meta)
    require(all(m.get(k) == v for k, v in expected.items()), 'Software build/scope contract drift')
    pinfile = output/'source-pins.json'
    require(sha(pinfile) == m['source_pins_sha256'], 'Software pin inventory drift')
    pins = json.loads(pinfile.read_text())
    require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing mandatory software input')
    contract.verify(pins)
    actual = {str(p): sha(p) for p in output.rglob('*') if p.is_file() and p != output/'build.json'}
    require(actual == m['artifacts'], 'Incomplete/extra software artifact inventory')
    commands = json.loads((output/'commands.json').read_text())
    require([dict(label=c['label'], argv=c['argv']) for c in commands] == recipes(output, m['kind']) and
            all(c['returncode'] == 0 and c['cwd'] == str(output) and c['env'] == environment() and
                c['log'] == str(output/(c['label']+'.log')) for c in commands), 'Unreviewed software recipe')
    dependencies(output, pins, m['kind'])
    require(sha(m['elf']) == m['elf_sha256'], 'ELF drift')
    accepted.check_elf(m['elf'])
    disassembly = (output/'disassembly.log').read_text()
    required = ('__wrap_'+SYMBOL, 'resident_pv_prepare', 'resident_pv_rotation_body', SYMBOL)
    require(all('<'+s+'>:' in disassembly for s in required) and '0485705b' in disassembly and
            '0205355b' in disassembly, 'Missing actual PV/prepare/strong rotation/native code')
    maptext = (output/'link.map').read_text()
    require(all(re.search(r'^LOAD '+re.escape(p)+r'$', maptext, re.M)
                for p in m['objects_recompiled']+m['objects_reused']), 'Link omitted required object')
    return m


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('build', 'recipes'):
        p = sub.add_parser(action, allow_abbrev=False)
        p.add_argument('--kind', choices=KINDS, required=True)
        p.add_argument('--output', type=Path, required=True)
        if action == 'build':
            p.add_argument('--parent-reviewed', action='store_true')
    p = sub.add_parser('verify', allow_abbrev=False)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--soc-build', type=Path)
    p = sub.add_parser('verify-soc', allow_abbrev=False)
    p.add_argument('--soc-build', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == 'build':
        result = build(args.output, args.kind, args.parent_reviewed)
    elif args.action == 'recipes':
        result = recipes(args.output, args.kind)
    elif args.action == 'verify-soc':
        result, _ = checked_soc(args.soc_build)
    else:
        result = verify_build(args.build)
        if args.soc_build:
            soc, _ = checked_soc(args.soc_build)
            require(soc['image_contract'] == result['image_contract'], 'Software/SoC image mismatch')
            result = dict(software=result, soc_build=str(args.soc_build.resolve()),
                          soc_build_sha256=sha(args.soc_build/'build.json'), execution='NOT_RUN')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
