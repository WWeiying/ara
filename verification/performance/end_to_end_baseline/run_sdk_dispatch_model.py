#!/usr/bin/env python3
"""Relink one isolated GGML archive and execute the accepted full-logit driver."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from audit import digest, require
from build_trace_context_library import Build, write
from sdk_dispatch_model import HERE, ROOT, RUNS, PRIOR, LIBRARY, MODEL, read, recipe, relink, guest_listing, accepted_inputs
from trace_context_model import check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-reviewed', action='store_true')
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole verification output required')
    out.mkdir(parents=True, exist_ok=False)
    build = Build(out)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, performance_measured=False,
                 rtl_changed=False, production_sdk_changed=False, model_library_promoted=False,
                 compiled_translation_units=0, reused_model_driver=True)

    def save():
        write(out / 'status.json', state)

    def run_binary(argv, label, destination, bound):
        argv = list(map(str, argv))
        build.pin(argv[0])
        build.verify()
        record = dict(label=label, argv=argv, cwd=str(out), environment=build.environment, timeout=bound)
        build.commands.append(record)
        write(out / 'commands.json', build.commands)
        state['state'] = label.upper()
        with destination.open('xb') as output, (out / (label + '.stderr')).open('xb') as errors:
            child = subprocess.Popen(argv, cwd=out, env=build.environment, stdout=output, stderr=errors)
            state['child_pid'] = child.pid
            save()
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                child.kill()
                child.wait()
                raise
            finally:
                state['child_pid'] = None
                save()
        record['returncode'] = code
        write(out / 'commands.json', build.commands)
        require(code == 0, label + ' failed')
        build.verify()

    save()
    try:
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE):
                build.pin(path)
        build.pin(HERE / 'test_sdk_dispatch_model.py')
        prior, old, library, expected_work = accepted_inputs(build.pin)
        original = recipe(read(PRIOR / 'commands.json'), 'link-candidate')
        baseline_library = Path(library['baseline_library'])
        candidate_library = Path(library['candidate_library'])
        link = relink(original, PRIOR / 'model.o', baseline_library, candidate_library,
                      PRIOR / 'candidate', out / 'candidate')
        require('-static' in link, 'Static link required')
        for token in original:
            if token.endswith('.a') and token != str(baseline_library):
                build.pin(token, old[str(Path(token).resolve())])
        compiler = Path(link[0])
        build.pin(compiler, old[str(compiler.resolve())])
        # The wrapper resolves to a shared binary; the g++ sibling is its actual child.
        lexical_real = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-g++.br_real')
        require(lexical_real.is_file(), 'Missing accepted C++ compiler executable')
        build.pin(lexical_real)
        build.tool_libraries(lexical_real, 'compiler')
        for name in ('collect2', 'ld'):
            tool = Path(build.run([compiler, '-print-prog-name=' + name], 'locate-' + name).strip())
            require(tool.is_absolute(), 'Unresolved linker subprogram')
            build.pin(tool)
            build.tool_libraries(tool, name)
        for name in ('libc.a', 'libstdc++.a', 'libm.a', 'libgcc.a', 'libgcc_eh.a', 'libpthread.a', 'libdl.a',
                     'crt1.o', 'crti.o', 'crtbeginT.o', 'crtend.o', 'crtn.o'):
            path = Path(build.run([compiler, '-print-file-name=' + name], 'locate-' + name).strip())
            require(path.is_absolute(), 'Unresolved link input')
            build.pin(path, old[str(path.resolve())])
        baseline_link = relink(original, PRIOR / 'model.o', baseline_library, baseline_library,
                               PRIOR / 'candidate', out / 'baseline-reproduced')
        build.run(baseline_link, 'link-reproduce-baseline', bound=300)
        build.pin(out / 'baseline-reproduced', prior['candidate_elf_sha256'])
        build.run(link, 'link-candidate', bound=300)
        build.pin(out / 'candidate')
        init_lines = [line.split() for line in (PRIOR / 'initramfs.list').read_text().splitlines()]
        matches = [Path(words[2]) for words in init_lines if len(words) == 6 and words[:2] == ['file', '/init']]
        require(len(matches) == 1, 'Prior init identity')
        init = matches[0]
        build.pin(init, old[str(init.resolve())])
        listing = guest_listing(init, PRIOR / 'candidate', out / 'candidate', PRIOR / 'test')
        write_path = out / 'initramfs.list'
        write_path.write_text(listing)
        build.pin(write_path)
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        build.pin(cpio, old[str(cpio.resolve())])
        build.tool_libraries(cpio, 'cpio')
        run_binary([cpio, write_path], 'make-initramfs', out / 'initramfs.cpio', 60)
        build.pin(out / 'initramfs.cpio')
        qemu = recipe(read(PRIOR / 'commands.json'), 'qemu')
        require(qemu.count('-initrd') == 1 and qemu[qemu.index('-initrd') + 1] == str(PRIOR / 'initramfs.cpio') and
                'xaraqbs=true' in qemu[qemu.index('-cpu') + 1] and
                qemu[qemu.index('-smp') + 1] == '1' and
                'readonly=on' in qemu[qemu.index('-drive') + 1], 'Native single-hart read-only model required')
        qemu[qemu.index('-initrd') + 1] = str(out / 'initramfs.cpio')
        disk = Path(qemu[qemu.index('-drive') + 1].split(',', 1)[0].removeprefix('file='))
        for path in (Path(qemu[0]), disk, Path(qemu[qemu.index('-bios') + 1]), Path(qemu[qemu.index('-kernel') + 1])):
            build.pin(path, old[str(path.resolve())])
        build.tool_libraries(qemu[0], 'qemu')
        build.pin(MODEL / 'qemu.log', old[str(MODEL / 'qemu.log')])
        sys.path.insert(0, str(ROOT / 'verification/qbs'))
        from run_ggml_segmented import verify_native_build
        build.pin(ROOT / 'verification/qbs/run_ggml_segmented.py')
        # Seal emulator provenance once after linking; do not hash this large tree per link query.
        for path in verify_native_build(Path(qemu[0])):
            build.pin(path, old[str(Path(path).resolve())])
        build.verify()
        write(out / 'source-pins.json', build.pins)
        write(out / 'path-identities.json', build.identities)
        state.update(state='SDK_DISPATCH_MODEL_PAIR_PREPARED_NOT_EXECUTED',
            source_pins_sha256=digest(out / 'source-pins.json'), library_build=str(LIBRARY),
            baseline_library_sha256=library['baseline_library_sha256'],
            candidate_library_sha256=library['candidate_library_sha256'],
            common_model_object_sha256=digest(PRIOR / 'model.o'),
            baseline_elf_sha256=digest(PRIOR / 'candidate'), candidate_elf_sha256=digest(out / 'candidate'),
            driver_elf_sha256=digest(PRIOR / 'test'), prior_model_worker=str(PRIOR))
        state['baseline_link_reproduced_exactly'] = True
        state['newly_inventoried_tool_inputs'] = [str(lexical_real.resolve()),
                                                 str(ROOT / 'verification/qbs/run_ggml_segmented.py')]
        save()
        if args.execute_reviewed:
            run_binary(qemu, 'qemu', out / 'qemu.log', 7200)
            measured = check((out / 'qemu.log').read_text(), (MODEL / 'qemu.log').read_text(),
                             read(PRIOR / 'projection-schema.json'))
            require(measured == expected_work, 'Model/native work differs from accepted prior pair')
            build.verify()
            state.update(state='SDK_DISPATCH_MODEL_PAIR_FUNCTIONAL_PASS', measured=measured,
                         log_sha256=digest(out / 'qemu.log'), post_pins_match=True)
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        save()
        write(out / 'source-pins.json', build.pins)
        write(out / 'path-identities.json', build.identities)
        write(out / 'commands.json', build.commands)
        state['source_pins_sha256'] = digest(out / 'source-pins.json')
        state['artifacts'] = {str(p): digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('result.json', 'status.json')}
        write(out / 'result.json', state)


if __name__ == '__main__':
    main()
