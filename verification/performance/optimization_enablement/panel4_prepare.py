#!/usr/bin/env python3
"""Freeze the single-C SDK overlay and test the actual selector on the host."""
import argparse
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = ROOT/'verification/performance/optimization_enablement'
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
REV = 'f50092f2d22238c6be4b6c159a1ad71a4ea68678'
BEFORE = '69832cfc9bfcc20aa17b6c57085041fc03ceae77020dd4bc81901590c10d1dfd'
NATIVE = Path('software/akv/src/akv_v2_native_riscv.c')
GCC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    with path.open('x') as stream:
        json.dump(obj, stream, sort_keys=True, indent=2)
        stream.write('\n')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and re.fullmatch(
        r'enablement_panel4_[A-Za-z0-9_-]+', out.name) and not out.exists(), 'Fresh PANEL4 output required')
    out.mkdir()
    inputs = out/'inputs'; inputs.mkdir()
    pins, commands = {}, []
    result = dict(state='FAIL', sdk_revision=REV, native_executed=False,
                  performance_measured=False, fpga_acceptance=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', LC_ALL='C')

    def pin(path):
        pins[str(path)] = sha(path)

    def run(label, argv):
        argv = list(map(str, argv))
        pin(Path(shutil.which(argv[0]) or argv[0]).resolve())
        with (out/(label+'.log')).open('xb') as log:
            proc = subprocess.run(argv, cwd=out, env=env, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=120)
        commands.append(dict(label=label, argv=argv, returncode=proc.returncode))
        require(proc.returncode == 0, label+' failed')
        return (out/(label+'.log')).read_text()

    try:
        for name in ('panel4_prepare.py', 'panel4_selection_test.c'):
            src = HERE/name; dst = inputs/name
            shutil.copyfile(src, dst); pin(src); pin(dst)
        archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', REV, 'software/akv'])
        (out/'sdk.tar').write_bytes(archive); pin(out/'sdk.tar')
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            require(all((m.isfile() or m.isdir()) and '..' not in Path(m.name).parts
                        and not Path(m.name).is_absolute() for m in tar.getmembers()), 'Unsafe SDK archive')
            tar.extractall(inputs/'sdk')
        native = inputs/'sdk'/NATIVE
        require(sha(native) == BEFORE, 'Pinned SDK preimage drift')
        original = native.read_text()
        shutil.copyfile(native, inputs/'native-before.c'); pin(inputs/'native-before.c')
        shutil.copyfile(ROOT/NATIVE, native); pin(ROOT/NATIVE)
        source = native.read_text()
        start = source.index('static int qk_panel4_enabled_for_plan(')
        end = source.index('static inline float negative_infinity_f32', start)
        before_start = original.index('static int qk_panel4_enabled_for_plan(')
        before_end = original.index('static inline float negative_infinity_f32', before_start)
        restored = source[:start]+original[before_start:before_end]+source[end:]
        restored = restored.replace('qk_panel4_enabled_for_plan(plan, auto_device, automatic)',
                                    'qk_panel4_enabled_for_plan(plan)')
        restored = restored.replace('/* Optional on freestanding targets; generic execution remains opt-in. */',
                                    '/* Optional on freestanding targets: no environment provider means OFF. */')
        require(restored == original and source.count(
            'qk_panel4_enabled_for_plan(plan, auto_device, automatic)') == 1, 'Overlay exceeds selector scope')
        (out/'sdk-overlay.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),
            source.splitlines(True), fromfile=str(NATIVE), tofile=str(NATIVE))))
        inc = inputs/'panel4_selection.inc'; inc.write_text(source[start:end]); pin(inc)
        sdk = inputs/'sdk/software/akv'
        for path in (inputs/'sdk').rglob('*'):
            if path.is_file(): pin(path)
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                 '-ffunction-sections', '-fdata-sections', '-I'+str(sdk/'include'), '-I'+str(inputs)]
        counts = {}
        for compiler, sanitizers in (('/usr/bin/gcc', []), ('clang', ['-fsanitize=undefined', '-fno-sanitize-recover=all'])):
            for absent in (False, True):
                tag = Path(compiler).name+('-noenv' if absent else '-env')
                binary = out/tag
                run(tag+'-compile', [compiler, *flags, *sanitizers,
                    *(['-DPANEL4_NO_ENV'] if absent else []), inputs/'panel4_selection_test.c',
                    sdk/'src/akv_runtime.c', '-Wl,--gc-sections', '-lm', '-o', binary])
                text = run(tag+'-run', [binary])
                matched = re.fullmatch(r'PANEL4_SELECTOR_PASS cases=(\d+) no_env=([01])\n', text)
                require(matched and int(matched[2]) == absent, 'Incomplete selector test')
                counts[tag] = int(matched[1])
        cross_flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
            '-O3', '-std=gnu11', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
            '-ffreestanding', '-fno-builtin', '-ffunction-sections', '-fdata-sections']
        run('native-cross-compile', [GCC, *cross_flags, '-I'+str(sdk/'include'),
            '-c', native, '-o', out/'native.o'])
        objdump = GCC.with_name('riscv64-unknown-elf-objdump')
        dis = run('native-disassembly', [objdump, '-dr', out/'native.o'])
        for symbol in ('akv_v2_compute_scores_f16_d128_gqa6_panel4',
                       'akv_v2_compute_scores_f16_d128_gqa6', 'getenv'):
            require(symbol in dis, 'Missing native selector target: '+symbol)
        require(all(sha(p) == h for p,h in pins.items()), 'Source drift')
        result.update(state='PANEL4_HOST_SELECTOR_PASS_NOT_NATIVE', checks=counts,
            post_pins_match=True, native_source_sha256=sha(native),
            assembly_sha256=sha(sdk/'src/akv_v2_attention_rvv.S'), overlay_files=[str(NATIVE)],
            sdk=str(inputs/'sdk'), native_object=str(out/'native.o'))
    except Exception as exc:
        result['error'] = repr(exc)
    save(out/'source-pins.json', pins); save(out/'commands.json', commands)
    result['source_pins_sha256'] = sha(out/'source-pins.json')
    result['artifacts'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    save(out/'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('artifacts',)}, sort_keys=True))
    return int(result['state'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
