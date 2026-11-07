#!/usr/bin/env python3
"""Archive-only boundary ELF preparation. Requires owner seal-ready; never runs RTL."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DEFAULT_OUTPUT = OUT / 'akv_pair_boundary_build_20261107_01'
CAPTURE = Path('/home/wangwy/llama/captures/'
               'qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv128/decode/block')
ORIGIN = OUT / 'akv-native-pair-runtime-build-20261024-03'
ORIGIN_SHA = {
    'build.json': 'bcc9f87bcd5563d5038870da4bba2291b3fb37568c0693b4ab300b861408ff14',
    'source-pins.json': 'f666e470ed2fc3a8a41e9a47f9915506f9ac0ce9710dcee8fc1162116591461f',
    'data.S': '47db9c6d421b3d3f837046fe337cbacf9d327aa2b70f7bc7a5412b76853bc794',
}
SDK_COMMIT = '785084122af984c1dd3fd6318efaf70cdcb017e8'
SDK_TREE = '099017ee4f6543417e4d666a5e0958ce175defe5'
COMMON_TREE = '027626ca2e2524cafbcb61b5b44b70fce9ec1cff'
HARNESS = 'verification/akv/paired_heads/native_runtime_main.c'
LEGACY = {
    HARNESS: '3e5700a22e67843406b40040045d22478d5b808a8fdc2505024c1cc498e88807',
    'verification/akv/paired_heads/native_runtime_check.py':
        '51c3d8923dc6ada63e06d8d1b4e10d81021044f6ddff2b237f0a40b14cd1d647',
    'verification/akv/paired_heads/attention_run.py':
        '90d8a4f4870249a98ff9d1ad44b284a998ceaacddc1b5d5da54390f8b5342362',
    'verification/akv/run_qk_panel4_abba.py':
        'b464998eec4391141af1b5e351f6785358374ed9ea790d9d1252c79aebc7823e',
    'verification/akv/run_refill_overlap_probe.py':
        'e5a327c531753118f57b10bb891c792b132b71770446f048779e4c9a0631403b',
    'verification/qbs/run_half_scale_soc.py':
        '7ddcf48bab34f6e06c62782347c1a25eb8b0d934e4064c8a1155e92185c704df',
    'verification/qbs/run_tile_context_engine.py':
        '320f60fdef3685be44ad58e74f657a7e179e08608916992994a66b87ddfea150',
}
ARCHIVE_PATHS = ['software/akv', 'apps/common', *LEGACY]
ARCHIVE_SHA = '405d55dfb555ad468f3ecc37fd8ab4c0e7db020962bcce19b1fb080a2d92209c'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
CC_SHA = '7af14c2b2b9f8ce5dc7b07521a929537a5306078df2a3a20bb367b7448828bbc'
HOST_CC = Path('/usr/bin/gcc')
HOST_CC_SHA = '472ed0bac12ba95f15d484b506ff1b32cc089cc47f5253a7ff0697667501f322'
GIT = Path('/usr/bin/git')
GIT_SHA = 'be60250fab3f99aaf4c136e7c50ce00d7a5af30a184be60bf237b13ee997309a'
OWN_FILES = ('build.py', 'main.c', 'check.py', 'test_boundary.py')
CASES = [dict(d=64, heads=3, kv=1, source_head=0),
         dict(d=96, heads=3, kv=65, source_head=1),
         dict(d=128, heads=6, kv=7, source_head=0),
         dict(d=128, heads=2, kv=64, source_head=1)]
ORDER = [0, 1, 0]
CALL_COMMANDS = [197, 84, 197, 774, 373, 774, 137, 137, 137, 386, 98, 386]
IMAGE = dict(NrLane=4, VLEN=1024, AXI=128, L2sim_bytes=16777216,
             shared_integer_multiply=True, EnableSharedFma=0)
PAYLOADS = {
    'q': dict(symbol='candidate_query_f32', role='attn_q_input', bytes=6144,
              sha256='bc12350a4d43614d43765d7fb0444b11469f5a74f85ea9410127ad7062435df8',
              meta_sha256='9cacfa07596643b82561566a4e2f12f9f0eece223e42a7d0fe9c5e78e9e0cb3a',
              fnv64=0xafefa3ea4b06654c, type='f32', shape=[128, 1, 12, 1],
              strides=[4, 512, 512, 6144]),
    'k': dict(symbol='candidate_key', role='attn_k_input', bytes=131072,
              sha256='fbf3599b98bd9f16e9a0caa765872f91efe9906ee8785d84124a7b34e53321d0',
              meta_sha256='75719dbda368fc09a5ebda2866d8528ed7614494cd2d98e25cc879182c80ddb5',
              fnv64=0x15c8a23d8a23ee33, type='f16', shape=[128, 256, 2, 1],
              strides=[2, 256, 65536, 131072]),
    'v': dict(symbol='candidate_value', role='attn_v_input', bytes=131072,
              sha256='d4f00cab1a0782c83ef611eebf78f32273e7f73dc4910eda5bc90e2bbbcc3cc8',
              meta_sha256='71ca6f2d3ef370aaf76340a5538e43fa9b49d71222f074a748b7251f738e7f44',
              fnv64=0x6e665fd6bccf1012, type='f16', shape=[128, 256, 2, 1],
              strides=[2, 256, 65536, 131072]),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unique_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def fnv64(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return value


def verify(pins):
    require(isinstance(pins, dict) and pins, 'Empty identity inventory')
    for path, digest in pins.items():
        require(Path(path).is_absolute() and Path(path).is_file() and
                re.fullmatch('[0-9a-f]{64}', digest) and sha(path) == digest,
                'Input/artifact identity drift: ' + path)


def validate_data(capture=CAPTURE, origin=ORIGIN):
    capture, origin = Path(capture), Path(origin)
    pins = {str(origin / n): h for n, h in ORIGIN_SHA.items()}
    verify(pins)
    receipt, inventory = read_json(origin / 'build.json'), read_json(origin / 'source-pins.json')
    require(receipt['source_pins_sha256'] == ORIGIN_SHA['source-pins.json'] and
            receipt['cases'] == [{k: c[k] for k in ('d', 'heads', 'kv')} for c in CASES] and
            receipt['expected_commands'] == 3680, 'Original data receipt contract')
    mapping = (origin / 'data.S').read_text()
    for item in PAYLOADS.values():
        for suffix, digest in (('.bin', item['sha256']), ('.json', item['meta_sha256'])):
            path = capture / (item['role'] + '-0' + suffix)
            require(inventory.get(str(CAPTURE / path.name)) == digest, 'Original capture pin missing')
            pins[str(path)] = digest
        raw = capture / (item['role'] + '-0.bin')
        meta = read_json(capture / (item['role'] + '-0.json'))
        require(meta == dict(role=item['role'] + '-0', tensor_name=item['role'] + '-0',
                            type=item['type'], shape=item['shape'], strides=item['strides'],
                            nbytes=item['bytes']), 'Original metadata shape/stride/type changed')
        require(raw.stat().st_size == item['bytes'] and fnv64(raw.read_bytes()) == item['fnv64'],
                'Independent full-payload host FNV mismatch')
        require(f"{item['symbol']}:\n.incbin {json.dumps(str(CAPTURE / raw.name))}\n" in mapping,
                'Original native symbol/data mapping changed')
    verify(pins)
    return pins


def expected_header():
    return ''.join(f'#define BOUNDARY_EXPECT_{key.upper()} UINT64_C(0x{p["fnv64"]:016x})\n'
                   for key, p in PAYLOADS.items())


def data_assembly(capture=CAPTURE):
    lines = ['.section .rodata.akv_boundary,"a",@progbits']
    for item in PAYLOADS.values():
        symbol = item['symbol']
        lines += ['.balign 64', '.global ' + symbol, '.type ' + symbol + ', @object',
                  symbol + ':', '.incbin ' + json.dumps(str(Path(capture) / (item['role'] + '-0.bin'))),
                  f'.size {symbol}, .-{symbol}']
    return '\n'.join(lines + ['.section .note.GNU-stack,"",@progbits', ''])


def archive_members(archive):
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = tar.getmembers()
        require(len({m.name for m in members}) == len(members), 'Duplicate archive member')
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                    '..' not in Path(m.name).parts for m in members), 'Unsafe archive member')
        return {m.name: tar.extractfile(m).read() for m in members if m.isfile()}


def unpack_archive(archive, inputs):
    archive_members(archive)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(inputs, filter='data')


def linker_script(common):
    text = (Path(common) / 'arch.link.ld').read_text()
    require(text.count('LENGTH = 0x00100000') == 1, 'Linker template changed')
    return text.replace('ALIGNMENT', '16').replace('LENGTH = 0x00100000', 'LENGTH = 0x01000000')


def sources(output):
    inputs = Path(output) / 'inputs'
    return [HERE / 'main.c', Path(output) / 'data.S',
            *[inputs / 'apps/common' / n for n in
              ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')],
            *[inputs / 'software/akv/src' / n for n in
              ('akv_runtime.c', 'akv_decode.c', 'akv_features.c', 'akv_prefill_reference.c',
               'akv_native_riscv.c', 'akv_v2_native_riscv.c',
               'akv_v2_attention_rvv.S', 'akv_attention_rvv.S')]]


def compile_flags(output):
    output = Path(output)
    return ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
            '-O3', '-DNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
            '-ffunction-sections', '-fdata-sections', '-std=gnu11', '-Wall', '-Wextra',
            '-Wno-unknown-pragmas', '-DNR_LANES=4', '-DVLEN=1024', '-DAKV_REFILL_OVERLAP=0',
            '-I' + str(output / 'inputs/software/akv/include'),
            '-I' + str(output / 'inputs/apps/common'), '-I' + str(output),
            '-iquote', str(output / 'inputs/verification/akv/paired_heads')]


def compile_recipe(output):
    output = Path(output)
    result = []
    for index, src in enumerate(sources(output)):
        obj = output / f'{index:02d}_{src.stem}.o'
        extra = (['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns']
                 if src.name == 'string.c' else [])
        result.append([str(CC), *compile_flags(output), *extra, '-MD', '-MF',
                       str(obj.with_suffix('.d')), '-c', str(src), '-o', str(obj)])
    return result


def link_recipe(output):
    output = Path(output)
    return [str(CC), *compile_flags(output)[:4], '-static', '-nostdlib', '-nostartfiles',
            *[c[-1] for c in compile_recipe(output)], '-Wl,--gc-sections',
            '-Wl,-Map=' + str(output / 'link.map'), '-T', str(output / 'link.ld'),
            '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group',
            '-o', str(output / 'akv_pair_boundary.elf')]


def dependency_inputs(path):
    text = Path(path).read_text().replace('\\\n', ' ')
    require(': ' in text, 'Malformed dependency inventory')
    return [Path(p).resolve(strict=True) for p in shlex.split(text.split(': ', 1)[1])]


def build(output=DEFAULT_OUTPUT, cc=CC, *, seal_ready=False):
    require(seal_ready is True, 'Owner seal-ready is required before any crossbuild')
    output, cc = Path(output).resolve(), Path(cc).resolve()
    require(output.parent == OUT.resolve() and
            re.fullmatch(r'akv_pair_boundary_build_\d{8}_\w+', output.name), 'Output ownership restriction')
    require(not output.exists(), 'Use a fresh output directory')
    require(cc == CC.resolve() and sha(cc) == CC_SHA, 'Only the pinned GNU target compiler is allowed')
    require(sha(HOST_CC) == HOST_CC_SHA and sha(GIT) == GIT_SHA, 'GNU host/git tool identity')
    pins = validate_data()
    pins.update({str(HERE / n): sha(HERE / n) for n in OWN_FILES})
    pins.update({str(p.resolve()): sha(p) for p in (CC, HOST_CC, GIT, Path(sys.executable))})
    output.mkdir()
    (output / 'tmp').mkdir()
    inputs = output / 'inputs'
    inputs.mkdir()
    commands = []
    env = dict(PATH='/usr/bin:/bin', HOME=os.environ.get('HOME', '/home/wangwy'), LC_ALL='C',
               TMPDIR=str(output / 'tmp'), PYTHONDONTWRITEBYTECODE='1')

    def run(label, argv, binary=False):
        argv = list(map(str, argv))
        proc = subprocess.run(argv, cwd=output, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=180)
        log = output / (label + '.log')
        log.write_bytes(proc.stderr if binary else proc.stdout + proc.stderr)
        commands.append(dict(label=label, argv=argv, cwd=str(output), env=env,
                             returncode=proc.returncode, log=str(log)))
        save(output / 'commands.json', commands)
        require(proc.returncode == 0, label + ': ' + log.read_text(errors='replace')[-3000:])
        return proc.stdout if binary else proc.stdout.decode().strip()

    try:
        for name, tree in (('software/akv', SDK_TREE), ('apps/common', COMMON_TREE)):
            require(run('tree-' + Path(name).name, [GIT, '-C', ROOT, 'rev-parse',
                        SDK_COMMIT + ':' + name]) == tree, 'Version contract drift')
        archive = run('archive', [GIT, '-C', ROOT, 'archive', SDK_COMMIT, *ARCHIVE_PATHS], True)
        require(hashlib.sha256(archive).hexdigest() == ARCHIVE_SHA, 'Exact archive identity mismatch')
        archive_file = inputs / 'sdk-785084122.tar'
        archive_file.write_bytes(archive)
        unpack_archive(archive, inputs)
        for name, digest in LEGACY.items():
            require(sha(inputs / name) == digest, 'Archived helper identity: ' + name)
        pins.update({str(p): sha(p) for p in inputs.rglob('*') if p.is_file()})
        run('gnu-version', [cc, '--version'])
        run('hosttests', [sys.executable, '-B', HERE / 'test_boundary.py', '-v'])
        (output / 'expected.h').write_text(expected_header())
        (output / 'data.S').write_text(data_assembly())
        (output / 'link.ld').write_text(linker_script(inputs / 'apps/common'))
        for lib in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
            path = Path(run('locate-' + lib, [cc, *compile_flags(output)[:2],
                                            '-print-file-name=' + lib])).resolve(strict=True)
            pins[str(path)] = sha(path)
        for tool in ('cc1', 'as', 'ld', 'collect2'):
            path = Path(run('locate-' + tool, [cc, '-print-prog-name=' + tool])).resolve(strict=True)
            pins[str(path)] = sha(path)
        for index, argv in enumerate(compile_recipe(output)):
            require(not Path(argv[-1]).exists(), 'Refusing an old object')
            run(f'compile-{index:02d}', argv)
        run('link', link_recipe(output))
        for name, switches in (('objdump', ['-d']), ('readelf', ['-lW'])):
            tool = cc.with_name(cc.name.replace('gcc', name))
            pins[str(tool.resolve())] = sha(tool)
            run(name, [tool, *switches, output / 'akv_pair_boundary.elf'])
        for dep in output.glob('*.d'):
            for path in dependency_inputs(dep):
                require(str(path) not in pins or pins[str(path)] == sha(path), 'Compile input drift')
                pins[str(path)] = sha(path)
        for n in ('expected.h', 'data.S', 'link.ld'):
            pins[str(output / n)] = sha(output / n)
        verify(pins)
        pinfile = output / 'source-pins.json'
        save(pinfile, pins)
        elf = output / 'akv_pair_boundary.elf'
        manifest = dict(schema=1, kind='boundary', state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
            target_executed=False, rtl_executed=False, performance_measured=False, seal_ready=True,
            post_pins_match=True, elf=str(elf), elf_sha256=sha(elf), sdk_head=SDK_COMMIT,
            sdk_tree=SDK_TREE, common_tree=COMMON_TREE, sdk_archive=str(archive_file),
            sdk_archive_sha256=ARCHIVE_SHA, sdk_unmodified=True, dirty_asm_excluded=True,
            SDKpins={str(p.relative_to(inputs)): sha(p) for p in (inputs / 'software/akv').rglob('*')
                     if p.is_file()}, all_runtime_objects_recompiled=True,
            objects_recompiled=len(compile_recipe(output)),
            objects=[c[-1] for c in compile_recipe(output)], compile_commands=str(output / 'commands.json'),
            source_pins=str(pinfile), source_pins_sha256=sha(pinfile), cases=CASES, order=ORDER,
            runs=12, expected_commands=3680, per_call_commands=CALL_COMMANDS, image_contract=IMAGE,
            capture=str(CAPTURE), payloads=PAYLOADS, original_data_receipt=str(ORIGIN),
            origin_usage='Data identity/mapping only; no inherited RTL acceptance',
            harness=dict(path=str(inputs / HARNESS), sha256=LEGACY[HARNESS], body='boundary_body'),
            toolchain=dict(target=str(CC), host=str(HOST_CC), zcc=False),
            environment=dict(AKV_PAIR_HEADS='OFF/ON/OFF; all other names return NULL'),
            numerical='Original byte-exact OFF/ON/OFF output4096B+gap, Q/mask/descriptor/guards/CSR; '
                      'not an independent full Attention oracle',
            scope='Four derived dims/heads/token boundaries from one Qwen2.5 capture, not four models; '
                  'functional/path regression only, no complete-call performance claim',
            checker=dict(entry=str(HERE / 'check.py'), function='check_run(log_path, build_dir)',
                         vector_function='check_vector_workcounts(vector_path, build_dir)',
                         independent_image_and_uvm_required=True),
            artifacts={str(p): sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
        save(output / 'build.json', manifest)
        spec = importlib.util.spec_from_file_location('akv_boundary_postbuild', HERE / 'check.py')
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        manifest['elf_link_checks'] = checker.verify_build(output)['elf_link_checks']
        save(output / 'build.json', manifest)
        return manifest
    except BaseException as exc:
        save(output / 'build.json', dict(state='FAIL', execution='NOT_RUN', rtl_executed=False,
                                        performance_measured=False, error=repr(exc)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--cc', type=Path, default=CC)
    parser.add_argument('--seal-ready', action='store_true')
    args = parser.parse_args()
    result = build(args.output, args.cc, seal_ready=args.seal_ready)
    print(json.dumps({k: result[k] for k in ('state', 'elf', 'elf_sha256', 'sdk_head')}))


if __name__ == '__main__':
    main()
