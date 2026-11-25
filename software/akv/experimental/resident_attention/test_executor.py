#!/usr/bin/env python3
"""Bounded host/stub and GNU compile checks, never launch native simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SDK = ROOT / 'software/akv'
CORE = SDK / 'src/akv_v2_native_riscv.c'
GNU = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-')
MACRO = 'AKV_EXPERIMENTAL_RESIDENT_ATTENTION'
ENTRY = 'akv_experimental_attention_execute_v2_native'
BASE_REV = '4a7361f51ba5447a616217dad1c8e72e3ee2b45b'
BASE_SHA = '7275cff381c45705e868c82626b4488080c79438b07d692d37646b6f29070122'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(output):
    output = output.resolve()
    output.mkdir(exist_ok=False)
    checks, commands = [], []
    pins = {str(p): sha(p) for tree in (SDK / 'include', SDK / 'src', SDK / 'experimental')
            for p in tree.rglob('*') if p.is_file() and p.suffix in ('.h', '.c', '.S', '.inc', '.py')}
    for tool in ('gcc', 'nm', 'objdump'):
        p = Path(str(GNU) + tool)
        pins[str(p)] = sha(p)
    pins['/usr/bin/cc'] = sha('/usr/bin/cc')
    pins['/usr/bin/clang'] = sha('/usr/bin/clang')
    (output / 'source-pins.json').write_text(json.dumps(pins, indent=2, sort_keys=True) + '\n')
    for p in (CORE, HERE / 'executor.h', HERE / 'test_executor.c', HERE / 'test_executor.py'):
        dest = output / 'inputs' / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)

    def command(label, argv, expected=0):
        argv = list(map(str, argv))
        log = output / (label + '.log')
        record = dict(label=label, argv=argv, cwd=str(output), timeout=60, log=str(log))
        commands.append(record)
        with log.open('x') as stream:
            proc = subprocess.run(argv, cwd=output, stdout=stream, stderr=subprocess.STDOUT, timeout=60)
        record['returncode'] = proc.returncode
        require(proc.returncode == expected if expected is not None else proc.returncode != 0,
                'Unexpected command result: ' + label)
        return log.read_text()

    report = dict(state='FAIL', native_execution=False, numerical_execution=False,
                  simulator_launched=False, checks=checks)
    try:
        original = subprocess.check_output(['git', 'show', BASE_REV + ':software/akv/src/akv_v2_native_riscv.c'], cwd=ROOT)
        require(hashlib.sha256(original).hexdigest() == BASE_SHA, 'Unreviewed predecessor core')
        baseline = output / 'baseline/akv_v2_native_riscv.c'
        baseline.parent.mkdir()
        baseline.write_bytes(original)
        other = [SDK / 'src' / name for name in ('akv_runtime.c', 'akv_native_riscv.c',
                 'akv_v2_reference.c', 'akv_prefill_reference.c', 'akv_features.c', 'akv_decode.c')]
        host = ['/usr/bin/cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-Wno-unknown-pragmas', '-fno-fast-math', '-ffp-contract=off', '-I' + str(SDK / 'include')]
        for mode in (0, 1):
            binary = output / f'host-{mode}'
            command(f'host-{mode}-compile', host + [f'-D{MACRO}={mode}', HERE / 'test_executor.c',
                    *other, '-lm', '-o', binary])
            log = command(f'host-{mode}-run', [binary])
            require(f'EXECUTOR_HOST_PASS macro={mode} native_execution=0' in log, 'Missing host marker')
            if mode:
                require('HOST_STUB_MAPS=196 LEAF_CALLS=976 numerical_execution=0' in log,
                        'Unexpected map/stub exercise counts')
            checks.append(f'host_macro_{mode}')
        binary = output / 'host-ubsan'
        command('host-ubsan-compile', ['/usr/bin/clang', *host[1:]] + [f'-D{MACRO}=1', '-fsanitize=undefined',
                '-fno-sanitize-recover=all', HERE / 'test_executor.c', *other, '-lm', '-o', binary])
        command('host-ubsan-run', [binary])
        checks.append('host_ubsan')

        flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
                 '-O3', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
                 '-Wno-unknown-pragmas', '-I' + str(SDK / 'include'), '-iquote', SDK / 'src',
                 '-DAKV_REFILL_OVERLAP=0']
        gcc = str(GNU) + 'gcc'
        for label, source, extra in (('baseline', baseline, []), ('default', CORE, []),
                ('off', CORE, [f'-D{MACRO}=0']), ('on', CORE, [f'-D{MACRO}=1'])):
            command(label + '-compile', [gcc, *flags, *extra, '-c', source, '-o', output / (label + '.o')])
            command(label + '-symbols', [str(GNU) + 'nm', output / (label + '.o')])
        require((output / 'baseline.o').read_bytes() == (output / 'default.o').read_bytes() ==
                (output / 'off.o').read_bytes(), 'Default/OFF GNU object changed from predecessor')
        checks.append('default_and_off_whole_object_byte_identity')
        default_symbols = (output / 'default-symbols.log').read_text()
        enabled_symbols = (output / 'on-symbols.log').read_text()
        require('akv_experimental_resident_' not in default_symbols and ENTRY not in default_symbols,
                'Resident reference in default object')
        require(re.search(r'\bT ' + ENTRY + r'$', enabled_symbols, re.M) and
                all(re.search(r'\bU akv_experimental_resident_' + n + r'$', enabled_symbols, re.M)
                    for n in ('qk_prepared', 'pv_prepared')), 'Missing actual resident entry/leaf links')
        checks.append('enabled_entry_and_both_leaf_references')
        overlap_flags = [f for f in flags if f != '-DAKV_REFILL_OVERLAP=0']
        command('on-overlap-compile', [gcc, *overlap_flags, '-DAKV_REFILL_OVERLAP=1',
                f'-D{MACRO}=1', '-c', CORE, '-o', output / 'on-overlap.o'])
        checks.append('enabled_overlap_policy_build')
        command('invalid-macro', [gcc, *flags, f'-D{MACRO}=2', '-c', CORE,
                '-o', output / 'invalid.o'], expected=None)
        checks.append('invalid_macro_rejected')
        command('on-disassembly', [str(GNU) + 'objdump', '-dr', '-M', 'no-aliases,numeric', output / 'on.o'])

        text = CORE.read_text()
        body = text.split('static akv_status_t execute_v2_with_features_native_internal(', 1)[1]
        body = body.split('\nakv_status_t akv_attention_execute_v2_with_features_native(', 1)[0]
        for before, after in (('akv_attention_can_use_plain_scores(', 'prepare_resident_schedule('),
                              ('prepare_resident_schedule(', 'csrr %0, vlenb'),
                              ('csrr %0, vlenb', 'initialize_workspace('),
                              ('initialize_workspace(', 'issue_full('),
                              ('resident_qk_tile(', 'apply_scale_mask_and_softmax('),
                              ('apply_scale_mask_and_softmax(', 'resident_pv_tile('),
                              ('resident_pv_tile(', 'issue_release('),
                              ('issue_release(', 'store_outputs(')):
            require(body.index(before) < body.index(after), 'Core ordering: ' + before)
        loop = body[body.index('for (uint32_t tile_start'):body.index('issue_release(')]
        require(not any(x in loop for x in ('prepare_resident_schedule(', 'return ', 'resident =',
                                            'resident_state_matches(', 'csrr')), 'Mid-execution re-selection')
        require(not re.search(r'\b(?:csrwi|csrw|fscsr|fsflags|fsrm)\b', body), 'Unexpected CSR write')
        for api in ('akv_attention_execute_v2_with_features_native',
                    'akv_attention_execute_v2_with_features_native_auto'):
            api_body = text.split('\nakv_status_t ' + api + '(', 1)[1].split('\nakv_status_t ', 1)[0]
            require('#if AKV_EXPERIMENTAL_RESIDENT_ATTENTION\n      , NULL\n#endif' in api_body,
                    'Original API must pass NULL resident options: ' + api)
        checks.append('same_core_ordering_no_retry_or_csr_write')
        require(all(sha(p) == digest for p, digest in pins.items()), 'Input drift during checks')
        report.update(state='HOST_GNU_PASS_NOT_EXECUTED', checks_passed=len(checks),
                      host_maps=196, host_stub_leaf_calls=976, predecessor_sha256=BASE_SHA,
                      predecessor_revision=BASE_REV,
                      default_object_sha256=sha(output / 'default.o'), post_pins_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    report['source_pins_sha256'] = sha(output / 'source-pins.json')
    report['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return report['state'] == 'HOST_GNU_PASS_NOT_EXECUTED'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    raise SystemExit(not run(parser.parse_args().output))
