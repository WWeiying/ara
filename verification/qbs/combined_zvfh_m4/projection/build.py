"""Fresh bare-metal canonical-kernel/SDK projection build. Never launch a simulator."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
QBS = ROOT / 'verification/qbs'
sys.path.insert(0, str(QBS))
from run_half_scale_soc import atomic_json, digest, hashes
from build_q8k_projection_soc import check_data
from build_q8k_prepare_soc import extract
from prepare_q8k_projection_data import q4_values, q8_rows
from check import fnv, check_contract


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('Only projection/ outputs are permitted')
    out.mkdir(parents=True, exist_ok=False)
    data = ROOT / 'verification/out/qbs-q8k-projection-data-20261023-01'
    native = ROOT / 'verification/out/q8k-combined-native-20261026-01'
    candidate = ROOT / 'verification/out/q8k-combined-zvfh-compile-20261026-02'
    inherited, data_report = check_data(data)
    receipt = json.loads((candidate / 'result.json').read_text())
    pins = json.loads((candidate / 'inputs.json').read_text())
    if (receipt['state'] != 'COMPILE_ONLY_PASS' or receipt['effective_march'] != '-march=rv64gcv_zfh_zvfh' or
            receipt['object_sha256'] != digest(candidate / 'candidate.o') or
            receipt['inputs_sha256'] != digest(candidate / 'inputs.json') or hashes(map(Path, pins)) != pins):
        raise ValueError('Combined candidate source identity drift')
    accepted = json.loads((native / 'result.json').read_text())
    if accepted['state'] != 'PASS' or accepted['checks'] != 4000 or \
            accepted['log_sha256'] != digest(native / 'qemu.log') or \
            accepted['manifest_sha256'] != digest(native / 'manifest.json'):
        raise ValueError('Current combined numerical receipt drift')
    current_checker = HERE.parent / 'check_native.py'
    checked = module('combined_byte_checker', current_checker).check_output((native / 'qemu.log').read_text())
    if any(accepted[key] != value for key, value in checked.items()):
        raise ValueError('Current combined byte evidence no longer passes')

    ggml = Path('/home/wangwy/llama/llama.cpp/ggml')
    installed = ggml / 'src/ggml-cpu/arch/riscv/q8_K-m4.h'
    canonical = ROOT / 'software/qbs/ggml/q8_K-m4.h'
    if installed.read_bytes() != canonical.read_bytes():
        raise ValueError('Installed quantizer differs from canonical production header')
    accepted_pins = json.loads((native / 'manifest.json').read_text())
    for path in (candidate / 'candidate.o', installed, current_checker):
        if accepted_pins.get(str(path)) != digest(path):
            raise ValueError('Consumed source differs from accepted combined gate: ' + str(path))

    source = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators/blk_0_attn_q_weight')
    weights = (source / 'weight_q4_K.bin').read_bytes()
    raw = (source / 'activation_f32.bin').read_bytes()
    captured = (source / 'output_f32.bin').read_bytes()
    metadata = {name: json.loads((source / (name + '.json')).read_text())
                for name in ('weight_q4_K', 'activation_f32', 'output_f32')}
    for name, shape, strides, size in (
            ('weight_q4_K', [1536, 1536, 1, 1], [144, 864, 1327104, 1327104], 1327104),
            ('activation_f32', [1536, 15, 1, 1], [4, 6144, 92160, 92160], 92160),
            ('output_f32', [1536, 15, 1, 1], [4, 6144, 92160, 92160], 92160)):
        meta = metadata[name]
        if meta['shape'] != shape or meta['strides'] != strides or meta['nbytes'] != size or \
                meta['type'] != ('q4_K' if name == 'weight_q4_K' else 'f32') or \
                (source / (name + '.bin')).stat().st_size != size:
            raise ValueError('Real capture geometry drift: ' + name)
    activation = raw[:24576]
    golden = (data / 'activation_q8k_m4.bin').read_bytes()
    if activation != (data / 'activation_f32.bin').read_bytes():
        raise ValueError('Captured first four rows differ')
    ih, ph = fnv(activation), fnv(golden)
    bridge = (f'Q8K_COMBINED_CALL_PASS id=44 frm=0 env=0 ef=1 af=1 ev=0 av=0 '
              f'packedbytes=exact scales=exact bsums=exact input=exact canaries=exact '
              f'signedmax=0 fma=0 underflow=0 input_digest={ih} digest={ph}')
    if [line.strip() for line in (native / 'qemu.log').read_text().splitlines()
            if 'Q8K_COMBINED_CALL_PASS id=44 frm=0 env=0 ' in line] != [bridge, bridge]:
        raise ValueError('Preserved golden is not the accepted current OFF/ON real capture')

    # Regenerate the independent decoded oracle and R4 packing; no old kernel is compiled.
    acts = q8_rows(golden, 1536)
    expected = [0.0] * 6144
    max_drift = 0.0
    for n in range(1536):
        decoded = [v for block in range(6) for v in q4_values(weights[(n*6+block)*144:(n*6+block+1)*144])]
        for row in range(4):
            value = math.fsum(w*x for w, x in zip(decoded, acts[row]))
            old_output = struct.unpack_from('<f', captured, (row*1536+n)*4)[0]
            if not math.isfinite(value) or not math.isfinite(old_output) or \
                    abs(value-old_output) > 2e-3 + 2e-3*abs(old_output):
                raise ValueError('Independent oracle disagrees with captured GGML output')
            max_drift = max(max_drift, abs(value-old_output))
            expected[row*1536+n] = value
    r4 = b''.join(weights[((first+row)*6+block)*144:((first+row)*6+block+1)*144]
                  for first in range(0, 1536, 4) for block in range(6) for row in range(4))
    oracle = struct.pack('<6144f', *expected)
    if r4 != (data / 'weight_r4.bin').read_bytes() or oracle != (data / 'oracle_f32.bin').read_bytes():
        raise ValueError('Recomputed data differs from preserved independent artifacts')
    contract = dict(shape=[4, 1536, 1536], golden_fcsr=1, oracle_atol=2e-4, oracle_rtol=2e-5,
                    activation_bytes=7008, context_capacity=4672, wide=0, segment=256,
                    weight_integrity='before_after_abba_exact_vector_compare',
                    trial_weight_field='Pre-ABBA baseline hash, not an additional per-trial weight pass',
                    digests=dict(input=ih, weights=fnv(r4), packed=ph),
                    capture=str(source), rows=[0, 4], max_capture_drift=max_drift,
                    current_numerical_receipt=str(native / 'result.json'),
                    current_byte_bridge=bridge, order=['generic', 'canonical', 'canonical', 'generic'],
                    cache_policy='Original ABBA, no warm-up: first-call and steady trials reported separately',
                    included=['SDK plan construction/context admission', 'current production preparation kernel',
                              'SDK dispatch/descriptor creation', '48 native M4/N32/K6 commands',
                              '6144 output stores', 'cycle fences and CSR probes'],
                    excluded=['GGML allocator/graph/threadpool', 'GGML environment-cached selector',
                              'GGML weight repacking', 'capability queries', 'oracle/integrity checks',
                              'model loading and end-to-end inference'])
    check_contract(contract)
    atomic_json(out / 'contract.json', contract)
    for name, contents in (('activation_f32.bin', activation), ('activation_q8k_m4.bin', golden),
                            ('weight_r4.bin', r4), ('oracle_f32.bin', oracle)):
        (out / name).write_bytes(contents)
    (out / 'contract.h').write_text('#pragma once\n#define Q8K_GOLDEN_FCSR 1U\n' + ''.join(
        f'#define Q8K_{key.upper()}_DIGEST UINT64_C(0x{value})\n' for key, value in contract['digests'].items()))

    common = ROOT / 'apps/common'
    gcc = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
    cxx, objdump = (gcc.with_name('riscv64-unknown-elf-' + name) for name in ('g++', 'objdump'))
    pair_helper = ROOT / 'apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py'
    pair = module('projection_link_checks', pair_helper)
    startup = [common / name for name in ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    sdk = [ROOT / ('software/qbs/src/' + name) for name in ('qbs_runtime.c', 'qbs_native_riscv.c')]
    repack = candidate / 'ggml/src/ggml-cpu/repack.cpp'
    pins.update(inherited)
    pins.update(data_report['artifacts'])
    inputs = [*HERE.glob('*.py'), HERE / 'projection.cpp', canonical, installed, repack,
              data / 'data.json', data / 'manifest.json', native / 'result.json', native / 'qemu.log',
              native / 'manifest.json', current_checker, candidate / 'result.json', candidate / 'candidate.o',
              candidate / 'inputs.json', pair_helper, gcc.resolve(), cxx.resolve(), objdump.resolve(),
              *startup, *sdk, *common.glob('*.h'), common / 'arch.link.ld',
              *ggml.rglob('*.h'), *ROOT.glob('software/qbs/include/**/*.h'),
              *[QBS / name for name in ('build_q8k_projection_soc.py', 'build_q8k_prepare_soc.py',
                                        'prepare_q8k_projection_data.py', 'run_half_scale_soc.py')]]
    inputs += [Path(subprocess.check_output([gcc, '-print-file-name=' + name], text=True).strip()).resolve(strict=True)
               for name in ('libm.a', 'libgcc.a')]
    pins.update(hashes(inputs))
    atomic_json(out / 'inputs.json', pins)
    text = repack.read_text()
    nearest = extract(text, 'static inline int nearest_int(', '\n// Functions to create')
    generic = extract(text, '\nvoid ggml_quantize_mat_q8_K_4x1_ara_generic(',
                      '\nvoid ggml_quantize_mat_q8_0_4x4_generic(')
    generic_source = out / 'generic.cpp'
    generic_source.write_text('#include "arch/riscv/q8_K-m4.h"\n' + nearest + '\nextern "C" {\n' + generic + '\n}\n')
    assembly = out / 'data.S'
    asm = '.section .rodata\n'
    for symbol, name, guard in (('projection_input', 'activation_f32.bin', 'input'),
                                ('projection_weights', 'weight_r4.bin', 'weights'),
                                ('projection_weights_reference', 'weight_r4.bin', None),
                                ('projection_golden', 'activation_q8k_m4.bin', None),
                                ('projection_oracle', 'oracle_f32.bin', None)):
        asm += '.balign 64\n'
        if guard:
            asm += f'.global {guard}_before\n{guard}_before:\n.fill 64,1,0xa5\n'
        asm += f'.global {symbol}\n{symbol}:\n.incbin "{out / name}"\n'
        if guard:
            asm += f'.global {guard}_after\n{guard}_after:\n.fill 64,1,0xa5\n'
    assembly.write_text(asm)
    link = out / 'link.ld'
    link.write_text((common / 'arch.link.ld').read_text().replace('ALIGNMENT', '16').replace(
        'LENGTH = 0x00100000', 'LENGTH = 0x01000000'))
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-O3', '-DNDEBUG',
             '-fno-fast-math', '-ffunction-sections', '-fdata-sections', '-DNR_LANES=4', '-DVLEN=1024',
             *['-I' + str(path) for path in (common, out, ROOT / 'apps/include', ROOT / 'software/qbs/include')],
             *[flag for path in (ggml / 'include', ggml / 'src', ggml / 'src/ggml-cpu')
               for flag in ('-isystem', str(path))]]
    commands, objects = [], []

    def run(command, label):
        command = list(map(str, command))
        commands.append(command)
        atomic_json(out / 'commands.json', commands)
        with (out / (label + '.log')).open('x') as stream:
            subprocess.run(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)

    for index, path in enumerate([HERE / 'projection.cpp', generic_source, assembly, *startup, *sdk]):
        cpp = path.suffix == '.cpp'
        extra = ['-std=gnu++17', '-fno-exceptions', '-fno-rtti'] if cpp else ['-std=gnu11']
        extra += ['-ffp-contract=fast' if path == generic_source else '-ffp-contract=off']
        if path in (HERE / 'projection.cpp', generic_source, *sdk):
            extra += ['-Wall', '-Wextra', '-Werror']
        if path == common / 'string.c':
            extra += ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns']
        obj = out / f'{index}.o'
        run([cxx if cpp else gcc, *flags, *extra, '-c', path, '-o', obj], f'compile-{index}')
        if path == common / 'string.c':
            pair.check_libc_calls(subprocess.check_output([objdump, '-dr', obj], text=True))
        objects.append(obj)
    elf = out / 'qbs_current_projection_soc'
    run([gcc, *flags, '-static', '-nostartfiles', '-nostdlib', *objects, '-Wl,--gc-sections',
         '-Wl,-Map=' + str(out / 'link.map'), '-T', link, '-lm', '-lgcc', '-o', elf], 'link')
    sections = pair.allocated_sections(elf)
    if min(s['address'] for s in sections) < 0x80000000 or \
            max(s['address'] + s['bytes'] for s in sections) > 0x81000000 - 65536:
        raise ValueError('ELF memory range')
    run([objdump, '-d', elf], 'disassembly')
    run([objdump, '-d', '--disassemble=ggml_quantize_mat_q8_K_4x1_ara_generic', elf], 'generic-disassembly')
    disasm = (out / 'disassembly.log').read_text()
    if 'fmadd.s' not in (out / 'generic-disassembly.log').read_text() or \
            not all(op in disasm for op in ('vfmacc.vf', 'vsse8.v', 'vredmaxu.vs', 'vredminu.vs')):
        raise ValueError('Production FMA/VLA quantizer instructions absent')
    if 'qbs_plan_create_segmented_r4' not in disasm or 'qbs_native_execute_command' not in disasm:
        raise ValueError('SDK planner/executor not linked')
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Build input drift')
    pins.update(hashes(path for path in out.iterdir() if path.is_file()))
    atomic_json(out / 'manifest.json', pins)
    atomic_json(out / 'build.json', dict(state='READY', execution='NOT_RUN',
        manifest_sha256=digest(out / 'manifest.json'), elf_sha256=digest(elf), sections=sections,
        canonical_sha256=digest(canonical), combined_candidate_sha256=receipt['object_sha256'],
        scope='Complete current-production-kernel + SDK planner/executor projection slice; not full GGML',
        exclusions=contract['excluded'], current_rtl_execution='PARENT_APPROVAL_REQUIRED'))
    print(json.dumps(dict(state='READY', execution='NOT_RUN', output=str(out))))


if __name__ == '__main__':
    main()
