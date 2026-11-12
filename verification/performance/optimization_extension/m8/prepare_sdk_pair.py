#!/usr/bin/env python3
"""Prepare one bounded native SDK pair. This program cannot launch VCS."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import sys

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
HERE = ROOT/'verification/performance/optimization_extension/m8'
TOOLS = ROOT.parent/'ara/install/riscv-gcc/bin'
SPIKE = ROOT.parent/'riscv-isa-sim-ara-dsa-vstart/build/spike'
CAPTURE = OUT/'stage2_qwen3_rows8_20261109_02/attn_q'
HELPER = ROOT/'verification/performance/chain_profile/q6_decode/build.py'
IMAGE = OUT/'enablement_soc_extension_20261111_01'
CAPABILITY = OUT/'optimization_extension_capability_20261111_05'


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('m8_sdk_builder', HELPER)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    out, target = args.output.resolve(), args.target.resolve(strict=True)
    base.require(out.parent == OUT and out.name.startswith('optimization_extension_m8_') and not out.exists(), 'Fresh signoff output')
    receipt = json.loads((target/'result.json').read_text())
    base.require(receipt.get('state') == 'M8_GNU_SPIKE_CHECKED' and receipt.get('post_pins_match') and
        receipt.get('actual_repack_trait_executed_layout_sink_metadata_only'), 'Final producer/boundary/repack gate required')
    source_pins = json.loads((target/'source-pins.json').read_text())
    for path, digest in source_pins.items():
        base.require(base.digest(path) == digest, 'Final target input drift: '+path)
    out.mkdir()
    b = base.Builder(out)
    for path in (HELPER, Path(__file__), target/'result.json', target/'source-pins.json'):
        b.pin(path)
    for name, digest in (('result.json', '0f3ac84e7ada0c1398aeca58cf978d4336e0ae49a03fa47e1d97753bdc153376'),
                         ('terminal-audit.json', 'c2a1c89a81a2b515b5db29ea2fe99acd9c21048caa64f6e3462559fb1c0f201e')):
        base.require(base.digest(CAPABILITY/name) == digest, 'Authoritative capability receipt drift')
        b.pin(CAPABILITY/name)
    capability = json.loads((CAPABILITY/'result.json').read_text())
    image = json.loads((IMAGE/'build.json').read_text())
    base.require(capability['state'] == 'PASS' and image['post_image_match'] and image['post_pins_match'] and
        capability['native'][1]['actual'] == capability['native'][1]['decoded'] == 1 and
        capability['native'][1]['simv_sha256'] == image['image_pins'][image['simv']], 'Real cooperative image gate')
    b.pin(IMAGE/'build.json')
    for path, digest in image['image_pins'].items():
        base.require(base.digest(path) == digest, 'Image artifact drift: '+path)
        b.pin(path)
    inputs = out/'inputs'
    inputs.mkdir()
    for name in ('sdk_export.cpp', 'sdk_pair.cpp', 'sdk_oracle.c', 'sdk_check.py', 'sdk_check_test.py'):
        shutil.copyfile(HERE/name, inputs/name)
        b.pin(inputs/name)
    shutil.copytree(target/'inputs/ggml', inputs/'ggml')
    revision = b.run('sdk-revision', ['git', '-C', ROOT, 'rev-parse', 'HEAD']).decode().strip()
    sdk = inputs/'sdk'
    b.archive(ROOT, revision, ['apps/common', 'verification/qbs/qbs_ref.c', 'verification/qbs/qbs_ref.h',
        'software/qbs/src/qbs_native_riscv.c'], sdk)
    shutil.copytree(target/'inputs/sdk/software/qbs/include', sdk/'software/qbs/include')
    shutil.copyfile(target/'inputs/sdk/software/qbs/src/qbs_runtime.c', sdk/'software/qbs/src/qbs_runtime.c')
    for name in ('start.S', 'runtime.cpp', 'link.ld', 'data.S', 'attn_q.bin', 'ffn_gate.bin'):
        shutil.copyfile(target/'inputs'/name, inputs/name)
    # The exporter data assembly must refer only to this new frozen collection.
    (inputs/'data.S').write_text('.section .rodata\n.balign 64\n.global real_attn\nreal_attn:\n.incbin "'+
        str(inputs/'attn_q.bin')+'"\n')
    for path in inputs.iterdir():
        if path.is_file(): b.pin(path)
    meta = json.loads((CAPTURE/'operator.json').read_text())
    base.require(meta['activation_shape'] == [2048, 8] and meta['distinct_rows'] == 8 and
        base.digest(inputs/'attn_q.bin') == meta['activation_sha256'] and
        base.digest(CAPTURE/'weight_q4_K.bin') == meta['weight_sha256'], 'Real complete K2048 capture')
    shutil.copyfile(CAPTURE/'weight_q4_K.bin', inputs/'weight_q4_K.bin')
    b.pin(inputs/'weight_q4_K.bin')
    ggml = inputs/'ggml'
    cxx, cc = TOOLS/'riscv64-unknown-elf-g++', TOOLS/'riscv64-unknown-elf-gcc'
    flags = ['-O2', '-DNDEBUG', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
        '-msmall-data-limit=0', '-fno-fast-math', '-ffp-contract=off', '-ffunction-sections', '-fdata-sections',
        '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-DNR_LANES=4', '-DVLEN=1024']
    includes = ['-I'+str(p) for p in (inputs, sdk/'apps/common', sdk/'software/qbs/include', ggml/'include',
        ggml/'src', ggml/'src/ggml-cpu', ggml/'src/ggml-cpu/arch/riscv')]
    cpp = [*flags, '-std=c++17', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics',
        '-fno-stack-protector', '-DGGML_RISCV_ACCEL_AUTO=1', *includes]
    generic = out/'generic.o'
    shutil.copyfile(target/'generic.o', generic)
    b.pin(generic)
    objects = [generic]
    for source, name, extra in ((inputs/'sdk_export.cpp', 'export', []), (inputs/'runtime.cpp', 'runtime',
        ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns']), (inputs/'start.S', 'start', []),
        (inputs/'data.S', 'data', [])):
        obj = out/(name+'.o'); b.compile(cxx, [*cpp, *extra], source, obj); objects.append(obj)
    export = out/'export.elf'
    b.run('export-link', [cxx, *cpp, '-nostdlib', '-static', *objects, '-Wl,--gc-sections',
        '-Wl,--build-id=none', '-T', inputs/'link.ld', '-lgcc', '-o', export])
    b.pin(export)
    symbols = b.run('export-symbols', [TOOLS/'riscv64-unknown-elf-nm', '-n', export]).decode()

    def address(name):
        matches = re.findall(r'^([0-9a-f]+) \w '+name+'$', symbols, re.M)
        base.require(len(matches) == 1, 'Missing export symbol '+name)
        return int(matches[0], 16)

    work = out/'export'
    work.mkdir()
    command = work/'debug.cmd'
    command.write_text(f'until pc 0 {address("test_exit"):x}\nreg 0 a0\nstr {address("test_log"):x}\ndump\nrs\n')
    b.pin(command)
    log = b.run('export-spike', [SPIKE, '-d', '--debug-cmd='+str(command),
        '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m2', export], cwd=work).decode()
    base.require(log.count('M8_EXPORT_PASS') == 1 and 'FAIL' not in log and 'TRAP' not in log and
        len(re.findall(r'^0x0000000000000000$', log, re.M)) == 1, 'Producer export failed')
    dump = work/'mem.0x80000000.bin'
    ram = dump.read_bytes()
    base.require(len(ram) == 2*1024*1024, 'Wrong export memory extent')
    for name, length in (('export_m4', 8*8*292), ('export_m8', 8*8*292), ('export_flags', 4)):
        offset = address(name) - 0x80000000
        base.require(0 <= offset <= len(ram) - length, 'Export outside memory')
        (work/(name+'.bin')).write_bytes(ram[offset:offset+length]); b.pin(work/(name+'.bin'))
    data = out/'data'
    data.mkdir()
    host_flags = ['-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math',
        '-Wall', '-Wextra', '-Werror', '-I'+str(sdk/'verification/qbs')]
    for source, name in ((inputs/'sdk_oracle.c', 'oracle'), (sdk/'verification/qbs/qbs_ref.c', 'reference')):
        b.compile('/usr/bin/gcc', host_flags, source, out/(name+'.o'))
    host = out/'oracle-host'
    b.run('host-link', ['/usr/bin/gcc', out/'oracle.o', out/'reference.o', '-lm', '-o', host])
    b.run('host-oracle', [host, inputs/'attn_q.bin', inputs/'weight_q4_K.bin',
        work/'export_m4.bin', work/'export_m8.bin', data])
    shutil.copyfile(work/'export_flags.bin', data/'prep_flags.bin')
    config = inputs/'sdk_pair_config.h'
    build_id = base.digest(export)
    config.write_text('#define SDK_PAIR_ID "'+build_id+'"\n'); b.pin(config)
    assembly = inputs/'pair-data.S'
    assembly.write_text('.section .rodata\n'+''.join('.balign 64\n.global '+symbol+'\n'+symbol+':\n.incbin "'+str(data/name)+'"\n'
        for symbol, name in (('pair_input', 'input_f32.bin'), ('pair_weights', 'weights_r4.bin'),
            ('pair_m4', 'm4.bin'), ('pair_m8', 'm8.bin'), ('pair_expected', 'expected.bin'),
            ('pair_engine_flags', 'flags.bin'), ('pair_prep_flags', 'prep_flags.bin')))); b.pin(assembly)
    native_objects = [generic]
    sources = [(inputs/'sdk_pair.cpp', 'pair', cxx, cpp), (assembly, 'pair-data', cc, [*flags, *includes])]
    sources += [(sdk/'apps/common'/name, 'native-'+Path(name).stem, cc,
        [*flags, *includes, *(['-fno-builtin'] if name == 'string.c' else [])])
        for name in ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    sources += [(sdk/'software/qbs/src'/name, Path(name).stem, cc, [*flags, *includes])
        for name in ('qbs_runtime.c', 'qbs_native_riscv.c')]
    for source, name, compiler, options in sources:
        obj = out/(name+'.o'); b.compile(compiler, options, source, obj); native_objects.append(obj)
    link = out/'native-link.ld'
    b.pin(sdk/'apps/common/arch.link.ld')
    b.run('native-linker-script', [cc, '-E', '-P', '-x', 'c', '-DALIGNMENT=16', sdk/'apps/common/arch.link.ld', '-o', link])
    elf = out/'native-pair.elf'
    b.run('native-link', [cxx, *flags, '-static', '-nostartfiles', '-nostdlib', *native_objects,
        '-Wl,--gc-sections', '-Wl,-Map='+str(out/'native.map'), '-T', link,
        '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
    disassembly = b.run('native-disassembly', [TOOLS/'riscv64-unknown-elf-objdump', '-d', elf]).decode()
    base.require(all(op in disassembly for op in ('vfmacc.vf', 'vsse32.v', 'qbs_execute_with_options', 'qbs_native_execute_command')),
        'Actual fused producer/native SDK missing from ELF')
    b.run('checker-unit', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', inputs,
        '-p', 'sdk_check_test.py', '-v'])
    plan = dict(state='PREPARED_REQUIRES_PARENT_REVIEW_NOT_EXECUTED', launches=1, automatic_retry=False,
        image=str(IMAGE), simv=image['simv'], simv_sha256=image['image_pins'][image['simv']],
        elf=str(elf), elf_sha256=base.digest(elf), checker=str(inputs/'sdk_check.py'),
        capability_receipt=str(CAPABILITY/'result.json'), capability_audit=str(CAPABILITY/'terminal-audit.json'),
        trials=[4, 8, 8, 4], native_commands=8, complete_outputs_per_trial=256, payload_bytes_per_trial=18688,
        estimated_wall_minutes=[15, 30], simulation_timeout_seconds=3600, service_runtime_seconds=4500,
        direct_service_owner=True, service_type='exec', kill_mode='control-group', capture_stdout_stderr=True,
        confirm_simv_once_then_no_poll=True, fsdb=False, instruction_trace=False, qbs_perf=True,
        independent_protocol_required=['events', 'backend', 'axi', 'axi-write', 'no-exceptions', 'EOC', 'image-identity'],
        before_after_source_image_artifact_pins_required=True,
        roi='No reusable M4 cache/context; preparation+query+SDK planning+native execute+final fence',
        parent_review_required=True, full_model=False, FPGA_acceptance=False)
    base.write_json(out/'plan.json', plan); b.pin(out/'plan.json')
    for path in (elf, link, dump, host, out/'commands.json', *data.iterdir()): b.pin(path)
    for path, digest in b.pins.items(): base.require(base.digest(path) == digest, 'Build input drift: '+path)
    base.write_json(out/'source-pins.json', b.pins)
    base.write_json(out/'build.json', dict(state='BUILT_NOT_EXECUTED', post_pins_match=True,
        source_pins_sha256=base.digest(out/'source-pins.json'), elf=str(elf), elf_sha256=base.digest(elf),
        build_id=build_id, final_target=str(target), trials=[4, 8, 8, 4], flag_seeds=[0, 8, 0, 8],
        m=8, k=2048, n=32, commands=8, outputs_per_trial=256, activation_payload_bytes=18688,
        prep_flags=struct.unpack('<I', (data/'prep_flags.bin').read_bytes())[0],
        engine_flags=struct.unpack('<I', (data/'flags.bin').read_bytes())[0],
        real_input=meta, q8_equal_before_oracle=True, golden='Independent ordered C-ref on identical GNU M4/M8 payload',
        cache=False, context_replay=False, rowwise_pack=False, full_software_call=True, whole_model=False,
        performance_measured=False, rtl_executed=False, automatic_retry=False,
        plan_sha256=base.digest(out/'plan.json'),
        roi='Preparation+device query+SDK plan+native execute+final fence; no cold weight repack or cache reuse'))
    print('BUILT_NOT_EXECUTED '+str(out/'build.json'), flush=True)


if __name__ == '__main__':
    main()
