#!/usr/bin/env python3
"""Prepare private SoftFloat Q8_K power firmware inputs; never launch RTL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[3] / 'ara_dsa_signoff_integration/verification/out'
DEFAULT = OUT / 'power_softdiv_prepare_20261117_01'
PARENT = OUT / 'operator_projection_real_prepare_20261115_release_01'
SOFTFLOAT = Path('/home/wangwy/openproject/riscv-isa-sim/softfloat')
QUANT_SHA = '26dfc79772e738286a8d751254080b9aa0fdb1e3ada77eb8a1cdaa8f2960a6b5'
SDK = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'
SOURCES = ('f32_div.c', 's_normSubnormalF32Sig.c', 's_roundPackToF32.c',
           's_propagateNaNF32UI.c', 'softfloat_state.c', 'softfloat_raiseFlags.c',
           's_countLeadingZeros8.c')
HEADERS = ('platform.h', 'internals.h', 'specialize.h', 'softfloat.h',
           'softfloat_types.h', 'primitives.h', 'primitiveTypes.h')
PRIVATE = ('f32_div', 'softfloat_normSubnormalF32Sig', 'softfloat_roundPackToF32',
           'softfloat_propagateNaNF32UI', 'softfloat_roundingMode',
           'softfloat_detectTininess', 'softfloat_exceptionFlags',
           'softfloat_raiseFlags', 'softfloat_countLeadingZeros8',
           'extF80_roundingPrecision')
REPLACEMENTS = (
    ('const float iscale = -127.f / (fabsf(max_val) > fabsf(min_val) ? max_val : min_val);',
     'const float iscale = power_softdiv_f32_rne(-127.f, (fabsf(max_val) > fabsf(min_val) ? max_val : min_val));'),
    ('y_block->d = 1.0f / iscale;', 'y_block->d = power_softdiv_f32_rne(1.0f, iscale);'))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def patch_quantizer(source):
    """Fail closed on the shared frozen source; change only Q8_K's two divides."""
    require(hashlib.sha256(source.encode()).hexdigest() == QUANT_SHA, 'Frozen quant source drift')
    begin = source.index('void quantize_row_q8_K(')
    end = source.index('\n//===================================== Dot products', begin)
    body = source[begin:end]
    for old, new in REPLACEMENTS:
        require(body.count(old) == 1, 'Quantizer division site changed')
        body = body.replace(old, new)
    return '#include "power_softdiv.h"\n' + source[:begin] + body + source[end:]


def quant_compile_command(argv, output, overlay, include):
    """Adapt a pinned parent compile command, not its SDK or data inputs."""
    argv = list(map(str, argv))
    original = Path(argv[argv.index('-c') + 1])
    require(sha(original) == QUANT_SHA, 'Parent quant source drift')
    require('-fno-fast-math' in argv and '-ffp-contract=off' in argv and
            '-mabi=lp64d' in argv and not any(x in argv for x in ('-ffast-math', '-flto')),
            'Unsupported quant compile semantics')
    argv[argv.index('-c') + 1] = str(overlay)
    argv[argv.index('-o') + 1] = str(output)
    argv[argv.index('-MF') + 1] = str(Path(output).with_suffix('.d'))
    return argv[:1] + ['-I' + str(include), '-iquote', str(original.parent)] + argv[1:]


HOST_ORACLE = r'''
#include <stdint.h>
#include <fenv.h>
uint32_t power_host_flags;
uint32_t power_host_div(uint32_t a, uint32_t b) {
    union { uint32_t u; float f; } x = {.u=a}, y = {.u=b}, z;
    fesetround(FE_TONEAREST); feclearexcept(FE_ALL_EXCEPT);
    volatile float lhs=x.f, rhs=y.f;
    volatile float value=lhs/rhs;
    z.f=value;
    int f=fetestexcept(FE_ALL_EXCEPT);
    power_host_flags = !!(f & FE_INEXACT) | (!!(f & FE_UNDERFLOW)<<1) |
        (!!(f & FE_OVERFLOW)<<2) | (!!(f & FE_DIVBYZERO)<<3) | (!!(f & FE_INVALID)<<4);
    return z.u;
}
'''


def prepare(output=DEFAULT):
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == OUT.resolve() and
            re.fullmatch(r'power_softdiv_prepare_20261117_[A-Za-z0-9_.-]+', output.name)
            and not output.exists(), 'Fresh owned output required')
    for key in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH',
                'LD_PRELOAD', 'LD_LIBRARY_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'CFLAGS', 'LDFLAGS'):
        require(not os.environ.get(key), 'Compiler environment injection: ' + key)
    commands = json.loads((PARENT / 'commands.json').read_text())
    command = next(x['argv'] for x in commands if x['label'] == 'compile-firmware_quant.o')
    inherited_pins = json.loads((PARENT / 'source-pins.json').read_text())
    parent_pins = {}
    for name, digest in inherited_pins.items():
        name = str(Path(name).resolve())
        require(name not in parent_pins or parent_pins[name] == digest, 'Conflicting inherited include pins')
        parent_pins[name] = digest
    original = Path(command[command.index('-c') + 1])
    require(sha(original) == parent_pins[str(original)] == QUANT_SHA, 'Quant source identity')
    output.mkdir()
    sf = output / 'softfloat'
    sf.mkdir()
    pins = {str(p): sha(p) for p in (HERE / 'software_div.py', HERE / 'software_div.c',
            HERE / 'test_software_div.py', PARENT / 'commands.json', PARENT / 'source-pins.json', original)}
    for build in sorted((PARENT / 'cases').glob('*/build.json')):
        require(json.loads(build.read_text())['sdk_commit'] == SDK, 'Frozen SDK mismatch')
        pins[str(build)] = sha(build)
    fixtures = sorted((PARENT / 'cases').iterdir()) + [
        OUT / ('operator_qbs_prepare_20261115_q4_m4_%s_01' % mode) / 'data'
        for mode in ('native', 'x32')]
    for fixture in fixtures:
        for path in fixture.iterdir():
            if path.suffix == '.bin':
                pins[str(path)] = sha(path)
    for mode in ('native', 'x32'):
        parent = OUT / ('operator_qbs_prepare_20261115_q4_m4_%s_01' % mode)
        receipt = json.loads((parent / 'build.json').read_text())
        require(receipt['sdk_commit'] == SDK, 'M4 SDK mismatch')
        for path in (parent / 'build.json', Path(receipt['source_pins'])):
            pins[str(path)] = sha(path)
        inherited = json.loads(Path(receipt['source_pins']).read_text())
        for path, digest in inherited.items():
            if path.endswith('/arch/riscv/quants.c'):
                require(sha(path) == digest == QUANT_SHA, 'M4 quantizer drift')
                pins[path] = digest
    for name in SOURCES + HEADERS:
        src = SOFTFLOAT / name
        pins[str(src)] = sha(src)
        shutil.copyfile(src, sf / name)
    (sf / 'config.h').write_text('/* Private little-endian bare-metal/host SoftFloat build. */\n')
    namespace = output / 'power_namespace.h'
    namespace.write_text(''.join('#define %s power_sf_%s\n' % (s, s) for s in PRIVATE))
    (output / 'power_softdiv.h').write_text(
        '#ifndef POWER_SOFTDIV_H\n#define POWER_SOFTDIV_H\n'
        'float power_softdiv_f32_rne(float, float);\n#endif\n')
    shutil.copyfile(HERE / 'software_div.c', output / 'software_div.c')
    overlay = output / 'quants-softdiv.c'
    overlay.write_text(patch_quantizer(original.read_text()))
    (output / 'host_oracle.c').write_text(HOST_ORACLE)
    env = dict(PATH='/usr/bin:/bin', HOME=str(output), LC_ALL='C', TZ='UTC',
               PYTHONDONTWRITEBYTECODE='1', POWER_SOFTDIV_BUILD=str(output))
    executed = []

    def run(label, argv):
        argv = list(map(str, argv))
        proc = subprocess.run(argv, cwd=output, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=120)
        (output / (label + '.log')).write_bytes(proc.stdout)
        executed.append(dict(label=label, argv=argv, returncode=proc.returncode))
        require(proc.returncode == 0, label + ': ' + proc.stdout[-3000:].decode(errors='replace'))
        return proc.stdout.decode()

    cc = Path(command[0])
    objdump = cc.with_name(cc.name.replace('gcc', 'objdump'))
    nm = cc.with_name(cc.name.replace('gcc', 'nm'))
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
             '-O2', '-fno-tree-vectorize', '-fno-fast-math', '-ffp-contract=off',
             '-ffunction-sections', '-fdata-sections', '-fno-strict-aliasing',
             '-I' + str(sf), '-include', str(namespace)]
    objects = []
    for source in [sf / n for n in SOURCES] + [output / 'software_div.c']:
        obj = output / (source.stem + '.o')
        run('compile-' + source.stem, [cc, *flags, '-MD', '-MF', obj.with_suffix('.d'),
                                      '-c', source, '-o', obj])
        objects.append(obj)
    helper = output / 'power-softdiv.o'
    run('combine-helper', [cc, *flags, '-nostdlib', '-r', *objects, '-o', helper])
    require(not run('helper-undefined', [nm, '-u', helper]).strip(), 'Helper has unresolved dependencies')
    helper_dis = run('helper-disassembly', [objdump, '-d', helper])
    require(not re.search(r'\bf(?:div|sqrt|mul|add|sub|madd|msub|nmadd|nmsub|cvt)\.', helper_dis),
            'FP arithmetic in integer helper')
    require(re.search(r'\bdivu\b', helper_dis) and re.search(r'\bcsrs\s+fflags,', helper_dis),
            'Missing integer divide/fflags OR')
    quant = output / 'quant-softdiv.o'
    qcmd = quant_compile_command(command, quant, overlay, output)
    run('compile-quant', qcmd)
    qdis = run('quant-q8k-disassembly', [objdump, '-dr', '--disassemble=quantize_row_q8_K', quant])
    require(not re.search(r'\bfdiv\.', qdis) and qdis.count('R_RISCV_CALL_PLT\tpower_softdiv_f32_rne') == 2,
            'Q8_K must have exactly two helper calls and no FP division')
    # Pin every actual compiler include, including inherited SDK/llama inputs.
    for dep in output.glob('*.d'):
        for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name).resolve()
            if not path.is_relative_to(output):
                digest = sha(path)
                if str(path) in parent_pins:
                    require(parent_pins[str(path)] == digest, 'Parent include drift: ' + str(path))
                else:
                    require(path.is_relative_to(cc.parents[1]), 'Unexpected compiler dependency: ' + str(path))
                pins[str(path)] = digest
    host_sources = [sf / n for n in SOURCES] + [output / 'software_div.c', output / 'host_oracle.c']
    run('host-build', ['/usr/bin/gcc', '-std=c11', '-O2', '-shared', '-fPIC',
        '-fno-fast-math', '-frounding-math', '-ffp-contract=off', '-fno-strict-aliasing',
        '-DPOWER_SOFTDIV_HOST', '-I' + str(sf), '-include', namespace,
        *host_sources, '-lm', '-o', output / 'host-softdiv.so'])
    recipe = dict(schema='power-softdiv-20261117-v1', label='SW_WORKAROUND_SOFTFLOAT_F32_DIV_RNE',
        sdk_commit=SDK, allowed_activation_profiles=[1], quantizer='quantize_row_q8_K',
        modes=['native', 'rvv'], shapes=['M1', 'M4'], helper_object=str(helper),
        quant_object=str(quant), include_overlay=str(output), quant_source_overlay=str(overlay),
        original_quant_sha256=QUANT_SHA, quant_compile_argv=qcmd,
        link_instructions='Replace parent quant.o/rvv_quant_dot.o with quant_object; append helper_object '
            'before --gc-sections. Never link original and replacement quant objects together. '
            'Use the identical two objects for native and RVV M1/M4 Q8_K programs.',
        patch_api='software_div.patch_quantizer(source); software_div.quant_compile_command('
            'parent_compile_argv, output_object, overlay_source, include_overlay)',
        timing_scope='Full runtime quantization stays inside the original quant ROI on BOTH paths; '
            'data, goldens, vector source and timing markers unchanged. Instruction activity changes.',
        preconditions=['FRM=0 enforced by benchmark', 'single worker; private SoftFloat state',
                       'SDK dbe2b78817ef45b912444afcb85ad6e01a2be135', 'activation profile Q8_K=1 only'],
        flags='SoftFloat RNE/after-rounding tininess; csrs fflags OR, preserves FRM and existing flags',
        no_other_profiles_replaced=True, rtl_executed=False, power_acceptance=False)
    save(output / 'recipe.json', recipe)
    run('unit-tests', ['/usr/bin/python3', '-B', '-m', 'unittest', 'discover', '-s', HERE,
                       '-p', 'test_software_div.py', '-v'])
    for path, digest in pins.items():
        require(sha(path) == digest, 'Preparation source drift: ' + path)
    pins.update({str(p): sha(p) for p in output.rglob('*') if p.is_file()})
    pins[str(cc)] = sha(cc)
    pins[str(objdump)] = sha(objdump)
    pins[str(nm)] = sha(nm)
    pins['/usr/bin/gcc'] = sha('/usr/bin/gcc')
    save(output / 'source-pins.json', pins)
    save(output / 'commands.json', executed)
    report = dict(state='HOST_TESTED_CROSS_BUILT_NOT_TARGET_EXECUTED', **recipe,
        helper_sha256=sha(helper), quant_sha256=sha(quant), source_pins=str(output / 'source-pins.json'),
        source_pins_sha256=sha(output / 'source-pins.json'),
        test_report=str(output / 'unit-tests.log'), simulations_launched=0,
        host_checks=dict(unit_tests=6, rational_host_edge_random_vectors=2256,
            captured_fixtures=10, captured_blocks=336, captured_scale_reciprocal_pairs=672,
            golden_q8_blocks_byte_exact=True, fault_operand_and_seeded_fflags_checks=True),
        original_baseline_fail_preserved=True, netlist_modified=False,
        source_origin=str(SOFTFLOAT), source_origin_note='Existing Spike Berkeley SoftFloat Release 3d; '
            'source bytes copied unchanged, namespace overlay only. See retained source license notices.',
        artifacts={str(p): sha(p) for p in output.rglob('*') if p.is_file()})
    save(output / 'build.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        result = prepare(args.output)
    except Exception as exc:
        if args.output.is_dir() and not (args.output / 'source-pins.json').exists():
            save(args.output / 'failure.json', dict(state='PREPARATION_FAILED', error=repr(exc)))
        raise
    print(json.dumps({k: result[k] for k in ('state', 'helper_object', 'quant_object', 'source_pins')}))
