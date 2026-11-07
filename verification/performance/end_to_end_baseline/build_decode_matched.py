#!/usr/bin/env python3
"""Build, never execute, a frozen same-ELF RVV/SDK Decode ABBA experiment."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, ROOT, VERIFY, RUNS
from collect_decode_rvv_build import BASE, BUILD, BUILD_SHA, ELF_SHA, COMMON, NAMES
from build_decode_rvv import modified_recipe, custom_instructions
from run_supply_sdk import PROGRAMS, bind
from run_wide_soc_smoke import elf_admission
from decode_rvv_data import pack_q4_r32

RVV_AUDIT = RUNS / 'e2e_decode_rvv_build_audit_20261106_01'
RVV_AUDIT_SHA = 'a5301ebbbfc665fea08563b28b5a8095e29909bc67457acbfdc313e215938124'
ISA = RUNS / 'e2e_decode_rvv_isa_20261106_03'
ISA_SHA = 'ee50533a21dfa06092a352582d552a4bb64f00eb823cc2442128966fdf5c4944'
DRIVER = HERE / 'decode_matched.cpp'
TOOLCHAIN = Path('/home/wangwy/openproject/ara/install/riscv-gcc')
K = (2048, 2048, 2048, 2048, 2048, 6144, 2048)
PROFILES = (1, 2, 1, 1, 1, 2, 2)
CUSTOM_OWNERS = ('qbs_native_info', 'qbs_native_execute_command')
N = 64
CAPTURED_N = 128


def labelled(records, label):
    selected = [record['argv'] for record in records if record['label'] == label]
    require(len(selected) == 1, 'Missing/duplicate producer command: ' + label)
    return list(selected[0])


def objects(command):
    result = [word for word in command if word.endswith('.o')]
    require(len(result) == len(set(result)), 'Duplicate linked object')
    return result


def reused_objects(rvv_link, sdk_link):
    rvv, sdk = objects(rvv_link), objects(sdk_link)
    expected_rvv = [str(BUILD / f'compiled-{i}.o') for i in range(6)] + [str(BASE / '1.o')] + [
        str(COMMON / f'{i}.o') for i in range(3, 9)]
    expected_sdk = [str(COMMON / f'{i}.o') for i in range(3, 11)] + [str(BASE / f'{i}.o') for i in range(3)]
    require(rvv == expected_rvv and sdk == expected_sdk, 'Unreviewed producer object inventory/order')
    retained = [word for word in rvv if word != str(BUILD / 'compiled-0.o')]
    additions = [str(COMMON / f'{i}.o') for i in range(3, 11) if str(COMMON / f'{i}.o') not in retained]
    require(additions == [str(COMMON / '9.o'), str(COMMON / '10.o')], 'Unexpected SDK object additions')
    return retained + additions


def matched_link(rvv_link, sdk_link, driver, data, elf, linkmap):
    reused = reused_objects(rvv_link, sdk_link)
    require(rvv_link.count('-o') == 1 and rvv_link.count('-Wl,--gc-sections') == 1 and
            sum(word.startswith('-Wl,-Map=') for word in rvv_link) == 1, 'Unsupported link recipe')
    result = [str(driver) if word == str(BUILD / 'compiled-0.o') else word for word in rvv_link]
    result[result.index('-o') + 1] = str(elf)
    result = ['-Wl,-Map=' + str(linkmap) if word.startswith('-Wl,-Map=') else word for word in result]
    position = result.index('-Wl,--gc-sections')
    result[position:position] = [str(data), *reused[-2:]]
    require(set(objects(result)) == set(reused + [str(driver), str(data)]) and len(objects(result)) == 16,
            'Matched link duplicated or lost an object')
    return result


def compile_recipe(template, source, target):
    required = ('-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
                '-O3', '-fno-fast-math', '-ffp-contract=off', '-Werror')
    require(all(flag in template for flag in required), 'Unaccepted strict driver ISA/math recipe')
    return modified_recipe(template, source, target)


def data_symbols():
    return ([(f'native_decode_weights_{p}', BASE / f'part_{p}_r4.bin') for p in range(7)] +
            [(f'rvv_decode_expected_{p}', ISA / f'isa_output_{p}.bin') for p in range(7)] +
            [('decode_flags', BASE / 'flags.bin')])


def assembly(symbols):
    require([name for name, path in symbols] == [name for name, path in data_symbols()],
            'Only the 15 additional matched symbols are permitted')
    result = '.section .rodata\n'
    for name, path in symbols:
        require(Path(path).is_absolute() and not any(c in str(path) for c in ('"', '\\', '\n', '\r')),
                'Unsafe assembly payload path')
        result += f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n'
    return result


def oracle_sources():
    return ({f'native_{p}.bin': BASE / f'part_{p}_expected.bin' for p in range(7)} |
            {f'rvv_{p}.bin': ISA / f'isa_output_{p}.bin' for p in range(7)} |
            {f'activation_{s}.bin': BASE / f'activation_{s}.bin' for s in range(4)} |
            {'flags.bin': BASE / 'flags.bin'})


def checked_flags(data):
    require(len(data) == 28, 'Invalid native flags length')
    flags = struct.unpack('<7I', data)
    require(all(flag in (0, 1) for flag in flags), 'N64 subset requires flags containing only zero/NX')
    return list(flags)


def oracle_payload(name, data):
    if re.fullmatch(r'(?:native|rvv)_[0-6]\.bin', name):
        require(len(data) == CAPTURED_N * 4, 'Expected complete N128 source oracle')
        return data[:N * 4]
    if name == 'flags.bin':
        checked_flags(data)
    else:
        match = re.fullmatch(r'activation_([0-3])\.bin', name)
        require(match and len(data) == (7008 if match[1] == '2' else 2336), 'Invalid activation oracle')
    return data


def copy_oracles(output, pins):
    output.mkdir(exist_ok=False)
    copied = {}
    for name, source in oracle_sources().items():
        key = str(source.resolve(strict=True))
        require(key in pins, 'Unpinned independent checker input: ' + key)
        bind(pins, source, pins[key])
        raw = source.read_bytes()
        payload = oracle_payload(name, raw)
        expected_sha = hashlib.sha256(payload).hexdigest()
        target = output / name
        target.write_bytes(payload)
        require(target.read_bytes() == payload and source.read_bytes() == raw and digest(target) == expected_sha,
                'Independent checker prefix/copy differs from source')
        bind(pins, source, pins[key]); bind(pins, target, expected_sha)
        copied[name] = dict(source=key, source_sha256=pins[key], source_bytes=len(raw),
                            copy=str(target), sha256=expected_sha, bytes=len(payload), source_offset=0)
    return copied


def pack_r4_for_prefix_proof(data, n, k, profile):
    """Host byte permutation only, checking the pinned reference's R4 indexing."""
    require(type(n) is int and type(k) is int and n > 0 and n % 4 == 0 and k > 0 and k % 256 == 0 and
            profile in (1, 2), 'Invalid R4 prefix proof geometry')
    block_bytes, blocks = (144 if profile == 1 else 210), k // 256
    require(len(data) == n * blocks * block_bytes, 'R4 proof payload length')
    result = bytearray(len(data))
    for row in range(n):
        for block in range(blocks):
            source = (row * blocks + block) * block_bytes
            target = ((row // 4 * blocks + block) * 4 + row % 4) * block_bytes
            result[target:target + block_bytes] = data[source:source + block_bytes]
    return bytes(result)


def descriptor_prefix_ranges():
    """Expected semantic ranges; actual runtime descriptors remain to be checked."""
    ranges = []
    for trial in (1, 2):
        for part, (k, profile) in enumerate(zip(K, PROFILES)):
            row_bytes = (k // 256) * (144 if profile == 1 else 210)
            for first in range(0, N, 32):
                ranges.append(dict(trial=trial, part=part, n=32, output_start=first, k_blocks=k // 256,
                    weight_offset_bytes=first * row_bytes, weight_bytes=32 * row_bytes,
                    admitted_weight_bytes=N * row_bytes))
    return ranges


def verify_prefixes(sdk, pins):
    def payload(path):
        key = str(path.resolve(strict=True))
        require(key in pins, 'Unpinned prefix proof input: ' + key)
        bind(pins, path, pins[key])
        return path.read_bytes()

    reference = ROOT / 'verification/qbs/qbs_ref.c'
    source = ' '.join(payload(reference).decode().split())
    for statement in ('qbs_ref_status_t qbs_ref_repack_weight_r4(',
                      'for (unsigned row = 0; row < n; ++row)',
                      'for (unsigned block = 0; block < k_blocks; ++block)',
                      'const size_t source_index = (size_t)row * k_blocks + block;',
                      '((size_t)(row / 4u) * k_blocks + block) * 4u + row % 4u;'):
        require(statement in source, 'Pinned R4 reference indexing changed')
    capture = Path(sdk['capture'])
    parts = []
    for part, (name, k, profile) in enumerate(zip(NAMES, K, PROFILES)):
        raw = payload(capture / (name + '.bin'))
        expected_bytes = CAPTURED_N * (k // 256) * (144 if profile == 1 else 210)
        require(len(raw) == expected_bytes, 'Captured prefix geometry differs')
        half = N * expected_bytes // CAPTURED_N
        rvv = payload(BUILD / f'weight_{part}.bin')
        r4 = payload(BASE / f'part_{part}_r4.bin')
        require(pack_r4_for_prefix_proof(raw, CAPTURED_N, k, profile) == r4 and
                pack_r4_for_prefix_proof(raw[:half], N, k, profile) == r4[:half],
                'N64 R4 prefix differs from accepted native packing')
        if profile == 1:
            require(pack_q4_r32(raw, CAPTURED_N, k) == rvv and
                    pack_q4_r32(raw[:half], N, k) == rvv[:half], 'N64 R32 prefix differs from accepted RVV packing')
        else:
            require(rvv == raw, 'Q6 native RVV weights changed')
        parts.append(dict(part=part, captured_n=CAPTURED_N, n=N, k=k, native_bytes=expected_bytes,
                          prefix_bytes=half, r4_prefix_sha256=hashlib.sha256(r4[:half]).hexdigest(),
                          rvv_prefix_sha256=hashlib.sha256(rvv[:half]).hexdigest(), prefix_equal=True))
    return dict(qbs_ref_source_sha256=pins[str(reference.resolve())], parts=parts,
                expected_native_descriptor_ranges=descriptor_prefix_ranges(),
                scope='Host byte-layout/range proof only; no descriptor execution or timing acceptance')


def inherit(pins, root, filename, expected_sha, expected_state):
    bind(pins, root / filename, expected_sha)
    report = json.loads((root / filename).read_text())
    require(report['state'] == expected_state, 'Unaccepted producer state: ' + str(root))
    bind(pins, root / 'source-pins.json', report['source_pins_sha256'])
    for path, sha in json.loads((root / 'source-pins.json').read_text()).items(): bind(pins, path, sha)
    for path, sha in report.get('artifacts', {}).items(): bind(pins, path, sha)
    return report


def dependency_allowed(path, accepted, generated):
    key = str(Path(path).resolve(strict=True))
    if key in generated or key == str(DRIVER.resolve()):
        require(key in accepted or key in generated, 'Unpinned new compilation source: ' + key)
        return key
    require(key in accepted and Path(key).suffix in ('.h', '.hpp', '.hh', '.hxx', '.tcc', '.inl', '.inc', '.def', ''),
            'Unaccepted new driver header dependency: ' + key)
    return key


def symbol_bodies(text):
    labels = list(re.finditer(r'(?m)^([0-9a-f]+) <([^>]+)>:$', text))
    require(labels and len({m[2] for m in labels}) == len(labels), 'Missing/duplicate disassembly labels')
    return {m[2]: text[m.end():labels[i + 1].start() if i + 1 < len(labels) else len(text)]
            for i, m in enumerate(labels)}


def custom_signature(data, disassembly):
    sites = custom_instructions(data)
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, header[6] + i * 64) for i in range(header[12])]
    labels = [(int(m[1], 16), m[2]) for m in re.finditer(r'(?m)^([0-9a-f]+) <([^>]+)>:$', disassembly)]
    require(labels == sorted(labels) and len({a for a, n in labels}) == len(labels), 'Invalid symbol address order')
    signature = Counter()
    for address in sites:
        containing = [s for s in sections if s[2] & 4 and s[3] <= address and address + 4 <= s[3] + s[5]]
        require(len(containing) == 1, 'Ambiguous custom instruction section')
        section = containing[0]
        word = struct.unpack_from('<I', data, section[4] + address - section[3])[0]
        owners = [name for start, name in labels if start <= address]
        require(owners and owners[-1] in CUSTOM_OWNERS, 'Custom opcode outside accepted native SDK functions')
        signature[owners[-1], word] += 1
    require({owner for owner, word in signature} == set(CUSTOM_OWNERS), 'Missing native SDK custom instruction family')
    return signature


def check_disassembly(text):
    bodies = symbol_bodies(text)
    clone = 'ggml_vec_dot_q6_K_q8_K_vl1024.isra.0'
    required = ('_start', '_eoc', 'main', 'ggml_gemv_q4_K_32x1_q8_K', 'ggml_vec_dot_q6_K_q8_K',
                clone, 'quantize_row_q8_K', 'qbs_device_query', 'qbs_plan_create',
                'qbs_execute_with_options', *CUSTOM_OWNERS)
    require(all(name in bodies for name in required) and 'qbs_ref_execute' not in bodies,
            'Genuine RVV/SDK symbols missing or reference executor leaked')
    require([name for name in bodies if name.startswith('ggml_vec_dot_q6_K_q8_K_vl1024')] == [clone],
            'Unreviewed Q6 clone identity')
    wrapper = bodies['ggml_vec_dot_q6_K_q8_K']
    require(re.search(r'\bcsrr\s+\w+,vlenb\b', wrapper) and re.search(r'\bli\s+\w+,1024\b', wrapper) and
            re.search(r'\b(?:jr|j|jal|jalr)\b[^\n]*<' + re.escape(clone) + r'>', wrapper) and
            all(op in bodies[clone] for op in ('\tvsetvli', '\tvle8.v', '\tvwmul.vv')),
            'Q6 VLEN1024 vector dispatcher changed')
    for pattern in (r'\bcsrwi\s+fcsr,8\b', r'\bcsrwi\s+vcsr,5\b', r'\bcsrwi\s+vstart,0\b',
                    r'\bfrcsr\b', r'\bcsrr\s+\w+,vcsr\b', r'\bcsrr\s+\w+,vstart\b', r'\brdcycle\b'):
        require(re.search(pattern, text), 'Initial/completed CSR or timing instruction missing: ' + pattern)
    require(all(op in bodies['qbs_native_execute_command'] for op in ('\tfence', '\tvsetvli', '\tvse32.v')) and
            re.search(r'\bsd\s+a0,', bodies['_eoc']), 'SDK result/completion path missing')
    return list(required)


def main(output, driver_sha256):
    require(re.fullmatch(r'[0-9a-f]{64}', driver_sha256 or ''), 'Explicit frozen driver SHA-256 required')
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification build required')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='PREPARING', runtime_accepted=False, performance_measured=False,
                  rtl_executed=False, production_library_changed=False)
    env = {k: v for k, v in os.environ.items() if k not in (
        'LD_PRELOAD', 'LD_LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
        'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')

    def run(argv, label):
        argv = list(map(str, argv)); bind(pins, argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv, timeout_seconds=300))
        result['state'] = label.upper()
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        try:
            process = subprocess.run(argv, cwd=out, env=env, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            (out / (label + '.log')).write_bytes((exc.stdout or b'') + (exc.stderr or b''))
            raise
        (out / (label + '.log')).write_bytes(process.stdout + process.stderr)
        commands[-1]['returncode'] = process.returncode
        require(process.returncode == 0, label + ' failed; preserve ' + str(out))
        verify_pins(pins)
        return process.stdout.decode()

    try:
        rvv = inherit(pins, RVV_AUDIT, 'result.json', RVV_AUDIT_SHA,
                      'REAL_QWEN3_DECODE_RVV_BUILD_REAUDITED_NOT_EXECUTED')
        isa = inherit(pins, ISA, 'result.json', ISA_SHA, 'EXACT_ELF_RVV_SPIKE_REFERENCE_PASS')
        sdk = inherit(pins, BASE, 'build.json', PROGRAMS['decode'][1], PROGRAMS['decode'][2])
        require(BASE == RUNS / PROGRAMS['decode'][0] and rvv['post_pins_match'] and isa['post_pins_match'] and
                rvv['elf_sha256'] == isa['elf_sha256'] == ELF_SHA and isa['independent_isa_output_words'] == 896 and
                isa['csr_records'] == 11, 'RVV build/ISA roots differ')
        require((sdk['m'], sdk['n'], sdk['commands'], sdk['outputs'], sdk['trials']) == (1, 128, 28, 896, 1) and
                tuple(sdk['k']) == K and tuple(sdk['profiles']) == PROFILES and sdk['existing_context_reuse'],
                'SDK workload differs')
        bind(pins, BUILD / 'build.json', BUILD_SHA)
        bind(pins, DRIVER, driver_sha256)
        for name in ('build_decode_matched.py', 'test_decode_matched_build.py'): bind(pins, HERE / name)
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(r) for r in (ROOT, VERIFY)):
                bind(pins, path)
        bind(pins, sys.executable)
        accepted_dependencies = dict(pins)
        symbols = data_symbols()
        for name, path in symbols:
            key = str(path.resolve(strict=True)); require(key in pins, 'Unpinned assembly input')
            bind(pins, path, pins[key])
        for p in range(7):
            require((ISA / f'isa_output_{p}.bin').read_bytes().hex() == isa['measured']['outputs_hex'][p] and
                    (ISA / f'isa_output_{p}.bin').stat().st_size == 512 and
                    (BASE / f'part_{p}_r4.bin').stat().st_size == 128 * (K[p] // 256) * (144 if PROFILES[p] == 1 else 210),
                    'ISA output/native weight geometry differs')
        native_flags = checked_flags((BASE / 'flags.bin').read_bytes())
        prefix_proof = verify_prefixes(sdk, pins)
        copies = copy_oracles(out / 'oracle', pins)
        data = out / 'data.S'; data.write_text(assembly(symbols)); bind(pins, data)
        rvv_records = json.loads((BUILD / 'commands.json').read_text())
        sdk_records = json.loads((BASE / 'commands.json').read_text())
        rvv_link, sdk_link = labelled(rvv_records, 'link'), labelled(sdk_records, 'link')
        reused = reused_objects(rvv_link, sdk_link)
        for path in reused:
            key = str(Path(path).resolve(strict=True)); require(key in pins, 'Unpinned reused object')
            bind(pins, path, pins[key])
        template = labelled(sdk_records, 'compile-0')
        rvv_template = labelled(rvv_records, 'compile-0')
        codegen_flags = lambda command: [v for v in command if v.startswith(('-m', '-f', '-O', '-std=', '-D'))]
        require(codegen_flags(template) == codegen_flags(rvv_template), 'RVV/SDK driver code-generation flags differ')
        for name in ('cc1plus', 'as', 'collect2', 'ld'):
            path = Path(run([template[0], '-print-prog-name=' + name], 'tool-' + name).strip()).resolve(strict=True)
            require(path.is_relative_to(TOOLCHAIN) and str(path) in accepted_dependencies,
                    'Compiler subprogram outside accepted inventory')
            bind(pins, path, accepted_dependencies[str(path)])
        driver_object, data_object = out / 'driver.o', out / 'data.o'
        for index, (source, target) in enumerate(((DRIVER, driver_object), (data, data_object))):
            command = compile_recipe(template, source, target)
            dep = [v for i, v in enumerate(command) if i not in (
                command.index('-c'), command.index('-o'), command.index('-o') + 1)]
            text = run([*dep, '-M', '-MT', 'object'], 'deps-' + str(index))
            for path in shlex.split(text.replace('\\\n', ' ').split(':', 1)[1]):
                key = dependency_allowed(path, accepted_dependencies, {str(data.resolve())})
                bind(pins, path, pins[key])
            run(command, 'compile-' + str(index)); bind(pins, target)
        elf = out / 'decode_matched.elf'
        link = matched_link(rvv_link, sdk_link, driver_object, data_object, elf, out / 'link.map')
        run(link, 'link'); bind(pins, elf)
        libraries = {str(Path(p).resolve(strict=True)): sha for p, sha in rvv['linked_archives'].items()}
        linked = {str(Path(p).resolve(strict=True)) for p in re.findall(
            r'^LOAD (.+[.]a)$', (out / 'link.map').read_text(), re.M)}
        require(len(libraries) == 5 and linked == set(libraries), 'Actual runtime archives differ')
        for path, sha in libraries.items(): bind(pins, path, sha)
        disassembly = run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
        required_symbols = check_disassembly(disassembly)
        signature = custom_signature(elf.read_bytes(), disassembly)
        baseline_signature = custom_signature(Path(sdk['elf']).read_bytes(), (BASE / 'disassembly.log').read_text())
        require(signature == baseline_signature, 'SDK custom opcode identity/count differs')
        loads = {str(width): elf_admission(elf.read_bytes(), width // 8) for width in (128, 256)}
        verify_pins(pins)
        result.update(state='REAL_DECODE_MATCHED_ABBA_BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=digest(elf),
            driver_sha256=driver_sha256, order=[0, 1, 1, 0], backends={'0': 'RVV', '1': 'SDK'},
            native_commands=28, native_commands_per_trial=14, outputs=1792, outputs_per_trial=448,
            m=1, n=N, captured_n=CAPTURED_N, k=list(K), parts=list(NAMES), full_k=True,
            full_n=False, full_ggml=False, whole_model=False, trials=4, preparation_included=True,
            cold_weight_repack_included=False, initial_fcsr=8, initial_vcsr=5, initial_vstart=0,
            rvv_build_audit_sha256=RVV_AUDIT_SHA, isa_reference_result_sha256=ISA_SHA,
            sdk_build_sha256=PROGRAMS['decode'][1], reused_objects={p: pins[str(Path(p).resolve())] for p in reused},
            rebuilt_objects=[str(driver_object), str(data_object)], linked_archives=libraries,
            oracle_copies=copies, prefix_proof=prefix_proof, native_flags=native_flags,
            required_symbols=required_symbols, preload_segments=loads,
            runtime_budget=dict(reason='Bounded same-ELF ABBA execution; reduce N only, preserve all K and captured inputs',
                observed_old_n128_rate_cycles_per_second=400, old_n128_runs_modified=False,
                retained_parts=7, preparation_stages_per_trial=4, arithmetic_objects_recompiled=False),
            custom_opcodes=[dict(owner=owner, word=f'{word:08x}', count=count)
                            for (owner, word), count in sorted(signature.items())], post_pins_match=True,
            limits=['Build only; runtime correctness, exact ISA output/state and performance not accepted',
                    'Only new driver/data compiled; original RVV, quantizer and native SDK objects reused',
                    'Native QBS reference and exact-ELF ISA goldens are separate numerical contracts',
                    'N64 output prefixes only; all payload objects retain original N128 bytes and full K'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        result['artifacts'] = {str(path): digest(path) for path in sorted(out.rglob('*'))
                               if path.is_file() and path.name not in ('status.json', 'build.json')}
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
        (out / 'build.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--driver-sha256', required=True, help='Main-reviewed frozen decode_matched.cpp SHA-256')
    args = parser.parse_args()
    main(args.output, args.driver_sha256)
