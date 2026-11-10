#!/usr/bin/env python3
"""Build equal-work complete Attention firmware without consuming live SDK files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BASE = OUT/'akv_pair_integration_build_20261107_01'
BASE_SHA = 'd4ff1a1d1d250ccba7b24dd86d5816004158df78d80652d7133286ae7f42c042'
PV_BASE = OUT/'resident_pv_soc_eval_abba_20261109_01'
PV_SHA = '78b8555cddac6c17eb7416d76afd05bf2098683b7c62c6fec438076dbd2f133d'
PERF = ROOT/'verification/performance'
QK_SYMBOL = 'akv_experimental_qk_f16_pair_panel4'
PV_SYMBOL = 'akv_experimental_pv_f16_pair'
OBJECTS = ('main', 'pv', 'prepare', 'strong_control', 'qk', 'qk_wrap')
SOURCES = (
    'verification/performance/akv_pair_eval/main.c',
    'verification/performance/resident_rvv/rotation/main.c',
    'verification/performance/resident_rvv/rotation/pv_rotation.S',
    'verification/performance/resident_rvv/pv_prepare/prepare.S',
    'verification/performance/resident_rvv/soc_eval/main.c',
    'verification/performance/resident_rvv/soc_eval/smoke.c',
    'verification/performance/resident_rvv/soc_eval/pv.S',
    'verification/performance/resident_rvv/qk_shared/full_call/qk_wrap.S',
    'software/akv/experimental/resident_attention/qk.S',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Identity mismatch: '+str(path))


def baseline():
    require(sha(BASE/'build.json') == BASE_SHA, 'Accepted software receipt changed')
    meta = json.loads((BASE/'build.json').read_text())
    require(meta['state'] == 'BUILT_NOT_EXECUTED', 'Unexpected original software state')
    require(sha(BASE/'source-pins.json') == meta['source_pins_sha256'],
            'Original software inventory changed')
    verify(meta['artifacts'])
    historical = json.loads((BASE/'source-pins.json').read_text())
    # Pin immutable software/tool inputs, not unrelated historical live RTL.
    pins = {p: h for p, h in historical.items()
            if Path(p).is_relative_to(BASE) or not Path(p).is_relative_to(ROOT)}
    pins.update(meta['artifacts'])
    pins[str(BASE/'build.json')] = BASE_SHA
    verify(pins)
    require(sha(PV_BASE/'build.json') == PV_SHA, 'Accepted PV software receipt changed')
    pv_meta = json.loads((PV_BASE/'build.json').read_text())
    require(sha(PV_BASE/'source-pins.json') == pv_meta['source_pins_sha256'],
            'Accepted PV software inventory changed')
    pv_pins = json.loads((PV_BASE/'source-pins.json').read_text())
    pins[str(PV_BASE/'build.json')] = PV_SHA
    pins[str(PV_BASE/'source-pins.json')] = pv_meta['source_pins_sha256']
    for rel in SOURCES:
        original = str(ROOT/rel)
        if '/qk_shared/' not in rel and not rel.startswith('software/'):
            require(pv_pins.get(original) == sha(original), 'Original caller/wrapper changed')
    return meta, pins


def recipes(output, kind):
    require(kind in ('smoke', 'abba'), 'Unknown firmware kind')
    output = Path(output)
    sources = output/'inputs/source'
    cmds = json.loads((BASE/'commands.json').read_text())
    templates = {c['label']: c['argv'] for c in cmds}
    rr = sources/'verification/performance/resident_rvv'
    selected = (
        rr/'soc_eval'/('smoke.c' if kind == 'smoke' else 'main.c'),
        rr/'soc_eval/pv.S', rr/'pv_prepare/prepare.S', rr/'rotation/pv_rotation.S',
        sources/'software/akv/experimental/resident_attention/qk.S',
        rr/'qk_shared/full_call/qk_wrap.S',
    )
    result = []
    for name, source in zip(OBJECTS, selected):
        template = 'compile-00_main' if name == 'main' else 'compile-14_akv_v2_attention_rvv'
        argv = list(templates[template])
        for option, value in (('-c', source), ('-o', output/(name+'.o')),
                              ('-MF', output/(name+'.d'))):
            argv[argv.index(option)+1] = str(value)
        if name == 'strong_control':
            argv += ['-D__wrap_'+PV_SYMBOL+'=resident_pv_rotation_body',
                     '-Dresident_pv_rotation_selected=resident_pv_rotation_always']
        result.append(dict(label=name, argv=argv))
    argv = list(templates['link'])
    argv[argv.index(str(BASE/'00_main.o'))] = str(output/'main.o')
    argv[argv.index('-Wl,-Map='+str(BASE/'link.map'))] = '-Wl,-Map='+str(output/'link.map')
    argv[argv.index('-o')+1] = str(output/'attention.elf')
    i = argv.index('-Wl,--gc-sections')
    argv[i:i] = [str(output/(name+'.o')) for name in OBJECTS[1:]] + [
        '-Wl,--wrap='+PV_SYMBOL, '-Wl,--wrap='+QK_SYMBOL,
        '-Wl,--undefined=akv_attention_execute_v2_native']
    result.append(dict(label='link', argv=argv))
    gcc = Path(argv[0])
    for label, tool, options in (
        ('disassembly', 'objdump', ['-d', '-M', 'no-aliases,numeric']),
        ('segments', 'readelf', ['-lW']),
    ):
        result.append(dict(label=label, argv=[str(gcc.with_name(gcc.name[:-3]+tool)),
                                             *options, str(output/'attention.elf')]))
    return result


def dependencies(output, pins):
    for name in OBJECTS:
        text = (output/(name+'.d')).read_text().replace('\\\n', ' ')
        paths = text.split(':', 1)[1].split()
        require(paths, 'Empty compiler dependency list')
        for raw in paths:
            path = Path(raw).resolve()
            require(str(path) in pins and sha(path) == pins[str(path)],
                    'Unpinned compiler dependency: '+raw)
            require(not path.is_relative_to(ROOT/'software') and
                    not path.is_relative_to(ROOT/'hardware'), 'Live SDK/RTL compiler input')


def build(output, kind):
    output = Path(output).resolve()
    require(output.parent == OUT and output.name.startswith('stage3_attention_build_') and
            not output.exists(), 'Fresh owned signoff output required')
    meta, pins = baseline()
    output.mkdir()
    for relative in SOURCES:
        source, dest = ROOT/relative, output/'inputs/source'/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        pins[str(source)] = sha(source)
        shutil.copyfile(source, dest)
        require(sha(dest) == pins[str(source)], 'Source changed during copy')
        pins[str(dest)] = sha(dest)
    for name in ('build.py', 'test_build.py', 'README.md'):
        source, dest = HERE/name, output/'inputs'/name
        shutil.copyfile(source, dest)
        pins[str(source)] = pins[str(dest)] = sha(source)
    commands = recipes(output, kind)
    for cmd in commands:
        pins[cmd['argv'][0]] = sha(cmd['argv'][0])
    # The GCC sysroot headers are captured by the accepted compile's pins.
    save(output/'source-pins.json', pins)
    save(output/'commands.json', commands)
    env = dict(PATH='/usr/bin:/bin', HOME=os.environ.get('HOME', '/home/wangwy'),
               LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
    report = dict(state='FAIL', kind=kind, rtl_executed=False, performance_measured=False,
                  baseline=str(BASE), baseline_sha256=BASE_SHA, sdk=meta['sdk_new'],
                  golden=meta['golden'], memory_expected=meta['memory_expected'])
    try:
        for command in commands:
            verify(pins)
            with (output/(command['label']+'.log')).open('x') as log:
                proc = subprocess.run(command['argv'], cwd=output, env=env,
                                      stdout=log, stderr=subprocess.STDOUT, timeout=180)
            require(proc.returncode == 0, 'Command failed: '+command['label'])
        dependencies(output, pins)
        text = (output/'disassembly.log').read_text()
        require(all('<'+name+'>:' in text for name in (QK_SYMBOL, '__wrap_'+QK_SYMBOL,
                '__wrap_'+PV_SYMBOL, 'resident_pv_rotation_body', 'akv_experimental_resident_qk')),
                'Missing baseline or candidate leaf')
        require('0605705b' in text and '0485705b' in text, 'Resident opcodes missing')
        loaded = set(re.findall(r'^LOAD (.+)$', (output/'link.map').read_text(), re.M))
        required = set(meta['objects']) - {str(BASE/'00_main.o')}
        require(required | {str(output/(n+'.o')) for n in OBJECTS} <= loaded,
                'Missing original or replacement link object')
        verify(pins)
        report.update(state='BUILT_NOT_EXECUTED', elf=str(output/'attention.elf'),
                      elf_sha256=sha(output/'attention.elf'), post_pins_match=True,
                      baseline_arm='panel4 RVV QK + rotating-register PV',
                      candidate_arm='resident QK + resident PV',
                      shape=dict(d=128, heads=2, tokens=137, tiles=[64,64,9]),
                      source_pins_sha256=sha(output/'source-pins.json'))
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'build.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kind', choices=('smoke','abba'), required=True)
    args = parser.parse_args()
    result = build(args.output, args.kind)
    print(json.dumps(result, indent=2))
    return int(result['state'] != 'BUILT_NOT_EXECUTED')


if __name__ == '__main__':
    raise SystemExit(main())
