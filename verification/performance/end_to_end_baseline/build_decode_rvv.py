#!/usr/bin/env python3
"""Build the actual GGML RVV counterpart of the accepted real Decode slice.

This only builds software. It neither edits sealed sources nor launches EDA.
Q4 uses the production 32-output RVV GEMV and Q6 its VLEN-dispatched vec-dot.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, ROOT, VERIFY, RUNS
from run_projection_capture_v3 import GRAPH
from run_supply_sdk import PROGRAMS, bind
from run_wide_soc_smoke import elf_admission
from decode_rvv_data import pack_q4_r32, unpack_q4_r32

BASE = RUNS / PROGRAMS['decode'][0]
COMMON = RUNS / 'e2e_qwen3_projection_native_build_20261106_03'
NAMES = ('attn_q', 'attn_v', 'attn_k', 'ffn_gate', 'ffn_up', 'ffn_down', 'vocabulary')


def modified_recipe(template, source, target):
    result = list(template)
    require(result.count('-c') == result.count('-o') == 1, 'Expected a single compile command')
    result[result.index('-c') + 1] = str(source)
    result[result.index('-o') + 1] = str(target)
    require(not any('GGML_USE_RISCV_QBS' in value or 'GGML_CPU_GENERIC' in value for value in result),
            'RVV baseline may not select QBS or rename generic implementations')
    return result


def upstream_warning_recipe(command, recorded):
    actual = shlex.split(recorded)
    require(not any(word == '-Werror' or word.startswith('-Werror=') for word in actual),
            'Recorded upstream build did require warning errors')
    # Keep every optimization/ISA/math option. Do not promote upstream's
    # existing warnings to errors merely because the new driver uses -Werror.
    return [word for word in command if word != '-Werror']


def custom_instructions(data):
    """Scan executable ELF64 sections only, not packed weights in RWX PT_LOAD."""
    import struct
    require(data[:6] == b'\x7fELF\x02\x01', 'Expected little-endian ELF64')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    require(h[11] == 64 and h[12] > 0 and h[6]+h[11]*h[12] <= len(data), 'ELF section table')
    sites, executable = [], 0
    for i in range(h[12]):
        section = struct.unpack_from('<IIQQQQIIQQ', data, h[6]+i*64)
        if not section[2] & 4: continue
        address, offset, size = section[3:6]
        require(offset+size <= len(data) and size % 2 == 0, 'Executable section bounds')
        executable += size; end = offset+size; cursor = offset
        while cursor < end:
            half = int.from_bytes(data[cursor:cursor+2], 'little')
            step = 2 if half & 3 != 3 else 4
            require(cursor+step <= end and not (step == 4 and half & 31 == 31),
                    'Unexpected long/truncated instruction in baseline')
            if step == 4:
                word = int.from_bytes(data[cursor:cursor+4], 'little')
                if word & 127 in (0x0b, 0x2b, 0x5b, 0x7b): sites.append(address+cursor-offset)
            cursor += step
    require(executable > 0, 'No executable code')
    return sites


def main(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification build directory')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='PREPARING', performance_measured=False, runtime_accepted=False,
                  rtl_changed=False, production_library_changed=False, whole_model=False)
    env = {k: v for k,v in os.environ.items() if k not in (
        'LD_PRELOAD', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C')
    def pin(path, sha=None): bind(pins, path, sha)
    def run(argv, label):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv)); result['state'] = label.upper()
        (out / 'status.json').write_text(json.dumps(result, indent=2)+'\n')
        (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        child = subprocess.run(argv, cwd=out, env=env, capture_output=True, timeout=300)
        (out / (label+'.log')).write_bytes(child.stdout+child.stderr)
        require(child.returncode == 0, label+' failed; see '+str(out / (label+'.log')))
        return child.stdout.decode()
    try:
        pin(BASE / 'build.json', PROGRAMS['decode'][1])
        original = json.loads((BASE / 'build.json').read_text())
        require(original['state'] == PROGRAMS['decode'][2] and original['commands'] == 28 and
                original['m'] == 1 and original['n'] == 128, 'Decode comparison identity')
        pin(BASE / 'source-pins.json', original['source_pins_sha256'])
        inherited = json.loads((BASE / 'source-pins.json').read_text()); verify_pins(inherited)
        verify_pins(original['artifacts'])
        for name, sha in original['artifacts'].items(): pin(name, sha)
        pin(GRAPH / 'source-pins.json', inherited[str(GRAPH / 'source-pins.json')])
        archived = json.loads((GRAPH / 'source-pins.json').read_text())
        capture = Path(original['capture']); pin(capture / 'result.json', inherited[str(capture / 'result.json')])
        cr = json.loads((capture / 'result.json').read_text())
        require(cr['state'] == 'REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED' and cr['post_pins_match'], 'Decode capture')
        pin(capture / 'source-pins.json', cr['source_pins_sha256']); verify_pins(cr['artifacts'])
        weights = {Path(r['file']).stem: r for r in cr['weights']}
        require(set(weights) == set(NAMES), 'Native Decode weight inventory')
        symbols = {'decode_profiles': BASE / 'profiles.bin'}
        for s, name in enumerate(('attn_norm-0', 'ffn_norm-0', 'ffn_swiglu-0', 'result_norm')):
            symbols[f'decode_input_{s}'] = capture / (name+'_f32.bin')
            symbols[f'decode_quantized_{s}'] = BASE / f'activation_{s}.bin'
        for part, name in enumerate(NAMES):
            source = capture / (name+'.bin'); pin(source, weights[name]['sha256']); raw = source.read_bytes()
            if weights[name]['type'] == 'Q4_K':
                packed = pack_q4_r32(raw, 128, weights[name]['k'])
                require(unpack_q4_r32(packed, 128, weights[name]['k']) == raw, 'Q4 R32 repack changed model bytes')
            else:
                require(weights[name]['type'] == 'Q6_K', 'Unknown real weight profile'); packed = raw
            target = out / f'weight_{part}.bin'; target.write_bytes(packed); pin(target)
            symbols[f'decode_weights_{part}'] = target
            symbols[f'decode_expected_{part}'] = BASE / f'part_{part}_expected.bin'
        assembly = '.section .rodata\n'
        for symbol, path in symbols.items():
            pin(path, cr['artifacts'].get(str(path), original['artifacts'].get(str(path))))
            assembly += f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{path}"\n'
        data = out / 'data.S'; data.write_text(assembly); pin(data)
        for name in ('build_decode_rvv.py', 'decode_rvv.cpp', 'decode_rvv_platform.cpp',
                     'decode_rvv_data.py', 'test_decode_rvv_data.py', 'test_decode_rvv_source.py',
                     'test_build_decode_rvv.py', 'audit.py'):
            pin(HERE / name)
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(root) for root in (ROOT, VERIFY)):
                pin(path)
        compilation = GRAPH / 'build/compile_commands.json'; pin(compilation, archived[str(compilation)])
        production_commands = json.loads(compilation.read_text()); warning_policy = []
        records = json.loads((BASE / 'commands.json').read_text())
        recipes = {r['label']: r['argv'] for r in records}
        cpp = recipes['compile-0']; cc = recipes['compile-1']
        tools = {}
        for driver, names in ((cpp[0], ('cc1plus', 'as', 'collect2', 'ld')), (cc[0], ('cc1',))):
            for name in names:
                path = Path(run([driver, '-print-prog-name='+name], 'tool-'+name).strip()).resolve(strict=True)
                require(path.is_relative_to('/home/wangwy/openproject/ara/install/riscv-gcc'),
                        'Compiler subprogram outside accepted toolchain')
                pin(path); tools[name] = dict(path=str(path), sha256=digest(path))
        sources = ((HERE / 'decode_rvv.cpp', cpp), (HERE / 'decode_rvv_platform.cpp', cpp),
            (GRAPH / 'llama/ggml/src/ggml-cpu/arch/riscv/repack.cpp', cpp),
            (GRAPH / 'llama/ggml/src/ggml-cpu/repack.cpp', cpp),
            (GRAPH / 'llama/ggml/src/ggml-cpu/quants.c', cc), (data, cpp))
        objects = []
        for index, (source, template) in enumerate(sources):
            if source.is_relative_to(GRAPH): pin(source, archived[str(source)])
            obj = out / f'compiled-{index}.o'; cmd = modified_recipe(template, source, obj)
            if source.is_relative_to(GRAPH):
                selected = [r for r in production_commands if r['file'] == str(source)]
                require(len(selected) == 1 and 'command' in selected[0], 'Recorded upstream compile policy missing')
                cmd = upstream_warning_recipe(cmd, selected[0]['command'])
                warning_policy.append(dict(source=str(source), source_sha256=digest(source),
                    policy='Keep warnings visible, not errors, as in pinned GGML build; ISA/math/optimization unchanged'))
            dep = [v for i,v in enumerate(cmd) if i not in (cmd.index('-c'), cmd.index('-o'), cmd.index('-o')+1)]
            text = run([*dep, '-M', '-MT', 'object'], 'deps-'+str(index))
            for name in shlex.split(text.replace('\\\n', ' ').split(':', 1)[1]):
                path = Path(name).resolve(strict=True)
                if str(path) in pins: pin(path, pins[str(path)])
                elif str(path) in archived: pin(path, archived[str(path)])
                elif str(path) in inherited: pin(path, inherited[str(path)])
                else:
                    require(path.is_relative_to('/home/wangwy/openproject/ara/install/riscv-gcc') and
                            path.suffix in ('.h', '.tcc', '.inl', '.inc', ''), 'Unreviewed compiler dependency: '+str(path))
                    pin(path)
            run(cmd, 'compile-'+str(index)); pin(obj); objects.append(str(obj))
        quant = BASE / '1.o'; pin(quant, original['artifacts'][str(quant)]); objects.append(str(quant))
        # Reuse startup/UART/string/trap objects, never the QBS runtime/executor.
        for i in range(3, 9):
            obj = COMMON / f'{i}.o'; pin(obj, inherited[str(obj)]); objects.append(str(obj))
        link = [v for v in recipes['link'] if not v.endswith('.o')]
        elf = out / 'decode_rvv.elf'; link[link.index('-o')+1] = str(elf)
        link = ['-Wl,-Map='+str(out / 'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = objects
        pin(link[link.index('-T')+1], inherited[str(Path(link[link.index('-T')+1]).resolve())])
        libraries = {}
        for name in ('libstdc++.a', 'libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
            path = run([link[0], '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-print-file-name='+name], 'locate-'+name).strip()
            pin(path); libraries[str(Path(path).resolve(strict=True))] = digest(path)
        run(link, 'link'); pin(elf)
        linked = {str(Path(p).resolve(strict=True)) for p in re.findall(r'^LOAD (.+[.]a)$',
                   (out / 'link.map').read_text(), re.M)}
        require(linked == set(libraries), 'Actual linked runtime archive selection differs')
        dis = run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
        require(all('<'+n+'>:' in dis for n in ('ggml_gemv_q4_K_32x1_q8_K', 'ggml_vec_dot_q6_K_q8_K',
                'ggml_vec_dot_q6_K_q8_K_vl1024', 'quantize_row_q8_K')) and
                all('<'+n+'>:' not in dis for n in ('qbs_native_execute_command', 'qbs_ref_execute')),
                'Production RVV path missing or custom/reference executor leaked')
        require(not custom_instructions(elf.read_bytes()), 'Custom opcode leaked into RVV baseline')
        loads = {str(w): elf_admission(elf.read_bytes(), w//8) for w in (128, 256)}
        verify_pins(pins); (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        result.update(state='REAL_QWEN3_DECODE_RVV_BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=digest(elf),
            source_pins_sha256=digest(out / 'source-pins.json'), m=1, n=128, outputs=896, trials=1,
            parts=list(NAMES), k=original['k'], profiles=original['profiles'], preparation_stages=4,
            preparation_included=True, cold_weight_repack_included=False, no_custom_opcodes=True,
            preload_segments=loads, compiler_tools=tools, linked_archives=libraries,
            upstream_warning_policy=warning_policy,
            prior_attempts=[dict(run=str(RUNS / 'e2e_decode_rvv_build_20261106_01'),
                state='FAIL', source_commit='6ed7a6ae2', stage='compile-2',
                reason='Fixture -Werror applied to unrelated upstream repack kernels; original report retained')],
            numerical_oracle='Existing independent QBS C reference with declared RVV tolerance; '
                'not bit-exact RVV reference acceptance',
            limits=['Build only: runtime numerics, protocol, repeatability and timings remain unaccepted',
                    'Same real Decode prefixes/full K, not complete GGML or whole-model execution'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        (out / 'status.json').write_text(json.dumps(result, indent=2)+'\n')
        # Retain input identities on failure as well as success. A later build
        # must not erase which tool/source produced the original diagnostic.
        if not (out / 'source-pins.json').exists():
            (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        result['artifacts'] = {str(p): digest(p) for p in out.iterdir()
                               if p.is_file() and p.name not in ('status.json', 'build.json')}
        (out / 'build.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
