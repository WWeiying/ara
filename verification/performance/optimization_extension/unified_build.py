#!/usr/bin/env python3
"""Minimal successor to the reviewed unified builder and independent audit."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT_ROOT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
LIVE = Path('/home/wangwy/llama/llama.cpp')
BASE = OUT_ROOT / 'enablement_unified_build_20261111_01'
REV = '870cadb9f32c79df8d30ab845e4dd2e463a00540'
BASE_SHA = '4288144cb79ce2b53f058415442c9cb4091d9d47df676348c91fbeeb2e40a0fc'
AUDIT_SHA = '7490bca97ce7fffbd4dd3c368dc80d2e3db8eea36b59255d702cdebd394998f8'
TOOL = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')
CC, CXX = TOOL / 'riscv64-linux-gcc', TOOL / 'riscv64-linux-g++'
OVERLAYS = ('software/qbs/include/qbs/qbs.h', 'software/qbs/include/qbs/qbs_abi.h',
            'software/qbs/src/qbs_runtime.c', 'software/akv/src/akv_v2_native_riscv.c')
KEYS = ('cmake/ara-optimized.cmake', 'ggml/CMakeLists.txt', 'ggml/src/ggml-cpu/CMakeLists.txt',
        'ggml/src/ggml-cpu/repack.cpp', 'ggml/src/ggml-cpu/arch/riscv/qbs.cpp',
        'ggml/src/ggml-cpu/arch/riscv/qbs.h', 'ggml/src/ggml-cpu/arch/riscv/akv.cpp',
        'ggml/src/ggml-cpu/arch/riscv/resident.inc', 'ggml/src/ggml-cpu/arch/riscv/q8_K-m8.h',
        'ggml/src/ggml-cpu/arch/riscv/q8_K-m4-preflight.h')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Identity drift: ' + str(path))


def allowed_source(name):
    return not any(p in ('.git', '.cache', 'cache', '__pycache__', 'build') or
                   p.startswith(('build-', 'build_', 'cmake-build-')) for p in Path(name).parts)


def output(path):
    path = Path(path).absolute()
    require(path == path.resolve() and path.parent == OUT_ROOT and
            re.fullmatch(r'optimization_extension_unified_[A-Za-z0-9_]+', path.name), 'Fresh direct unified output required')
    return path


def ready_check(path, digest):
    require(re.fullmatch('[0-9a-f]{64}', digest or '') and sha(path) == digest, 'Parent READY receipt identity')
    receipt = read(path)
    require(receipt['state'] == 'READY' and receipt['sdk_revision'] == REV, 'Final parent READY required')
    require({'m4_k', 'm8_freeze'} <= set(receipt['gates']), 'Both short final gates required')
    for gate in receipt['gates'].values():
        target = Path(gate['path'])
        require(target.is_absolute() and target.is_relative_to(OUT_ROOT), 'Gate must be preserved OUT evidence')
        verify({str(target): gate['sha256']})
        result = read(target)
        require(result.get('state') and 'FAIL' not in result['state'] and
                result.get('post_pins_match', True) is True, 'Gate is not terminal checked evidence')
        if 'source_pins_sha256' in gate:
            verify({str(target.parent / 'source-pins.json'): gate['source_pins_sha256']})
    required = {str(ROOT / p) for p in OVERLAYS} | {str(LIVE / p) for p in KEYS}
    require(required <= set(receipt['source_pins']), 'READY lacks current key headers/overlays')
    verify(receipt['source_pins'])
    return receipt


def apply_overlays(out, root, sdk, pins, before):
    records = {}
    for name in OVERLAYS:
        source, dest = root / name, sdk / name
        old = out / 'inputs/overlay' / (Path(name).name + '.before')
        new = out / 'inputs/overlay' / (Path(name).name + '.after')
        shutil.copyfile(dest, old)
        shutil.copyfile(source, new)
        shutil.copyfile(new, dest)
        pins[str(source)] = sha(source)
        require(sha(source) == sha(new) == sha(dest), 'SDK overlay copy drift')
        diff = subprocess.run(['/usr/bin/diff', '-u', str(old), str(new)], capture_output=True)
        require(diff.returncode in (0, 1), 'Overlay diff failed')
        filename = 'panel4-overlay.diff' if name.endswith('akv_v2_native_riscv.c') else Path(name).name + '.diff'
        (out / filename).write_bytes(diff.stdout)
        pins[str(out / filename)] = sha(out / filename)
        records[name] = dict(source=str(source), before_sha256=sha(old), after_sha256=sha(new),
                             diff=str(out / filename), diff_sha256=sha(out / filename))
    after = {p.relative_to(sdk).as_posix(): sha(p) for p in sorted(sdk.rglob('*')) if p.is_file()}
    changed = [p for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
    require(set(changed) <= set(OVERLAYS) and before.keys() == after.keys(), 'Unexpected SDK delta')
    assembly = {p: h for p, h in before.items() if p.endswith(('.S', '.s'))}
    require(all(after[p] == h for p, h in assembly.items()), 'SDK assembly differs from pinned archive')
    save(out / 'sdk-manifest.json', after)
    save(out / 'overlay-manifest.json', dict(sdk_revision=REV, explicitly_overlaid=list(OVERLAYS),
        changed_paths=changed, overlays=records, asm_files=assembly, dirty_asm_excluded=True,
        panel_performance_accepted=False))


def replace(text, before, after):
    require(text.count(before) == 1, 'Reviewed template changed: ' + before[:90])
    return text.replace(before, after)


def derive_build(text, panel):
    text = replace(text, "REV = 'f50092f2d22238c6be4b6c159a1ad71a4ea68678'", 'REV = ' + repr(REV))
    text = replace(text, "PANEL = '7275cff381c45705e868c82626b4488080c79438b07d692d37646b6f29070122'", 'PANEL = ' + repr(panel))
    text = replace(text, "require(OUT.name == 'enablement_unified_build_20261111_01', 'Wrong output')",
                   "require(OUT.name.startswith('optimization_extension_unified_'), 'Wrong output')")
    text = replace(text, "{'unified_build.py'}, 'Preserve prior preparation/evidence'",
        "{'unified_build.py', 'unified_driver.py', 'unified_build_audit.py', 'parent-ready.json', 'derivation.json'}, 'Preserve prior preparation/evidence'")
    start = text.index("    for name, expected in (\n")
    end = text.index("    (OUT / 'inputs/overlay').mkdir", start)
    text = text[:start] + "    verify(read(OUT / 'parent-ready.json')['source_pins'])\n" + text[end:]
    start = text.index("    original = OUT / 'inputs/overlay/")
    end = text.index("    roots = ", start)
    text = text[:start] + '    apply_overlays(OUT, ROOT, SDK, pins, before)\n' + text[end:]
    text = replace(text, "name for name in names if name and\n", "name for name in names if name and allowed_source(name) and\n")
    text = replace(text, "archive = OUT / 'sdk-f50092f2.tar'", "archive = OUT / 'sdk-870cadb9.tar'")
    text = replace(text, "version.startswith('14.')", "version.startswith('14.3.')")
    text = replace(text, "ROOT / REL, PLATFORM / 'toolchain-rvv.cmake'):",
        "ROOT / REL, PLATFORM / 'toolchain-rvv.cmake', OUT / 'unified_driver.py', OUT / 'unified_build_audit.py', OUT / 'parent-ready.json', OUT / 'derivation.json'):")
    text = replace(text, "'-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=' + str(OUT / 'bin')],",
        "'-DGGML_RISCV_AKV_RESIDENT=OFF', '-DGGML_RISCV_AKV_PROVIDER_SOURCE:FILEPATH=',\n            '-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=' + str(BUILD / 'bin')],")
    text = replace(text, "elf = OUT / 'bin' / name", "elf = BUILD / 'bin' / name")
    text = text.replace("'-h', '-l', '-d', str(elf)", "'-h', '-l', '-d', '-A', str(elf)")
    text = replace(text, 'import time\n', 'import time\nfrom unified_driver import apply_overlays, allowed_source\n')
    compile(text, 'unified_build.py', 'exec')
    return text


def audit_extensions(m, pins, cc, compiled, cache):
    require('GGML_RISCV_AKV_RESIDENT:BOOL=OFF' in cache and
            'GGML_RISCV_AKV_PROVIDER_SOURCE:FILEPATH=\n' in cache, 'Resident/provider policy differs')
    by_source = {str(Path(row['file']).resolve()): row for row in cc}
    arch = m.LLAMA / 'ggml/src/ggml-cpu/arch/riscv'
    required = [m.SDK / 'software/qbs/src/qbs_runtime.c', arch / 'qbs.cpp',
        m.SDK / 'software/akv/src/akv_native_riscv.c', m.SDK / 'software/akv/src/akv_v2_native_riscv.c',
        m.SDK / 'software/akv/src/akv_v2_attention_rvv.S']
    actual = {}
    for source in required:
        row = by_source.get(str(source))
        require(row is not None, 'Required SDK/native source not compiled: ' + str(source))
        argv = row.get('arguments') or shlex.split(row['command'])
        obj = Path(row['directory']) / argv[argv.index('-o') + 1]
        dep = Path(str(obj) + '.d')
        require(obj.is_file() and (source.suffix == '.S' or dep.is_file()), 'Missing actual object/dependency: ' + str(obj))
        require('-DGGML_AKV_RESIDENT=1' not in argv and '-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1' not in argv,
                'Unexpected resident compile macro')
        m.pin(pins, obj)
        actual[str(source)] = dict(object=str(obj), object_sha256=m.sha(obj),
            dependency=str(dep) if dep.is_file() else None, argv=argv)
    runtime = m.SDK / 'software/qbs/src/qbs_runtime.c'
    row = by_source[str(runtime)]
    argv = row.get('arguments') or shlex.split(row['command'])
    at = argv.index('-o')
    argv = argv[:at] + argv[at + 2:]
    argv.remove('-c')
    for name, flags in (('cap5-macros', ['-E', '-dM']), ('cap5-preprocessed', ['-E', '-P'])):
        log = m.OUT / (name + '.log')
        with log.open('x') as stream:
            subprocess.run([*argv, *flags], cwd=row['directory'], stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
        m.pin(pins, log)
    macros = (m.OUT / 'cap5-macros.log').read_text()
    require(re.search(r'^#define QBS_COOPERATIVE_CAPABILITY_INDEX 5u$', macros, re.M) and
            re.search(r'^#define QBS_COOPERATIVE_Q4_K_BIT 0u$', macros, re.M), 'Compiled SDK cap5 ABI missing')
    preprocessed = (m.OUT / 'cap5-preprocessed.log').read_text()
    require(re.search(r'reader\(context,\s*5u\)', preprocessed) and
            'device->capabilities.q4_k_cooperative' in preprocessed, 'Compiled cap5 decoder missing')
    qbs_dep = Path(actual[str(arch / 'qbs.cpp')]['dependency']).read_text()
    require(str(arch / 'q8_K-m8.h') in qbs_dep, 'Actual M8 helper dependency missing')
    runtime_dep = Path(actual[str(runtime)]['dependency']).read_text()
    for header in ('qbs.h', 'qbs_abi.h'):
        require(str(m.SDK / 'software/qbs/include/qbs' / header) in runtime_dep, 'SDK capability header not consumed')
    fast_allowed = {str(arch / 'quant-kv.cpp')} | {str(m.SDK / ('software/akv/experimental/quantized_kv/' + p))
        for p in ('runtime.c', 'runtime_strided.c', 'register_pv/entry.c', 'prefill/ggml_entry.c')}
    modes = {}
    for row in cc:
        argv = row.get('arguments') or shlex.split(row['command'])
        source = str(Path(row['file']).resolve())
        require('-O3' in argv, 'Missing Release O3: ' + source)
        contracts = [p for p in argv if p.startswith('-ffp-contract=')]
        if contracts and contracts[-1] == '-ffp-contract=fast':
            require(source in fast_allowed, 'Unreviewed FP contraction: ' + source)
        modes[source] = dict(macros=[p for p in argv if p.startswith('-D')], fp_contract=contracts[-1] if contracts else None)
    for name in m.PROGRAMS:
        log = m.OUT / ('audit-' + name + '-readelf.log')
        text = log.read_text()
        require(re.search(r'Tag_RISCV_arch:.*_v\d+p\d+', text) and 'zfh' in text and 'zvfh' in text, 'Missing ELF RVV ISA attributes')
        m.pin(pins, log)
    save(m.OUT / 'compiled-capability-and-helpers.json', dict(capability_index=5, capability_bit=0,
        objects=actual, resident=False, provider=False, ordinary_native_akv_compiled=True,
        m8_helper_dependency=True, compile_modes=modes, functional_acceptance=False))
    m.pin(pins, m.OUT / 'compiled-capability-and-helpers.json')


def derive_audit(text):
    start = text.index("        m.require(original['state'] == 'FAIL'")
    end = text.index("        m.require(m.inventory(m.SDK)", start)
    text = text[:start] + "        m.require(original['state'] == 'FRESH_UNIFIED_LLAMA_BUILD_CHECKED_NOT_MODEL_EXECUTED', 'Original build did not finish')\n        m.require(all(row['returncode'] == 0 for row in commands), 'Build command failure')\n" + text[end:]
    text = replace(text, "        m.verify(pins)\n        m.save(OUT / 'compile-source-pins.json', pins)",
        "        audit_extensions(m, pins, cc, compiled, cache)\n        m.verify(pins)\n        m.save(OUT / 'compile-source-pins.json', pins)")
    text = replace(text, "original_failure='Post-build check used OUT/bin; actual CMake products are OUT/build/bin. No source/config/build retry.',", 'original_failure=None,')
    text = text.replace("'-h', '-l', '-d', str(elf)", "'-h', '-l', '-d', '-A', str(elf)")
    text = replace(text, 'import subprocess\n', 'import subprocess\nfrom unified_driver import audit_extensions\n')
    compile(text, 'unified_build_audit.py', 'exec')
    return text


def templates():
    verify({str(BASE / 'unified_build.py'): BASE_SHA, str(BASE / 'unified_build_audit.py'): AUDIT_SHA})
    return (BASE / 'unified_build.py').read_text(), (BASE / 'unified_build_audit.py').read_text()


def self_check():
    build, audit = templates()
    changed = derive_build(build, '0' * 64)
    derive_audit(audit)
    require("elf = BUILD / 'bin' / name" in changed and "elf = OUT / 'bin' / name" not in changed, 'Output path regression')
    require("--parallel', '8'" in changed and '-DGGML_RISCV_AKV_RESIDENT=OFF' in changed, 'Build policy regression')
    require(not allowed_source('ggml/build/cache/thing') and allowed_source('ggml/src/ggml-cpu/arch/riscv/q8_K-m8.h'), 'Snapshot exclusions')
    print(json.dumps(dict(state='BUILDER_READY_NOT_FROZEN', old_templates_verified=True,
        source_snapshot_created=False, model_executed=False, sdk_revision=REV, overlays=list(OVERLAYS))), flush=True)


def preflight(out):
    require(not out.exists(), 'Fresh preflight output required')
    out.mkdir()
    pins, commands = {}, []

    def query(label, argv, input_text=None):
        proc = subprocess.run(list(map(str, argv)), input=input_text, text=True, capture_output=True, check=True, timeout=60)
        (out / (label + '.log')).write_text(proc.stdout + proc.stderr)
        commands.append(dict(label=label, argv=list(map(str, argv)), returncode=proc.returncode))
        return proc.stdout.strip()

    version = query('gnu-version', [CXX, '-dumpfullversion'])
    require(version.startswith('14.3.'), 'GNU 14.3 Linux toolchain required')
    libraries = {}
    for name in ('libgcc.a', 'libgcc_eh.a', 'libstdc++.a', 'libc.a', 'libm.a', 'libpthread.a',
                 'libdl.a', 'librt.a', 'crt1.o', 'crti.o', 'crtn.o', 'crtbeginT.o', 'crtend.o'):
        path = Path(query(name, [CXX, '-print-file-name=' + name])).resolve(strict=True)
        require(path.is_file(), 'Missing static library: ' + name)
        libraries[name] = str(path)
        pins[str(path)] = sha(path)
    for driver, names in ((CC, ('cc1', 'as', 'ld')), (CXX, ('cc1plus', 'collect2'))):
        pins[str(driver)] = sha(driver)
        for name in names:
            value = query('tool-' + name, [driver, '-print-prog-name=' + name])
            path = Path(value) if '/' in value else Path(shutil.which(value) or value)
            pins[str(path.resolve(strict=True))] = sha(path)
    for path in ('/usr/bin/python3.11', '/usr/bin/cmake', '/usr/bin/gmake', '/usr/bin/git',
                 str(TOOL / 'riscv64-linux-readelf'), str(TOOL / 'riscv64-linux-nm')):
        pins[path] = sha(path)
    macros = query('rvv-preprocessor', [CXX, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-dM', '-E', '-x', 'c++', '-'], '')
    require(all('#define ' + name + ' ' in macros for name in ('__riscv_vector', '__riscv_zfh', '__riscv_zvfh')), 'Compiler lacks required RVV ISA')
    save(out / 'commands.json', commands)
    save(out / 'tool-library-pins.json', pins)
    save(out / 'preflight.json', dict(state='TOOLS_AND_LIBRARIES_CHECKED_NOT_FROZEN', version=version,
        libraries=libraries, target_compiled=False, source_snapshot_created=False, sdk_archived=False,
        tool_pins_sha256=sha(out / 'tool-library-pins.json')))
    print(json.dumps(read(out / 'preflight.json')), flush=True)


def prepare(out, receipt_path, receipt_sha, launch):
    receipt = ready_check(receipt_path, receipt_sha)
    require(not out.exists(), 'Preserve every prior unified attempt')
    build, audit = templates()
    derived = derive_build(build, receipt['source_pins'][str(ROOT / OVERLAYS[-1])])
    derived_audit = derive_audit(audit)
    out.mkdir()
    shutil.copyfile(__file__, out / 'unified_driver.py')
    shutil.copyfile(receipt_path, out / 'parent-ready.json')
    (out / 'unified_build.py').write_text(derived)
    (out / 'unified_build_audit.py').write_text(derived_audit)
    save(out / 'derivation.json', dict(base_builder=str(BASE / 'unified_build.py'), base_sha256=BASE_SHA,
        base_audit=str(BASE / 'unified_build_audit.py'), audit_sha256=AUDIT_SHA,
        changes=['Fixed SDK HEAD + four explicit overlays, archive-only ASM', 'Parent READY source pins',
                 'OUT/build/bin products', 'Resident OFF, no provider', 'SDK cap5/M8 dependencies and RVV ELF audit'],
        parent_ready_source=str(receipt_path), parent_ready_sha256=receipt_sha))
    subprocess.run(['/usr/bin/python3.11', '-B', str(out / 'unified_build.py'), 'prepare'], cwd=out, check=True)
    pins = read(out / 'source-pins.json')
    pins.update(receipt['source_pins'])
    pins[str(receipt_path)] = receipt_sha
    pins[str(Path(__file__).resolve())] = sha(__file__)
    for gate in receipt['gates'].values():
        pins[gate['path']] = gate['sha256']
    verify(pins)
    (out / 'source-pins.json').write_text(json.dumps(pins, indent=2, sort_keys=True) + '\n')
    review = sha(out / 'source-pins.json')
    cmd = ['/usr/bin/systemd-run', '--user', '--unit=' + unit(out), '--property=Type=exec',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), '/usr/bin/python3.11', '-B', '-u',
        str(out / 'unified_driver.py'), 'execute', '--output', str(out), '--review-sha256', review]
    save(out / 'launch-command.json', cmd)
    print(json.dumps(dict(state='PREPARED_NOT_COMPILED', output=str(out), review_sha256=review, command=cmd)), flush=True)
    if launch:
        subprocess.run(cmd, check=True)


def unit(out):
    return 'optimization-extension-unified-' + out.name + '.service'


def execute(out, review):
    require(Path(__file__).resolve() == out / 'unified_driver.py' and sha(out / 'source-pins.json') == review and
            not (out / 'attempt.json').exists(), 'Frozen one-attempt worker required')
    group = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit(out), '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit(out) in group and owner == str(os.getpid()), 'Direct systemd MainPID required')
    save(out / 'attempt.json', dict(main_pid=os.getpid(), unit=unit(out), cgroup=group, review_sha256=review))
    report = dict(state='FAIL', model_executed=False, native_vcs_pass_claimed=False,
                  rtl_performance_accepted=False, functional_acceptance=False, automatic_retry=False)
    try:
        verify(read(out / 'source-pins.json'))
        for argv in (['/usr/bin/python3.11', '-B', str(out / 'unified_build.py'), 'execute', '--review-sha256', review],
                     ['/usr/bin/python3.11', '-B', str(out / 'unified_build_audit.py')]):
            proc = subprocess.Popen(argv, cwd=out)
            try:
                require(proc.wait() == 0, 'Unified build/audit child failed')
            except BaseException:
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise
        audit = read(out / 'build-audit.json')
        require(audit['state'] == 'FRESH_UNIFIED_LLAMA_BUILD_INDEPENDENTLY_CHECKED_NOT_MODEL_EXECUTED', 'Independent build audit failed')
        images = {r['path']: r['sha256'] for r in audit['programs'].values()}
        for path in (out / 'build').rglob('*.a'):
            images[str(path)] = sha(path)
        verify(images)
        verify(read(out / 'source-pins.json'))
        verify(read(out / 'compile-source-pins.json'))
        save(out / 'image-pins.json', images)
        report.update(state='BUILT_NOT_MODEL_OR_RTL_PERFORMANCE_ACCEPTANCE', programs=audit['programs'],
            source_pins_sha256=review, image_pins_sha256=sha(out / 'image-pins.json'),
            audit_sha256=sha(out / 'build-audit.json'), source_and_image_pins_match=True,
            resident=False, provider_supplied=False, sdk_revision=REV)
    except BaseException as exc:
        report['error'] = repr(exc)
    save(out / 'delivery.json', report)
    print(json.dumps(report), flush=True)
    return int(report['state'] == 'FAIL')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('self-check', 'preflight', 'prepare', 'execute'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--ready-receipt', type=Path)
    parser.add_argument('--ready-sha256')
    parser.add_argument('--review-sha256')
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    if args.action == 'self-check':
        self_check()
        return 0
    out = output(args.output)
    if args.action == 'preflight':
        preflight(out)
    elif args.action == 'prepare':
        require(args.ready_receipt is not None, 'Parent READY required before any snapshot')
        prepare(out, args.ready_receipt, args.ready_sha256, args.launch)
    else:
        return execute(out, args.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(main())
