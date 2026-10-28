#!/usr/bin/env python3
"""Stage and compile the production-shaped delta without touching live sources."""
import argparse
import difflib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
LIVE = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu')
PUBLIC = ROOT / 'software/qbs/ggml'
REPAIR = HERE.parents[1] / 'packed_stride'
RUNTIME = ROOT / 'verification/out/m4-prepared-installed-build-20261027-01'
ACTIVE = ROOT / 'verification/out/m4-packed-qkv-vcs-20261027-01/source-pins.json'
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Reviewed source structure changed: ' + old[:120])
    return text.replace(old, new)


def transform(repack, controller):
    # Reuse the accepted address repair, not a second implementation of it.
    sys.path.insert(0, str(REPAIR))
    spec = importlib.util.spec_from_file_location('accepted_stride_repair', REPAIR / 'repair.py')
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)
    repack = repair.transform(repack)
    repack = once(repack, '#include "strided_input.h"', '#include "arch/riscv/qbs-strided-input.h"')
    repack = once(repack, '#include "arch/riscv/q8_K-m4.h"', '#include "arch/riscv/q8_K-m4-packed.h"')
    repack = once(repack, 'vector_used = ggml_riscv_q8_K_m4::quantize(x, vy, n_per_row);',
                  'vector_used = ggml_riscv_q8_K_m4_packed::selected_quantize(x, vy, n_per_row);')
    trace = '''        std::fprintf(stderr, "GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=%d path=%s k=%lld\\n",
                     int(enabled), vector_used ? "rvv" : "generic", (long long) n_per_row);'''
    repack = once(repack, trace, trace + '''
        std::fprintf(stderr, "GGML_RISCV_QBS_M4_SELECTED source=direct tag=%u path=%s k=%lld\\n",
                     enabled ? ggml_riscv_q8_K_m4_packed::producer_tag() : 0u,
                     vector_used ? "rvv" : "generic", (long long)n_per_row);''')
    controller = once(controller, '#include "q8_K-m4.h"', '#include "q8_K-m4-packed.h"')
    controller = once(controller, 'identity.producer_tag=1;',
                      'identity.producer_tag=ggml_riscv_q8_K_m4_packed::producer_tag();')
    controller = once(controller, 'ggml_riscv_q8_K_m4::quantize<16>(input,output,k)',
                      'ggml_riscv_q8_K_m4_packed::selected_quantize(input,output,k)')
    trace = '''        if(trace) std::fprintf(stderr,"GGML_RISCV_QBS_M4_CACHE epoch=%llu group=%lld event=%s fill=%d\\n",
            (unsigned long long)epoch,(long long)group,event,int(policy.fill));'''
    controller = once(controller, trace, trace + '''
        if(trace) std::fprintf(stderr,"GGML_RISCV_QBS_M4_SELECTED source=cache tag=%u event=%s k=%lld\\n",
            identity.producer_tag,event,(long long)k);''')
    return repack, controller


def files():
    repack, controller = transform((LIVE / 'repack.cpp').read_text(),
                                  (PUBLIC / 'q8_K-prepared-reuse.h').read_text())
    return {
        Path('repack.cpp'): repack,
        Path('arch/riscv/q8_K-prepared-reuse.h'): controller,
        Path('arch/riscv/q8_K-m4-packed.h'): (PUBLIC / 'q8_K-m4-packed.h').read_text(),
        Path('arch/riscv/qbs-strided-input.h'): (REPAIR / 'strided_input.h').read_text(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out') or out.exists():
        raise ValueError('Fresh independent output required')
    pins = json.loads((RUNTIME / 'manifest.json').read_text())
    if json.loads((RUNTIME / 'result.json').read_text())['state'] != 'PASS':
        raise ValueError('Normal library prerequisite')
    active = json.loads(ACTIVE.read_text())
    for path, value in active.items():
        if path in pins and pins[path] != value:
            raise ValueError('Conflicting source inventories: ' + path)
        pins[path] = value
    accepted = [
        ROOT / 'verification/out/m4-packed-canonical-20261027-02/result.json',
        ROOT / 'verification/out/m4-packed-stride-repair-20261027-01/result.json',
        ROOT / 'verification/out/m4-stride-expanded-20261027-01/acceptance-result.json',
    ]
    for report in accepted:
        if json.loads(report.read_text())['state'] != 'PASS':
            raise ValueError('Missing functional qualification: ' + str(report))
    pins.update(hashes([*accepted, ACTIVE, Path(__file__), REPAIR / 'repair.py',
                       REPAIR / 'strided_input.h', *PUBLIC.glob('*.h')]))
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Sealed prerequisites changed')
    if (PUBLIC / 'q8_K-prepared-reuse.h').read_bytes() != (LIVE / 'arch/riscv/q8_K-prepared-reuse.h').read_bytes():
        raise ValueError('Live and canonical cache controller differ')
    generated = files()
    out.mkdir(parents=True)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None,
                 installed=False, rtl_changed=False, performance_measured=False)

    def run(command, label, cwd):
        atomic_json(out / (label + '.command.json'), dict(argv=command, cwd=str(cwd)))
        with (out / (label + '.log')).open('x') as log:
            with subprocess.Popen(command, cwd=cwd, stdout=log, stderr=log) as process:
                state.update(state=label.upper(), child_pid=process.pid)
                atomic_json(out / 'status.json', state)
                try:
                    code = process.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise
        atomic_json(out / (label + '.exit.json'), dict(returncode=code))
        if code:
            raise RuntimeError(label + ' failed')

    try:
        src = out / 'src'
        headers = src / 'arch/riscv'
        headers.mkdir(parents=True)
        # Unmodified shared dependencies accompany the patch only for this
        # isolated compile; they are not additional production changes.
        for header in PUBLIC.glob('*.h'):
            (headers / header.name).write_bytes(header.read_bytes())
        patch = []
        for relative, text in generated.items():
            target = src / relative
            target.write_text(text)
            original = LIVE / relative
            prefix = 'ggml/src/ggml-cpu/' + str(relative)
            before = original.read_text() if original.exists() else ''
            patch.extend(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
                         fromfile='a/' + prefix if original.exists() else '/dev/null', tofile='b/' + prefix))
        (out / 'integration.patch').write_text(''.join(patch))
        pins.update(hashes([*src.rglob('*.h'), src / 'repack.cpp', out / 'integration.patch']))
        records = json.loads((RUNTIME / 'build/compile_commands.json').read_text())
        record, = [row for row in records if Path(row['file']).resolve() == LIVE / 'repack.cpp']
        command = shlex.split(record['command'])
        command[command.index('-c') + 1] = str(src / 'repack.cpp')
        command[command.index('-o') + 1] = str(out / 'repack.o')
        for flag, suffix in (('-MF', 'd'), ('-MT', 'o')):
            if flag in command:
                command[command.index(flag) + 1] = str(out / ('repack.' + suffix))
        command += ['-iquote', str(LIVE), '-I' + str(headers)]
        atomic_json(out / 'manifest.json', pins)
        run(command, 'compile', record['directory'])
        # Parse ordinary runtime templates too, with QBS disabled. This is not
        # execution coverage for a QBS-free runtime or a different ISA target.
        disabled = list(command) + ['-UGGML_USE_RISCV_QBS', '-fsyntax-only']
        for flag in ('-o', '-MF', '-MT'):
            if flag in disabled:
                index = disabled.index(flag)
                del disabled[index:index+2]
        disabled = [arg for arg in disabled if arg not in ('-MD', '-MMD')]
        run(disabled, 'qbs-disabled-syntax', record['directory'])
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Inputs changed during private compile')
        pins.update(hashes([out / 'repack.o']))
        atomic_json(out / 'manifest.json', pins)
        state.update(state='COMPILE_ONLY_PASS', qbs_disabled_syntax='PASS',
                     patch_sha256=digest(out / 'integration.patch'),
                     scope='Private combined production-shaped object; no installation or execution claim')
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        atomic_json(out / 'status.json', state)
        atomic_json(out / 'result.json', state)


if __name__ == '__main__':
    main()
