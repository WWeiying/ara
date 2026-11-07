#!/usr/bin/env python3
"""One-member production-library Norm integration, checked by full native-model logits."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from audit import digest, require
from build_trace_context_library import Build, write, archive_members, dependencies
from build_sdk_dispatch_library import compare_member_archives
from audit_sdk_guest_payload import validate_payload
from sdk_dispatch_model import HERE, ROOT, RUNS, PRIOR, MODEL, read, recipe, relink, guest_listing, accepted_inputs
from rms_ggml_model import driver, check

LATEST = RUNS/'e2e_sdk_dispatch_model_pair_20261106_01'
RECEIPT = ROOT/'verification/performance/evidence/sdk_dispatch_model_20261106_01/result.json'
RECEIPT_SHA = '5e24427b0d8e8510259d5771f2fd169034f738b8fdd131aef0e9d8ac1f925dcd'
BASE_ELF = 'f0d8741421d95b08057973f58d370b9fc48c4325b08e909b299946e175dfcaad'
GUARDS = RUNS/'e2e_rms_ggml_runtime_20261106_02'


def run(output, library_root, execute):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole verification output required')
    out.mkdir(parents=True, exist_ok=False)
    b = Build(out)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, performance_measured=False,
                 rtl_changed=False, production_library_promoted=False, compiled_translation_units=0,
                 common_model_object_reused=True, default_enabled=False)

    def save():
        write(out/'status.json', state)

    def binary(argv, label, destination, bound):
        argv = list(map(str, argv)); b.pin(argv[0]); b.verify()
        row = dict(label=label, argv=argv, timeout_seconds=bound, environment=b.environment)
        b.commands.append(row); write(out/'commands.json', b.commands)
        state['state'] = label.upper()
        with destination.open('xb') as stream, (out/(label+'.stderr')).open('xb') as err:
            child = subprocess.Popen(argv, cwd=out, env=b.environment, stdout=stream, stderr=err)
            state['child_pid'] = child.pid; save()
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                child.kill(); child.wait(); raise
            finally:
                state['child_pid'] = None; save()
        row['returncode'] = code; write(out/'commands.json', b.commands)
        require(code == 0, label+' failed'); b.verify()

    try:
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE):
                b.pin(path)
        b.pin(HERE/'test_rms_ggml_model.py')
        b.pin(GUARDS/'result.json'); guards = read(GUARDS/'result.json')
        require(guards['state'] == 'RMS_GGML_RUNTIME_HOST_AND_SPIKE_FUNCTIONAL_PASS' and
                guards['marker'] == 'RMS_GGML_RUNTIME_PASS cases=90 aliases=30 rejected=7 modes=5 exact=1 flags=1' and
                guards['post_pins_match'], 'Actual frozen wrapper guard/alias/rounding acceptance required')
        b.pin(GUARDS/'source-pins.json', guards['source_pins_sha256'])
        for path, sha in read(GUARDS/'source-pins.json').items():
            b.pin(path, sha)
        for path, sha in guards['artifacts'].items():
            b.pin(path, sha)
        _, old, baseline_library, _ = accepted_inputs(b.pin)
        b.pin(RECEIPT, RECEIPT_SHA); receipt = read(RECEIPT)
        require(receipt['state'] == 'SDK_DISPATCH_QWEN3_MODEL_PAIR_REAUDITED' and
                receipt['candidate_library_sha256'] == baseline_library['candidate_library_sha256'],
                'Latest native model/library acceptance required')
        b.pin(Path(receipt['run'])/'result.json', receipt['result_sha256'])
        b.pin(LATEST/'result.json', receipt['worker_result_sha256']); latest = read(LATEST/'result.json')
        require(latest['state'] == 'SDK_DISPATCH_MODEL_PAIR_FUNCTIONAL_PASS' and
                latest['candidate_elf_sha256'] == BASE_ELF, 'Latest model executable identity')
        b.pin(LATEST/'source-pins.json', receipt['source_pins_sha256'])
        latest_pins = read(LATEST/'source-pins.json')
        for path, sha in latest['artifacts'].items():
            b.pin(path, sha)
        original = recipe(read(LATEST/'commands.json'), 'link-candidate')
        base = Path(baseline_library['candidate_library'])
        library_root = library_root.resolve(strict=True)
        require(library_root.is_relative_to(RUNS), 'Isolated library required')
        b.pin(library_root/'result.json'); library = read(library_root/'result.json')
        require(library['state'] == 'RMS_GGML_LIBRARY_BUILT_ARCHIVE_VERIFIED' and
                library['baseline_library_sha256'] == digest(base) and library['member'] == 'ops.cpp.o' and
                library['unchanged_other_members'] == 31 and library['members'] == 32 and
                library['original_object_reproduced_exactly'] and library['public_exports_unchanged'] and
                not library['target_executed'] and not library['performance_measured'] and
                not library['production_library_promoted'], 'Norm isolated archive acceptance required')
        b.pin(library_root/'source-pins.json', library['source_pins_sha256'])
        for path, sha in read(library_root/'source-pins.json').items():
            b.pin(path, sha)
        for path, sha in library['artifacts'].items():
            require(Path(path).is_relative_to(library_root), 'Escaping library artifact')
            b.pin(path, sha)
        for path, target in read(library_root/'path-identities.json').items():
            require(str(Path(path).resolve(strict=True)) == target, 'Library symlink drift')
        candidate = Path(library['candidate_library']); b.pin(candidate, library['candidate_library_sha256'])
        member = Path(library['candidate_object']); b.pin(member, library['candidate_object_sha256'])
        require(compare_member_archives(archive_members(base.read_bytes()), archive_members(candidate.read_bytes()),
                    'ops.cpp.o', member.read_bytes()) == read(library_root/'archive-members.json'),
                'Only accepted ops member may change')
        model_object = PRIOR/'model.o'; b.pin(model_object, latest['common_model_object_sha256'])
        compiler = Path(original[0]); b.pin(compiler, old[str(compiler.resolve())])
        real = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-g++.br_real')
        b.pin(real); b.tool_libraries(real, 'compiler')
        for name in ('cc1plus', 'as', 'collect2', 'ld'):
            path = Path(b.run([compiler, '-print-prog-name='+name], 'locate-'+name).strip())
            require(path.is_absolute(), 'Unresolved compiler/linker tool')
            b.pin(path, old.get(str(path.resolve()))); b.tool_libraries(path, name)
        for token in original:
            if token.endswith('.a'):
                b.pin(token, latest_pins[str(Path(token).resolve())])
        for name in ('libc.a', 'libstdc++.a', 'libm.a', 'libgcc.a', 'libgcc_eh.a', 'libpthread.a', 'libdl.a',
                     'crt1.o', 'crti.o', 'crtbeginT.o', 'crtend.o', 'crtn.o'):
            path = Path(b.run([compiler, '-print-file-name='+name], 'locate-'+name).strip())
            b.pin(path, old[str(path.resolve())])
        for label, target, archive in (('reproduce-baseline', 'baseline-reproduced', base),
                                       ('link-candidate', 'candidate', candidate)):
            argv = relink(original, model_object, base, archive, LATEST/'candidate', out/target)
            b.run(argv, label, bound=300)
            b.pin(out/target, BASE_ELF if target == 'baseline-reproduced' else None)
        source = HERE/'trace_context_model_driver.cpp'; b.pin(source)
        new_source = out/'inputs/rms_model_driver.cpp'; new_source.write_text(driver(source.read_text())); b.pin(new_source)
        compile_driver = recipe(read(PRIOR/'commands.json'), 'compile-driver')
        compile_driver[compile_driver.index('-c')+1] = str(new_source)
        compile_driver[compile_driver.index('-o')+1] = str(out/'objects/driver.o')
        dep_command = [token for i, token in enumerate(compile_driver) if i not in
                       (compile_driver.index('-c'), compile_driver.index('-o'), compile_driver.index('-o')+1)]
        for path in dependencies(b.run([*dep_command, '-M', '-MT', 'object'], 'driver-dependencies'), out):
            if path != new_source:
                require(str(path) in old, 'New driver compiler dependency requires review: '+str(path))
                b.pin(path, old[str(path)])
        b.run(compile_driver, 'compile-driver', bound=120); b.pin(out/'objects/driver.o')
        b.run([compiler, '-static', out/'objects/driver.o', '-lm', '-o', out/'test'], 'link-driver', bound=120)
        b.pin(out/'test')
        entries = [line.split() for line in (LATEST/'initramfs.list').read_text().splitlines()]
        initializers = [Path(p[2]) for p in entries if len(p) == 6 and p[:2] == ['file', '/init']]
        require(len(initializers) == 1, 'Guest init identity'); init = initializers[0]
        b.pin(init, old[str(init.resolve())])
        (out/'initramfs.list').write_text(guest_listing(init, LATEST/'candidate', out/'candidate', out/'test'))
        b.pin(out/'initramfs.list')
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        b.pin(cpio, old[str(cpio.resolve())]); b.tool_libraries(cpio, 'cpio')
        binary([cpio, out/'initramfs.list'], 'make-initramfs', out/'initramfs.cpio', 60); b.pin(out/'initramfs.cpio')
        payload = validate_payload((out/'initramfs.cpio').read_bytes(), {
            'init': init.read_bytes(), 'base': (LATEST/'candidate').read_bytes(),
            'candidate': (out/'candidate').read_bytes(), 'test': (out/'test').read_bytes()})
        write(out/'guest-payload.json', payload); b.pin(out/'guest-payload.json')
        qemu = recipe(read(LATEST/'commands.json'), 'qemu')
        require(qemu.count('-initrd') == 1 and qemu[qemu.index('-initrd')+1] == str(LATEST/'initramfs.cpio') and
                'xaraqbs=true' in qemu[qemu.index('-cpu')+1] and qemu[qemu.index('-smp')+1] == '1' and
                'readonly=on' in qemu[qemu.index('-drive')+1], 'Native single-hart readonly execution required')
        qemu[qemu.index('-initrd')+1] = str(out/'initramfs.cpio')
        disk = Path(qemu[qemu.index('-drive')+1].split(',', 1)[0].removeprefix('file='))
        for path in (Path(qemu[0]), disk, Path(qemu[qemu.index('-bios')+1]), Path(qemu[qemu.index('-kernel')+1])):
            b.pin(path, old[str(path.resolve())])
        b.tool_libraries(qemu[0], 'qemu')
        b.pin(MODEL/'qemu.log', old[str(MODEL/'qemu.log')])
        sys.path.insert(0, str(ROOT/'verification/qbs'))
        from run_ggml_segmented import verify_native_build
        b.pin(ROOT/'verification/qbs/run_ggml_segmented.py')
        for path in verify_native_build(Path(qemu[0])):
            b.pin(path, old[str(Path(path).resolve())])
        b.verify(); write(out/'source-pins.json', b.pins); write(out/'path-identities.json', b.identities)
        state.update(state='RMS_GGML_MODEL_PAIR_PREPARED_NOT_EXECUTED', library_build=str(library_root),
            baseline_library_sha256=digest(base), candidate_library_sha256=digest(candidate),
            baseline_elf_sha256=BASE_ELF, candidate_elf_sha256=digest(out/'candidate'),
            driver_elf_sha256=digest(out/'test'), common_model_object_sha256=digest(model_object),
            guest_cpio_parsed_and_bound=True, wrapper_guard_result_sha256=digest(GUARDS/'result.json'),
            baseline_link_reproduced_exactly=True, compiled_translation_units=1,
            source_pins_sha256=digest(out/'source-pins.json')); save()
        if execute:
            binary(qemu, 'qemu', out/'qemu.log', 7200)
            measured = check((out/'qemu.log').read_text(), (MODEL/'qemu.log').read_text(), read(PRIOR/'projection-schema.json'))
            require(measured['native'] == latest['measured'], 'Existing QBS/AKV native work changed')
            b.verify(); state.update(state='RMS_GGML_MODEL_PAIR_FUNCTIONAL_PASS', measured=measured,
                                      log_sha256=digest(out/'qemu.log'), post_pins_match=True)
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc)); raise
    finally:
        save(); write(out/'source-pins.json', b.pins); write(out/'path-identities.json', b.identities)
        write(out/'commands.json', b.commands); state['source_pins_sha256'] = digest(out/'source-pins.json')
        state['artifacts'] = {str(p): digest(p) for p in out.rglob('*') if p.is_file() and
            p.name not in ('result.json', 'status.json') and 'tmp' not in p.relative_to(out).parts}
        write(out/'result.json', state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--execute-reviewed', action='store_true')
    def stop(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    args = parser.parse_args(); run(args.output, args.library, args.execute_reviewed)
