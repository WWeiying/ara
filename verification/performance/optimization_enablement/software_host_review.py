#!/usr/bin/env python3
"""Short GNU host contracts only; independent files, no model or EDA launch."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LLAMA = Path('/home/wangwy/llama/llama.cpp')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True); stream.write('\n')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fragment(text, start):
    pos = text.index(start); brace = text.index('{', pos); end = brace + 1; depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}'); end += 1
    return text[pos:end]


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); output = args.output.resolve()
    require(output.parent == OUT and output.name.startswith('enablement_software_') and
            not output.exists(), 'Fresh signoff enablement_software_ output required')
    output.mkdir()
    prefix = output/'software_host'
    def path(name): return Path(str(prefix) + '.' + name)
    report = dict(state='FAIL', native_execution=False, performance_measured=False,
                  model_launched=False, eda_launched=False)
    commands = []; pins = {}
    def pin(p): pins[str(p)] = sha(p)
    def verify():
        for p, digest in pins.items(): require(sha(p) == digest, 'Input drift: ' + p)
    def run(label, argv):
        with path(label + '.log').open('x') as stream:
            done = subprocess.run(list(map(str, argv)), stdout=stream, stderr=subprocess.STDOUT,
                                  cwd=ROOT, timeout=60, stdin=subprocess.DEVNULL)
        commands.append(dict(label=label, argv=list(map(str, argv)), returncode=done.returncode))
        require(done.returncode == 0, 'Command failed: ' + label)
        return path(label + '.log').read_text()
    try:
        for p in (Path(__file__).resolve(), HERE/'software_contract_test.cpp',
                  LLAMA/'ggml/src/ggml-cpu/repack.cpp',
                  LLAMA/'ggml/src/ggml-cpu/arch/riscv/quants.c',
                  LLAMA/'ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp',
                  LLAMA/'ggml/src/ggml-cpu/arch/riscv/qbs.cpp',
                  ROOT/'hardware/docs/INFERENCE_STAGE2_RVV_COOPERATIVE_MATRIX_20261109.md',
                  ROOT/'verification/performance/next_mechanism/stage4/RESULTS.md'):
            pin(p)
        historical = {}
        for directory, name in (
                ('stage2_soc_campaign_20261109_01', 'report.json'),
                ('stage4_projection_chain_vcs_20261110_01', 'result.json'),
                ('stage4_resident_features_vcs_perf_20261110_01', 'result.json'),
                ('stage4_resident_features_vcs_functional_20261110_01', 'result.json')):
            receipt = OUT/directory/name; pin(receipt)
            value = json.loads(receipt.read_text())
            require(value['state'] in ('PASS', 'PAIRED_CALLS_CHECKED') and
                    value['post_pins_match'] is True, 'Historical receipt not passing: ' + str(receipt))
            historical[str(receipt)] = dict(state=value['state'], sha256=sha(receipt),
                scope='Read-only historical receipt, not a fresh closure revalidation',
                measurements=value.get('summary', value.get('checked')))
        source = (LLAMA/'ggml/src/ggml-cpu/repack.cpp').read_text()
        path('repack.inc').write_text(fragment(source, 'static inline int nearest_int(') + '\n' +
            fragment(source, 'void ggml_quantize_mat_q8_K_4x1_ara_generic(') + '\n')
        pin(path('repack.inc'))
        quant = (LLAMA/'ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp').read_text()
        path('pv-guard.inc').write_text(fragment(quant, 'if (call.register_pv && call.grouped_pv)') + '\n')
        pin(path('pv-guard.inc'))
        sdk = ROOT/'software/akv'
        common = ['-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unknown-pragmas',
                  '-fno-fast-math', '-ffp-contract=off']
        jobs = [('qbs', '/usr/bin/gcc', ['-std=c11', *common, '-I'+str(ROOT/'software/qbs/include')],
                 ROOT/'software/qbs/src/qbs_runtime.c', path('qbs.o')),
                ('contracts', '/usr/bin/g++', ['-std=c++17', *common, '-Wno-unused-function',
                 '-DSOFTWARE_REPACK_FRAGMENT="'+str(path('repack.inc'))+'"',
                 '-DSOFTWARE_PV_GUARD_FRAGMENT="'+str(path('pv-guard.inc'))+'"',
                 *['-I'+str(p) for p in (ROOT, ROOT/'software/qbs/include', LLAMA/'ggml/include',
                    LLAMA/'ggml/src', LLAMA/'ggml/src/ggml-cpu', LLAMA/'ggml/src/ggml-cpu/arch/riscv')]],
                 HERE/'software_contract_test.cpp', path('contracts.o'))]
        feature_flags = ['-std=c11', *common, '-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1',
            '-DAKV_EXPERIMENTAL_RESIDENT_FEATURES_V2=1', '-I'+str(sdk/'include'), '-iquote', str(sdk/'src')]
        feature_sources = [ROOT/'verification/performance/next_mechanism/stage4/resident_features/test_features.c',
            *[sdk/'src'/n for n in ('akv_runtime.c', 'akv_native_riscv.c', 'akv_v2_reference.c',
                                  'akv_prefill_reference.c', 'akv_features.c', 'akv_decode.c')]]
        jobs += [('features'+str(i), '/usr/bin/gcc', feature_flags, p, path('features'+str(i)+'.o'))
                 for i, p in enumerate(feature_sources)]
        deps = {}
        for label, cc, flags, src, obj in jobs:
            pin(Path(cc).resolve())
            run(label+'-deps', [cc, *flags, '-M', '-MF', path(label+'.d'), src])
            deps[label] = shlex.split(path(label+'.d').read_text().replace('\\\n', '').split(':', 1)[1])
            for p in deps[label]: pin(Path(p).resolve())
        save(path('source-pins.json'), pins); verify()
        for label, cc, flags, src, obj in jobs:
            run(label+'-compile', [cc, *flags, '-c', src, '-o', obj])
        run('contracts-link', ['/usr/bin/g++', path('contracts.o'), path('qbs.o'), '-lm', '-o', path('contracts')])
        contract_log = run('contracts-run', [path('contracts')])
        require('SOFTWARE_CONTRACT_HOST_PASS' in contract_log, 'Missing contract completion')
        run('features-link', ['/usr/bin/gcc', *[job[4] for job in jobs[2:]], '-lm', '-o', path('features')])
        feature_log = run('features-run', [path('features')])
        require('FEATURES_V2_HOST_PASS maps=15360 leaf_stubs=76800 feature_combinations=32 native_execution=0'
                in feature_log, 'Incomplete feature gate')
        verify()
        report.update(state='SOFTWARE_HOST_CONTRACTS_CHECKED', pre_post_pins_match=True,
                      pins=len(pins), contract_log=contract_log, feature_log=feature_log,
                      historical_receipts=historical,
                      source_pins_sha256=sha(path('source-pins.json')))
    except BaseException as exc:
        report['error'] = repr(exc)
    save(path('commands.json'), commands)
    report['artifacts'] = {str(p): sha(p) for p in output.glob(prefix.name + '.*') if p.is_file()}
    save(path('result.json'), report)
    print(json.dumps({k:v for k,v in report.items() if k != 'artifacts'}, sort_keys=True))
    return report['state'] != 'SOFTWARE_HOST_CONTRACTS_CHECKED'


if __name__ == '__main__':
    raise SystemExit(main())
