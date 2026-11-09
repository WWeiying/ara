#!/usr/bin/env python3
"""Qualify per-target ISA flags against the measured FPGA build; never deploy."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import time

import build as base

REFERENCE = Path('/home/wangwy/fpga_runs/qwen3_hw_sw_ab_20261104_01/build-sw/compile_commands.json')
REFERENCE_SHA = 'f8901040c08991ed224b3dfbca6b391350faac7ec4c8050d5d9498ed418c23ce'


def source_identity(path):
    for part in ('llama', 'ara'):
        marker = '/inputs/' + part + '/'
        if marker in path:
            return part + '/' + path.split(marker, 1)[1]
    return None


def isa_abi(row):
    return [a for a in shlex.split(row['command']) if a.startswith(('-march=', '-mabi='))]


def verify_target_policy(row, reference):
    identity = source_identity(row['file'])
    if identity is None:
        return False
    base.require(identity in reference, 'Source not in the measured build: ' + identity)
    base.require(isa_abi(row) == reference[identity], 'ISA/ABI differs from board for ' + identity)
    return True


class Build(base.Build):
    def prepare(self):
        super().prepare()
        self.pin([Path(__file__), REFERENCE])

    def audit_compilation(self, directory):
        base.require(base.sha(REFERENCE) == REFERENCE_SHA, 'Original board command inventory drift')
        reference = {source_identity(r['file']): isa_abi(r) for r in json.loads(REFERENCE.read_text())
                     if source_identity(r['file']) is not None}
        rows = json.loads((directory / 'compile_commands.json').read_text())
        audited = sum(verify_target_policy(row, reference) for row in rows)
        actual = {row['file'] for row in rows}
        native = set()
        for row in rows:
            if row['file'].startswith(str(self.sdk / 'software/akv/src') + '/') and row['file'].endswith('.c'):
                argv = shlex.split(row['command'])
                base.require(all(a in argv for a in ('-fno-fast-math', '-ffp-contract=off')) and
                             not any(a in argv for a in ('-ffast-math', '-Ofast', '-ffp-contract=fast')),
                             'F16 AKV floating point contract changed')
                native.add(Path(row['file']).name)
        base.require(native == {'akv_runtime.c', 'akv_native_riscv.c', 'akv_v2_native_riscv.c',
                     'akv_prefill_reference.c', 'akv_features.c'}, 'Missing canonical F16 runtime')
        base.require({str(self.llama / 'ggml/src/ggml-cpu/arch/riscv' / p) for p in
                     ('akv.cpp', 'qbs.cpp', 'quant-kv.cpp')} <= actual, 'Missing GGML adapters')
        cpu, elf = directory / 'ggml/src/libggml-cpu.a', directory / 'bin/llama-simple'
        base.require(cpu.is_file() and elf.is_file(), 'Complete linked program is required')
        artifacts = (cpu, elf, directory / 'compile_commands.json')
        self.pin([*artifacts, REFERENCE, *[base.TOOLS / p for p in
                  ('riscv64-linux-gcc', 'riscv64-linux-g++', 'riscv64-linux-ar',
                   'riscv64-linux-strip', 'riscv64-linux-readelf', 'riscv64-linux-nm')]])
        self.run([base.TOOLS / 'riscv64-linux-nm', cpu], 'cpu-symbols')
        self.run([base.TOOLS / 'riscv64-linux-nm', elf], 'elf-symbols')
        symbols = (self.out / 'elf-symbols.log').read_text()
        for name in ('akv_attention_execute_v2_native_auto',
                     'akv_attention_execute_v2_with_features_native_auto', 'qbs_native_execute_command',
                     'akv_experimental_qk_f16_pair_panel4', 'akv_experimental_pv_f16_pair'):
            base.require(any(line.endswith(' T ' + name) for line in symbols.splitlines()),
                         'Missing final ELF symbol: ' + name)
        self.run([base.TOOLS / 'riscv64-linux-readelf', '-h', '-l', '-A', elf], 'elf-identity')
        base.require('INTERP' not in (self.out / 'elf-identity.log').read_text(), 'ELF not static')
        self.check_pins()
        base.save(self.out / 'compile-audit.json', dict(state='PASS', configured_translation_units=len(rows),
            per_source_isa_abi_matched=audited, original_command_inventory_sha256=REFERENCE_SHA,
            compiled_objects=sum(1 for p in directory.rglob('*.o') if p.is_file()),
            native_fp_contract=True, complete_model_executable=True, static=True,
            dirty_sources_excluded=True, deployment=False,
            artifacts={str(p): base.sha(p) for p in artifacts}))
        return elf

    def cross_build(self):
        directory = self.out / 'build'
        self.run(['cmake', '-S', self.llama, '-B', directory, '-G', 'Ninja',
            '-DCMAKE_SYSTEM_NAME=Linux', '-DCMAKE_SYSTEM_PROCESSOR=riscv64',
            '-DCMAKE_C_COMPILER=' + str(base.TOOLS / 'riscv64-linux-gcc'),
            '-DCMAKE_CXX_COMPILER=' + str(base.TOOLS / 'riscv64-linux-g++'),
            '-DCMAKE_ASM_COMPILER=' + str(base.TOOLS / 'riscv64-linux-gcc'),
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
        self.run(['cmake', '--build', directory, '--target', 'llama-simple', '-j', self.jobs],
                 'cmake-build', timeout=2400)
        return self.audit_compilation(directory)

    def reuse(self, previous):
        base.require(previous.parent == base.OUT.resolve(), 'Previous build must be in the verification outputs')
        original = json.loads((previous / 'result.json').read_text())
        base.require(original['state'] == 'FAIL' and original.get('error') ==
            "ValueError('Unexpected GGML ISA flags; preserve the board build override order')",
            'Reuse is limited to the proven per-target checker failure')
        base.require(json.loads((previous / 'host-tests.json').read_text())['state'] == 'PASS',
                     'Prior host qualification must have passed')
        base.require('[223/223] Linking CXX executable bin/llama-simple' in
                     (previous / 'cmake-build.log').read_text(), 'Incomplete original link')
        self.pins = json.loads((previous / 'source-pins.json').read_text())
        self.check_pins()
        self.handoff = json.loads(base.HANDOFF.read_text())
        self.llama, self.sdk = previous / 'inputs/llama', previous / 'inputs/ara'
        for name in ('composition.json', 'host-tests.json'):
            shutil.copy2(previous / name, self.out / name)
        self.pin([Path(__file__), *[previous / name for name in
            ('result.json', 'source-pins.json', 'host-tests.json', 'composition.json',
             'commands.json', 'cmake-build.log')]])
        base.save(self.out / 'reuse.json', dict(original_worker=str(previous),
            original_state_unchanged='FAIL', source_pins_rechecked=True,
            reason='Per-file ISA/ABI must match the original board target, not one global expectation',
            compiler_rerun=False, simulator_rerun=False))
        return self.audit_compilation(previous / 'build')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--reuse-build', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    base.require(output.parent == base.OUT.resolve() and not output.exists(), 'Fresh output required')
    base.require(1 <= args.jobs <= 32, 'Jobs must be 1..32')
    output.mkdir()
    worker = Build(output, args.jobs)
    started = time.time()
    result = dict(state='FAIL', model_executed=False, board_executed=False, rtl_modified=False)
    try:
        if args.reuse_build:
            executable = worker.reuse(args.reuse_build.resolve(strict=True))
        else:
            worker.prepare()
            worker.host_tests()
            executable = worker.cross_build()
        bundle, hashes = worker.package(executable)
        worker.check_pins()
        result.update(state='HOST_QUALIFIED_BOARD_UNTESTED', board_bundle=str(bundle), binaries=hashes,
                      source_pins_sha256=base.sha(output / 'source-pins.json'))
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        result['elapsed_seconds'] = time.time() - started
        base.save(output / 'result.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
