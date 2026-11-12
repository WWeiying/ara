#!/usr/bin/env python3
"""Check portable receipts, unchanged math/entry, and the existing provider oracle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
ARCH = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def span(text, start, end):
    first = text.index(start)
    return text[first:text.index(end, first)]


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--host', required=True, type=Path)
    parser.add_argument('--spike', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and
            re.fullmatch(r'enablement_portable_[A-Za-z0-9_-]+', out.name) and not out.exists(), 'Fresh portable output required')
    out.mkdir()
    host, spike = args.host.resolve(), args.spike.resolve()
    pins, commands = {}, []
    report = dict(state='FAIL', model_executed=False, native_execution=False,
                  performance_measured=False, rtl_execution=False, fpga_acceptance=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GGML_', 'AKV_'))}
    env.update(LC_ALL='C', LANG='C')

    def pin(path):
        path = Path(path).resolve()
        digest = sha(path)
        require(str(path) not in pins or pins[str(path)] == digest, 'Input drift: ' + str(path))
        pins[str(path)] = digest

    def receipt(directory, state):
        pin(directory / 'result.json')
        pin(directory / 'source-pins.json')
        data = json.loads((directory / 'result.json').read_text())
        require(data['state'] == state and data['post_pins_match'] is True, 'Receipt not passing')
        require(data['source_pins_sha256'] == sha(directory / 'source-pins.json'), 'Receipt pins identity')
        for path, digest in json.loads((directory / 'source-pins.json').read_text()).items():
            require(sha(path) == digest, 'Receipt input drift: ' + path)
        return data

    try:
        pin(__file__)
        h = receipt(host, 'PORTABLE_HOST_CHECKED')
        s = receipt(spike, 'PORTABLE_SELECTOR_GNU_SPIKE_CHECKED')
        require(len(h['checks']) == 4 and len(s['cases']) == 4, 'Incomplete test matrix')
        old = (host / 'preimage/akv.cpp').read_text()
        live = (ARCH / 'akv.cpp').read_text()
        for path in (host / 'preimage/akv.cpp', host / 'preimage/resident.inc', ARCH / 'akv.cpp', ARCH / 'resident.inc'):
            pin(path)
        unchanged = []
        for label, start, end in (
                ('feature_math', 'static bool decode_features(', 'static kernel_policy requested_kernel_policy('),
                ('prefill', 'static int prefill_past_tokens(', 'static akv_status_t emulate('),
                ('decode_math_and_native_dispatch', 'static akv_status_t emulate(', '#if defined(GGML_AKV_RESIDENT) && GGML_AKV_RESIDENT\n#include "resident.inc"'),
                ('stage5_entry', 'bool ggml_riscv_akv_flash_attn(', 'static bool stage5_legacy_body(const ggml_compute_params *params')):
            require(span(old, start, end) == span(live, start, end), 'Changed protected region: ' + label)
            unchanged.append(label)
        resident = (host / 'preimage/resident.inc').read_text()
        resident = resident.replace('    if (supports_decode(params,dst,&active,&version,&rows,&dim)!=support_reason::supported ||',
            '    bool portable=false;\n    if (supports_decode(params,dst,&active,&version,&rows,&dim,&portable)!=support_reason::supported ||')
        resident = resident.replace('    const bool portable=portable_decode_enabled();\n', '')
        require(resident == (ARCH / 'resident.inc').read_text(), 'Resident changed beyond selection output')
        unchanged.append('resident_except_preflight_output')
        sdk = host / 'inputs/sdk/software/akv'
        arch = host / 'inputs/llama/ggml/src/ggml-cpu/arch/riscv'
        test = ROOT / 'verification/performance/next_mechanism/stage5/runtime/test_platform.c'
        pin(test)
        provider = []
        for mode, cc, extra in (('gnu', '/usr/bin/gcc', []),
                ('ubsan', '/usr/bin/clang', ['-fsanitize=undefined', '-fno-sanitize-recover=all'])):
            exe = out / ('provider-' + mode)
            argv = [cc, '-std=c11', '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-ffp-contract=off', '-ffunction-sections', '-fdata-sections', *extra,
                '-I' + str(arch), '-I' + str(sdk / 'include'), '-I' + str(sdk / 'experimental'),
                str(test), str(arch / 'platform.c'), str(sdk / 'src/akv_runtime.c'), str(sdk / 'src/akv_features.c'),
                '-Wl,--gc-sections', '-lm', '-o', str(exe)]
            pin(Path(cc).resolve())
            for label, command in ((mode + '-build', argv), (mode + '-run', [str(exe)])):
                with (out / (label + '.log')).open('x') as stream:
                    done = subprocess.run(command, env=env, cwd=out, stdout=stream,
                        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=90)
                commands.append(dict(label=label, argv=command, returncode=done.returncode))
                require(done.returncode == 0, 'Provider command failed: ' + label)
            text = (out / (mode + '-run.log')).read_text()
            require(text == 'PLATFORM_HOST_PASS checks=88 native_execution=0 board_acceptance=0\n', 'Incomplete provider oracle')
            pin(exe)
            provider.append(dict(mode=mode, checks=88, log_sha256=sha(out / (mode + '-run.log'))))
        for path, digest in pins.items():
            require(sha(path) == digest, 'Post-audit pin drift: ' + path)
        report.update(state='PORTABLE_ENABLEMENT_CHECKED', host=str(host), spike=str(spike),
            unchanged_regions=unchanged, provider=provider, post_pins_match=True,
            live_sha256={name: sha(ARCH / name) for name in ('akv.cpp', 'resident.inc')},
            limits=['Host backend and Spike selector only; not new hardware acceptance',
                    'Fresh GGML oracle core is a release build; adapter and SDK have UBSan checks',
                    'No new performance measurement; historical Refact whole-call benefit is separate',
                    'D256 remains rejected; mask holes require explicit portable or another selected feature'])
    except BaseException as exc:
        report['error'] = repr(exc)
    save(out / 'source-pins.json', pins)
    save(out / 'commands.json', commands)
    report['source_pins_sha256'] = sha(out / 'source-pins.json')
    save(out / 'result.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)
    return report['state'] != 'PORTABLE_ENABLEMENT_CHECKED'


if __name__ == '__main__':
    raise SystemExit(main())
