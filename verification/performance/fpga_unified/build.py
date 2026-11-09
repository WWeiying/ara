#!/usr/bin/env python3
"""Build a frozen FPGA software candidate, without deploying or running a model."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ARA = HERE.parents[2]
OUT = ARA.parent / 'ara_dsa_signoff_integration/verification/out'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
LLAMA_BASE = 'da56aa750559c180d631b466de983ff2bb5d54d9'
SDK = 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1'
QBS = '130730b5bb25eeba375a5b04eefb67d9e8635f34'
AKV_ADAPTER = '06d046324e1dde07d3d6f8625843b2b8858a1a06'
TOOLS = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin')
HANDOFF = Path('/home/wangwy/fpga_runs/optimization_board_proof_20261105_01/software_version_handoff_20261107.json')
HANDOFF_SHA = '1713eb4d08457e930b990dc9e94cf728f738842b2ebe18ad5b4a669bade32f07'
TRACE_TEST = Path('/home/wangwy/fpga_runs/qwen3_perf_diagnosis_20261104_01/test_trace_context_v1.cpp')
TRACE_TEST_SHA = '252a99fa90640e41a12612263bca87ed340e18509ba2f8b4c86ca5db99076eaa'
POLICY = ARA / 'verification/performance/akv_pair_eval/integration'
ISA = '-march=rv64gcv_zfh_zvfh'
F16_ENV = {
    'GGML_RISCV_QBS': '1', 'GGML_RISCV_AKV': '1',
    'GGML_RISCV_QBS_TRACE': '1', 'GGML_RISCV_AKV_TRACE': '1',
    'GGML_RISCV_QBS_EMULATE': '0', 'GGML_RISCV_AKV_EMULATE': '0',
    'GGML_RISCV_AKV_PORTABLE': '0', 'GGML_RISCV_QBS_M4_PREPARE': '1',
    'GGML_RISCV_QBS_M4_PACKED': '1', 'GGML_RISCV_QBS_M4_PARALLEL_SUMS': '1',
    'GGML_RISCV_QBS_M4_CACHE': '1', 'GGML_RISCV_QBS_CROSS_OP_CONTEXT': '1',
    'GGML_RISCV_QBS_ACTIVATION_CONTEXT': '1', 'GGML_RISCV_QBS_WIDE_M': '0',
    'GGML_RISCV_QBS_TRACE_M4_PREPARE': '0', 'GGML_RISCV_QBS_TRACE_LIFETIME': '0',
    'GGML_RISCV_QBS_TRACE_CALLS': '0', 'GGML_RISCV_AKV_QUANT_KV': '0',
    'GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY': '0',
    'GGML_RISCV_AKV_REGISTER_PV': '0', 'GGML_RISCV_AKV_QUANT_PREFILL': '0',
    'GGML_RISCV_AKV_GROUPED_PV': '0',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            result.update(chunk)
    return result.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def extract(repo, commit, target, paths=()):
    raw = git(repo, 'archive', commit, *paths)
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        members = archive.getmembers()
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute()
                    and '..' not in Path(m.name).parts for m in members), 'Unsafe archive member')
        archive.extractall(target, filter='data')


def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in root.rglob('*') if p.is_file()}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Build:
    def __init__(self, output, jobs):
        self.out, self.jobs = output, jobs
        self.commands = []
        self.pins = {}

    def run(self, argv, label, cwd=None, timeout=300):
        argv = list(map(str, argv))
        self.commands.append(dict(argv=argv, cwd=str(cwd or self.out)))
        save(self.out / 'commands.json', self.commands)
        print(label, flush=True)
        with (self.out / (label + '.log')).open('x') as log:
            subprocess.run(argv, cwd=cwd or self.out, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=timeout)

    def pin(self, paths):
        self.pins.update({str(p.resolve()): sha(p) for p in paths})
        save(self.out / 'source-pins.json', self.pins)

    def check_pins(self):
        require(all(sha(p) == expected for p, expected in self.pins.items()), 'Sealed source drift')

    def prepare(self):
        require(sha(HANDOFF) == HANDOFF_SHA, 'Board handoff identity changed')
        require(sha(TRACE_TEST) == TRACE_TEST_SHA, 'Trace test identity changed')
        self.handoff = json.loads(HANDOFF.read_text())
        require(self.handoff['delivery']['llama_commit'] == LLAMA_BASE, 'Unexpected board source base')
        for variant in self.handoff['variants'].values():
            require(sha(variant['host_elf']) == variant['sha256'], 'Accepted ELF identity changed')
        require(git(ARA, 'rev-parse', SDK + ':software/qbs') ==
                git(ARA, 'rev-parse', QBS + ':software/qbs'), 'QBS SDK differs from board repair')
        changes = git(ARA, 'diff', '--name-only', self.handoff['delivery']['ara_commit'], SDK,
                      '--', 'software/akv').decode().splitlines()
        require(set(changes) == {'software/akv/experimental/paired_heads/auto_policy.h',
            'software/akv/include/akv/akv.h', 'software/akv/include/akv/akv_features.h',
            'software/akv/src/akv_v2_native_riscv.c'}, 'Unexpected SDK delta from board delivery')

        inputs = self.out / 'inputs'
        inputs.mkdir()
        self.llama, self.sdk = inputs / 'llama', inputs / 'ara'
        extract(LLAMA, LLAMA_BASE, self.llama)
        extract(ARA, SDK, self.sdk, ('software/akv', 'software/qbs'))
        before = inventory(self.llama)
        self.baseline_trace = inputs / 'baseline-qbs.cpp'
        shutil.copy2(self.llama / 'ggml/src/ggml-cpu/arch/riscv/qbs.cpp', self.baseline_trace)
        patches = [HERE / 'qbs_trace_context.patch', HERE / 'akv_auto.patch']
        for index, patch in enumerate(patches):
            options = ['--unsafe-paths', '--directory=' + str(self.llama)]
            self.run(['git', 'apply', '--check', *options, patch], 'patch-check-' + str(index), cwd=ARA)
            self.run(['git', 'apply', *options, patch], 'patch-apply-' + str(index), cwd=ARA)
        after = inventory(self.llama)
        changed = [name for name in before if before[name] != after[name]]
        require(before.keys() == after.keys() and set(changed) == {
            'ggml/src/ggml-cpu/arch/riscv/qbs.cpp', 'ggml/src/ggml-cpu/arch/riscv/akv.cpp'},
            'Candidate modified more than the two scoped adapters')
        qbs = self.llama / 'ggml/src/ggml-cpu/arch/riscv/qbs.cpp'
        require(sha(qbs) == self.handoff['trace_candidate']['overlay_sha256'],
                'QBS patch does not reproduce the measured board overlay')
        require(sha(self.sdk / 'software/qbs/src/qbs_runtime.c') ==
                self.handoff['sdk_repairs']['runtime_source_sha256'], 'QBS runtime drift')
        for name in ('akv_attention_rvv.S', 'akv_v2_attention_rvv.S'):
            relative = 'software/akv/src/' + name
            require((self.sdk / relative).read_bytes() == git(ARA, 'show',
                    self.handoff['delivery']['ara_commit'] + ':' + relative), 'Non-delivery assembly')
        self.policy = load_module(POLICY / 'test_ggml_policy.py', 'unified_ggml_policy')
        adapter = (self.llama / 'ggml/src/ggml-cpu/arch/riscv/akv.cpp').read_text()
        committed = git(LLAMA, 'show', AKV_ADAPTER + ':ggml/src/ggml-cpu/arch/riscv/akv.cpp').decode()
        require(self.policy.helper_region(adapter)[2] == self.policy.helper_region(committed)[2],
                'Auto helper differs from the reviewed adapter')
        self.pin([p for base in (self.llama, self.sdk) for p in base.rglob('*') if p.is_file()] +
                 [Path(__file__), HANDOFF, TRACE_TEST, *patches, HERE / 'run_board.sh',
                  POLICY / 'test_ggml_policy.py', POLICY / 'test_auto_policy.c', self.baseline_trace])
        save(self.out / 'composition.json', dict(llama_base=LLAMA_BASE, sdk=SDK,
            qbs_sdk_equivalent_to=QBS, reviewed_auto_adapter=AKV_ADAPTER,
            source_changes=changed, patches={str(p): sha(p) for p in patches},
            delivery_assembly_unchanged=True, dirty_sources_excluded=True,
            m4_and_quantized_kv_sources_retained=True, rtl_modified=False))

    def host_tests(self):
        tests = self.out / 'tests'
        tests.mkdir()
        trace_outputs = {}
        for compiler, flags in [('g++', ['-O2']), ('clang++',
                ['-O2', '-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
            cc = shutil.which(compiler)
            require(cc, 'Required host compiler missing: ' + compiler)
            for mode, source in [(0, self.baseline_trace),
                    (1, self.llama / 'ggml/src/ggml-cpu/arch/riscv/qbs.cpp')]:
                label = 'trace-' + compiler.replace('+', 'p') + '-' + str(mode)
                binary = tests / label
                self.run([cc, *flags, '-std=c++17', '-ffunction-sections', '-fdata-sections',
                    '-Wl,--gc-sections', '-Wl,--wrap=getenv',
                    '-DGGML_CPU_FP16_TO_FP32=GGML_COMPUTE_FP16_TO_FP32',
                    '-DTRACE_CANDIDATE=' + str(mode), '-DTRACE_TEST_SOURCE="' + str(source) + '"',
                    *['-I' + str(self.llama / p) for p in
                      ('ggml/include', 'ggml/src', 'ggml/src/ggml-cpu', 'ggml/src/ggml-cpu/arch/riscv')],
                    '-I' + str(self.sdk / 'software/qbs/include'), TRACE_TEST, '-o', binary], label + '-build')
                self.run([binary], label + '-run')
                trace_outputs[(compiler, mode)] = (self.out / (label + '-run.log')).read_bytes()
            require(trace_outputs[(compiler, 0)] == trace_outputs[(compiler, 1)],
                    'Trace/counter/output diagnostics changed')

        for compiler, flags in [('gcc', '-O2 -g'), ('clang',
                '-O2 -g -fsanitize=address,undefined -fno-omit-frame-pointer')]:
            self.run(['make', '-j' + str(self.jobs), 'check', 'CC=' + compiler,
                'BUILD=' + str(tests / ('qbs-' + compiler)),
                'CFLAGS=' + flags + ' -std=c11 -Wall -Wextra -Werror -Iinclude'],
                'sdk-qbs-' + compiler, cwd=self.sdk / 'software/qbs')

        adapter = (self.llama / 'ggml/src/ggml-cpu/arch/riscv/akv.cpp').read_text()
        for mode in (0, 1, 2):
            sdk = self.sdk
            if mode == 0:
                sdk = tests / 'old-sdk'
                extract(ARA, self.handoff['delivery']['ara_commit'], sdk, ('software/akv/include',))
            for portable in (0, 1):
                label = 'akv-routing-' + str(mode) + '-' + str(portable)
                source = tests / (label + '.cpp')
                source.write_text(self.policy.HOST.replace('@HELPERS@', self.policy.helper_region(adapter)[2])
                    .replace('@PORTABLE_BODY@', self.policy.portable_region(adapter))
                    .replace('@WIP_PLAIN@', 'true'))
                binary = source.with_suffix('')
                self.run(['g++', '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-function', '-Wno-unused-variable', '-DPOLICY_MODE=' + str(mode),
                    '-DPORTABLE=' + str(portable), '-I' + str(sdk / 'software/akv/include'),
                    source, '-o', binary], label + '-build')
                self.run([binary], label + '-run')
        binary = tests / 'auto-policy'
        self.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-ffunction-sections', '-fdata-sections', '-fno-fast-math', '-ffp-contract=off',
            '-I' + str(self.sdk / 'software/akv/include'),
            '-I' + str(self.sdk / 'software/akv/experimental/paired_heads'),
            POLICY / 'test_auto_policy.c', *[self.sdk / 'software/akv/src' / p for p in
                ('akv_runtime.c', 'akv_features.c', 'akv_v2_native_riscv.c')],
            '-Wl,--gc-sections', '-lm', '-o', binary], 'auto-policy-build')
        self.run([binary], 'auto-policy-run')
        require('decisions=185760 native_execution=0' in (self.out / 'auto-policy-run.log').read_text(),
                'Auto policy matrix not executed')
        self.check_pins()
        save(self.out / 'host-tests.json', dict(state='PASS', trace_variants=4,
            trace_bytes_and_counters_equal=True, trace_configurations_per_variant=64,
            qbs_sdk_suites=['gcc', 'clang-address-undefined'],
            akv_routing_variants=6, auto_policy_decisions=185760, target_execution=False))

    def cross_build(self):
        build = self.out / 'build'
        self.run(['cmake', '-S', self.llama, '-B', build, '-G', 'Ninja',
            '-DCMAKE_SYSTEM_NAME=Linux', '-DCMAKE_SYSTEM_PROCESSOR=riscv64',
            '-DCMAKE_C_COMPILER=' + str(TOOLS / 'riscv64-linux-gcc'),
            '-DCMAKE_CXX_COMPILER=' + str(TOOLS / 'riscv64-linux-g++'),
            '-DCMAKE_ASM_COMPILER=' + str(TOOLS / 'riscv64-linux-gcc'),
            '-DCMAKE_C_FLAGS=-march=rv64gcv -mabi=lp64d',
            '-DCMAKE_CXX_FLAGS=-march=rv64gcv -mabi=lp64d',
            '-DCMAKE_EXE_LINKER_FLAGS=-static', '-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DBUILD_SHARED_LIBS=OFF',
            '-DGGML_NATIVE=OFF', '-DGGML_OPENMP=OFF', '-DGGML_BACKEND_DL=OFF',
            '-DGGML_RVV=ON', '-DGGML_RV_ZFH=ON', '-DGGML_RV_ZVFH=ON',
            '-DGGML_RV_ZICBOP=OFF', '-DGGML_RV_ZIHINTPAUSE=OFF', '-DGGML_RV_ZVFBFWMA=OFF',
            '-DGGML_RISCV_QBS=ON', '-DGGML_RISCV_QBS_RUNTIME_DIR=' + str(self.sdk / 'software/qbs'),
            '-DGGML_RISCV_AKV=ON', '-DGGML_RISCV_AKV_RUNTIME_DIR=' + str(self.sdk / 'software/akv'),
            '-DGGML_RISCV_AKV_QUANT_KV=ON', '-DGGML_RISCV_AKV_REGISTER_PV=ON',
            '-DGGML_RISCV_AKV_QUANT_PREFILL=ON',
            '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_TOOLS=OFF', '-DLLAMA_BUILD_EXAMPLES=ON',
            '-DLLAMA_BUILD_SERVER=OFF', '-DLLAMA_BUILD_MTMD=OFF', '-DLLAMA_BUILD_APP=OFF',
            '-DLLAMA_OPENSSL=OFF'], 'cmake-configure')
        self.run(['cmake', '--build', build, '--target', 'llama-simple', '-j', self.jobs],
                 'cmake-build', timeout=2400)
        rows = json.loads((build / 'compile_commands.json').read_text())
        native = set()
        actual = {row['file'] for row in rows}
        for row in rows:
            if not ('/ggml/' in row['file'] or '/software/' in row['file']):
                continue
            argv = shlex.split(row['command'])
            arches = [a for a in argv if a.startswith('-march=')]
            require(arches == ['-march=rv64gcv', ISA] or
                    (row['file'].endswith('.S') and arches == [ISA]),
                    'Unexpected GGML ISA flags; preserve the board build override order')
            require('-mabi=lp64d' in argv, 'Unexpected ABI')
            if row['file'].startswith(str(self.sdk / 'software/akv/src') + '/') and row['file'].endswith('.c'):
                require(all(a in argv for a in ('-fno-fast-math', '-ffp-contract=off')) and
                        not any(a in argv for a in ('-ffast-math', '-Ofast', '-ffp-contract=fast')),
                        'AKV floating point contract changed')
                native.add(Path(row['file']).name)
        require(native == {'akv_runtime.c', 'akv_native_riscv.c', 'akv_v2_native_riscv.c',
                           'akv_prefill_reference.c', 'akv_features.c'}, 'Missing canonical runtime')
        require({str(self.llama / 'ggml/src/ggml-cpu/arch/riscv' / p) for p in
                 ('akv.cpp', 'qbs.cpp', 'quant-kv.cpp')} <= actual, 'Missing runtime adapter')
        cpu = build / 'ggml/src/libggml-cpu.a'
        require(cpu.is_file(), 'Missing CPU archive')
        self.run([TOOLS / 'riscv64-linux-nm', cpu], 'cpu-symbols')
        self.run([TOOLS / 'riscv64-linux-nm', build / 'bin/llama-simple'], 'elf-symbols')
        elf_symbols = (self.out / 'elf-symbols.log').read_text()
        for symbol in ('akv_attention_execute_v2_native_auto',
                       'akv_attention_execute_v2_with_features_native_auto', 'qbs_native_execute_command',
                       'akv_experimental_qk_f16_pair_panel4', 'akv_experimental_pv_f16_pair'):
            require(any(line.endswith(' T ' + symbol) for line in elf_symbols.splitlines()),
                    'Final ELF missing definition: ' + symbol)
        self.run([TOOLS / 'riscv64-linux-readelf', '-h', '-l', '-A', build / 'bin/llama-simple'], 'elf-identity')
        require('INTERP' not in (self.out / 'elf-identity.log').read_text(), 'ELF not statically linked')
        self.pin([TOOLS / p for p in ('riscv64-linux-gcc', 'riscv64-linux-g++',
                                     'riscv64-linux-ar', 'riscv64-linux-strip', 'riscv64-linux-readelf')])
        self.check_pins()
        save(self.out / 'compile-audit.json', dict(state='PASS', configured_translation_units=len(rows),
            compiled_objects=sum(1 for p in build.rglob('*.o') if p.is_file()),
            native_fp_contract=True, complete_model_executable=True, static=True,
            dirty_sources_excluded=True, deployment=False,
            artifacts={str(p): sha(p) for p in (cpu, build / 'bin/llama-simple', build / 'compile_commands.json')}))
        return build / 'bin/llama-simple'

    def package(self, executable):
        bundle = self.out / 'board_bundle'
        bundle.mkdir()
        unified = bundle / 'llama-f16-unified'
        shutil.copy2(executable, unified)
        self.run([TOOLS / 'riscv64-linux-strip', unified], 'strip-unified')
        accepted = self.handoff['variants']['final_F16_trace_M4']
        shutil.copy2(accepted['host_elf'], bundle / 'llama-f16-accepted')
        shutil.copy2(HERE / 'run_board.sh', bundle / 'run_board.sh')
        (bundle / 'run_board.sh').chmod(0o755)
        binaries = {p.name: sha(p) for p in (unified, bundle / 'llama-f16-accepted')}
        (bundle / 'SHA256SUMS').write_text(''.join(v + '  ' + k + '\n' for k, v in binaries.items()))
        save(bundle / 'manifest.json', dict(state='HOST_QUALIFIED_BOARD_UNTESTED',
            llama_base=LLAMA_BASE, sdk=SDK, source_manifest=str(self.out / 'composition.json'),
            source_pins_sha256=sha(self.out / 'source-pins.json'), binaries=binaries,
            hardware=self.handoff['hardware'], model=self.handoff['model'],
            environment=F16_ENV, arms={'accepted': 'Original measured F16/M4 ELF',
                'generic': 'Unified ELF, AKV_PAIR_HEADS=0', 'auto': 'Unified ELF, AKV_PAIR_HEADS absent'},
            expected_kv='f16/f16', quantized_kv_compiled_but_disabled=True,
            model_executed=False, new_board_speedup=None))
        return bundle, binaries


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.parent == OUT.resolve() and not out.exists(), 'Use a fresh verification output directory')
    require(1 <= args.jobs <= 32, 'Jobs must be 1..32')
    out.mkdir()
    worker = Build(out, args.jobs)
    started = time.time()
    result = dict(state='FAIL', model_executed=False, board_executed=False, rtl_modified=False)
    try:
        worker.prepare()
        worker.host_tests()
        binary = worker.cross_build()
        bundle, hashes = worker.package(binary)
        worker.check_pins()
        result.update(state='HOST_QUALIFIED_BOARD_UNTESTED', board_bundle=str(bundle),
                      binaries=hashes, source_pins_sha256=sha(out / 'source-pins.json'))
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        result['elapsed_seconds'] = time.time() - started
        save(out / 'result.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
