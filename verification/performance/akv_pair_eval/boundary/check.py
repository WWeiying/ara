#!/usr/bin/env python3
"""Functional/path gates for the four derived Qwen2.5 boundaries, never timing acceptance."""
import argparse
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('akv_boundary_contract', HERE / 'build.py')
contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contract)
require, sha, read_json = contract.require, contract.sha, contract.read_json
FULL, REFILL, RELEASE = 0x00b5605b, 0x02a0605b, 0x0000505b
COLUMN, COLUMN9, PANEL = 0x0005745b, 0x000574db, 0x0205745b
ROW64, ROW96, ROW128, ROW128_GQA6 = 0x0005345b, 0x0405345b, 0x0205345b, 0x0205375b
SIGNATURE_NAMES = {FULL: 'full', REFILL: 'refill', RELEASE: 'release',
                   COLUMN: 'column_v8', COLUMN9: 'column_v9', PANEL: 'panel4',
                   ROW64: 'row_d64', ROW96: 'row_d96', ROW128: 'row_d128',
                   ROW128_GQA6: 'row_d128_gqa6'}
EXPECTED_COUNTS = dict(full=12, refill=3, release=12, column_v8=2496, column_v9=192,
                       panel4=96, row_d64=8, row_d96=520, row_d128=320, row_d128_gqa6=21)
FUNCTION_WORDS = {
    'akv_native_info': [0x0005455b],
    'akv_attention_execute_v2_with_features_native': [FULL, REFILL, RELEASE],
    'akv_experimental_qk_f16_pair_panel4': [PANEL],
    'akv_experimental_pv_f16_pair': [ROW64, ROW96, ROW128],
    'akv_v2_compute_scores_f16_generic': [COLUMN],
    'akv_v2_update_outputs_f16_generic': [ROW64, ROW96, ROW128],
    'akv_v2_compute_scores_f16_d128_gqa6': [COLUMN, COLUMN9],
    'akv_v2_update_outputs_f16_d128_gqa6': [ROW128_GQA6],
}


def load_legacy(inputs):
    """Load the exact original checker and its complete import closure in isolation."""
    inputs = Path(inputs)
    paths = ['verification/qbs/run_half_scale_soc.py', 'verification/qbs/run_tile_context_engine.py',
             'verification/akv/run_refill_overlap_probe.py', 'verification/akv/run_qk_panel4_abba.py',
             'verification/akv/paired_heads/attention_run.py',
             'verification/akv/paired_heads/native_runtime_check.py']
    saved_path = sys.path[:]
    saved = {Path(p).stem: sys.modules.get(Path(p).stem) for p in paths}
    try:
        for name in paths:
            path = inputs / name
            source = path.read_bytes()
            require(contract.hashlib.sha256(source).hexdigest() == contract.LEGACY[name],
                    'Legacy helper identity: ' + name)
            module = types.ModuleType(path.stem)
            module.__file__ = str(path)
            sys.modules[path.stem] = module
            exec(compile(source, str(path), 'exec'), module.__dict__)
        return sys.modules['native_runtime_check']
    finally:
        sys.path[:] = saved_path
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def expected_vector_calls():
    """Independent ISA schedule, including the unchanged GQA6 six-head leaves."""
    calls = []
    for case in contract.CASES:
        d, heads, tokens = (case[k] for k in ('d', 'heads', 'kv'))
        special = d == 128 and heads == 6
        for mode in contract.ORDER:
            words = []
            for start in range(0, tokens, 64):
                count = min(64, tokens - start)
                words.append(FULL if start == 0 else REFILL)
                if special:
                    words += [COLUMN, COLUMN9] * 64
                elif mode:
                    words += [PANEL] * ((heads // 2) * (d // 4))
                    words += [COLUMN] * ((heads % 2) * d)
                else:
                    words += [COLUMN] * (heads * d)
                row = ROW128_GQA6 if special else {64: ROW64, 96: ROW96, 128: ROW128}[d]
                groups = 1 if special else (heads + 1) // 2 if mode else heads
                words += [row] * (groups * count)
            calls.append(words + [RELEASE])
    require([len(c) for c in calls] == contract.CALL_COMMANDS and
            sum(map(len, calls)) == 3680, 'Independent boundary command formulas changed')
    return calls


def _signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def instructions(code, address=0):
    result, offset = [], 0
    while offset < len(code):
        require(offset + 2 <= len(code), 'Truncated RISC-V instruction')
        half = struct.unpack_from('<H', code, offset)[0]
        size = 4 if half & 3 == 3 else 2
        require(size == 2 or half & 0x1f != 0x1f, 'Unsupported long RISC-V instruction')
        require(offset + size <= len(code), 'Truncated RISC-V instruction')
        result.append((address + offset, int.from_bytes(code[offset:offset + size], 'little'), size))
        offset += size
    return result


def direct_targets(code, address):
    result = set()
    insns = instructions(code, address)
    for index, (pc, word, size) in enumerate(insns):
        if size != 4:
            continue
        if word & 0x7f == 0x6f:
            imm = ((word >> 31) << 20 | ((word >> 12) & 255) << 12 |
                   ((word >> 20) & 1) << 11 | ((word >> 21) & 1023) << 1)
            result.add(pc + _signed(imm, 21))
        if word & 0x7f == 0x17 and index + 1 < len(insns):
            npc, nextword, nextsize = insns[index + 1]
            if (nextsize == 4 and npc == pc + 4 and nextword & 0x707f == 0x67 and
                    (nextword >> 15) & 31 == (word >> 7) & 31):
                result.add((pc + _signed(word & 0xfffff000, 32) +
                            _signed(nextword >> 20, 12)) & ~1)
    return result


def elf_contents(path):
    """Read actual ELF64-LE RISC-V sections/symbols, not a saved disassembly log."""
    raw = Path(path).read_bytes()
    require(len(raw) >= 64 and raw[:7] == b'\x7fELF\x02\x01\x01', 'Not ELF64 little endian')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    _, kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, _ = header
    require(kind == 2 and machine == 243 and version == 1 and ehsize == 64 and
            flags == 5 and shsize == 64 and shnum > 0,
            'ELF is not the native GNU RV64 double-float executable')
    require(shoff + shsize * shnum <= len(raw) and phsize == 56 and
            phoff + phsize * phnum <= len(raw), 'ELF table bounds')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, shoff + i * shsize) for i in range(shnum)]
    programs = [struct.unpack_from('<IIQQQQQQ', raw, phoff + i * phsize) for i in range(phnum)]
    loads = [p for p in programs if p[0] == 1]
    require(loads and all(p[0] not in (2, 3) for p in programs), 'Dynamic/interpreted ELF')
    for p in loads:
        require(p[5] <= p[6] and p[2] + p[5] <= len(raw) and
                0x80000000 <= p[3] and p[3] + p[6] < 0x80ff0000, 'ELF load/memory bounds')
    symbols = {}
    for sec in sections:
        _, stype, sflags, addr, offset, size, link, _, _, entsize = sec
        if sflags & 2:
            require(0x80000000 <= addr and addr + size < 0x80ff0000, 'Alloc section outside L2/stack reserve')
        if stype != 2:
            continue
        require(entsize == 24 and size % 24 == 0 and offset + size <= len(raw) and link < shnum,
                'ELF symbol table bounds')
        strings = sections[link]
        require(strings[4] + strings[5] <= len(raw), 'ELF string table bounds')
        names = raw[strings[4]:strings[4] + strings[5]]
        for pos in range(offset, offset + size, 24):
            name, info, _, section, value, nbytes = struct.unpack_from('<IBBHQQ', raw, pos)
            require(name < len(names), 'Invalid ELF symbol name')
            end = names.find(b'\0', name)
            require(end >= 0, 'Unterminated ELF symbol name')
            text = names[name:end].decode('ascii')
            if (section == 0 or section >= shnum or not text or
                    (info & 15 not in (1, 2) and text != '_start')):
                continue
            target = sections[section]
            require(value >= target[3] and value + nbytes <= target[3] + target[5], 'ELF symbol section bounds')
            file_offset = target[4] + value - target[3]
            require(target[1] == 8 or file_offset + nbytes <= len(raw), 'ELF symbol file bounds')
            if target[1] == 8:
                continue
            require(text not in symbols, 'Duplicate ELF symbol: ' + text)
            symbols[text] = dict(address=value, bytes=nbytes, type=info & 15, section_flags=target[2],
                                 data=raw[file_offset:file_offset + nbytes], offset=file_offset)
    require('_start' in symbols and symbols['_start']['address'] == entry, 'ELF entry point drift')
    return symbols


def check_elf(path):
    symbols = elf_contents(path)
    for name, item in contract.PAYLOADS.items():
        symbol = symbols.get(item['symbol'], {})
        require(symbol.get('bytes') == item['bytes'] and symbol.get('type') == 1 and
                symbol.get('section_flags', 0) & 2 and not symbol['section_flags'] & 1 and
                symbol['address'] % 64 == 0 and
                contract.hashlib.sha256(symbol['data']).hexdigest() == item['sha256'] and
                contract.fnv64(symbol['data']) == item['fnv64'], 'ELF actual payload/link mismatch: ' + name)
    required = ['main', 'boundary_body', 'akv_device_query', 'akv_attention_plan_create_v2',
                'akv_attention_execute_v2_native', 'getenv', *FUNCTION_WORDS]
    for name in required:
        symbol = symbols.get(name, {})
        require(symbol.get('type') == 2 and symbol.get('bytes', 0) > 0 and
                symbol.get('section_flags', 0) & 4, 'Missing native function link: ' + name)
    for name, words in FUNCTION_WORDS.items():
        actual = [w for _, w, size in instructions(symbols[name]['data']) if size == 4]
        require(all(w in actual for w in words), 'Actual ELF known-call signature mismatch: ' + name)
    for caller, callees in {
        'main': ['boundary_body'],
        'boundary_body': ['akv_device_query', 'akv_attention_plan_create_v2', 'akv_attention_execute_v2_native'],
        'akv_attention_execute_v2_native': ['akv_attention_execute_v2_with_features_native'],
    }.items():
        targets = direct_targets(symbols[caller]['data'], symbols[caller]['address'])
        require(all(symbols[n]['address'] in targets for n in callees), 'Actual native call edge mismatch: ' + caller)
    require(not any(n.startswith(('bench_', 'mock_', 'f16_profile_')) for n in symbols),
            'Benchmark/mock/profiling implementation linked')
    return dict(actual_payload_link_checked=True, actual_native_call_edges_checked=True,
                knowncall_signatures_checked=True, elf_sha256=sha(path))


def verify_build(build_dir):
    directory = Path(build_dir).resolve(strict=True)
    m = read_json(directory / 'build.json')
    require(all(m.get(k) == v for k, v in dict(schema=1, kind='boundary', state='BUILT_NOT_EXECUTED',
            execution='NOT_RUN', target_executed=False, rtl_executed=False, performance_measured=False,
            seal_ready=True, post_pins_match=True, sdk_head=contract.SDK_COMMIT,
            sdk_tree=contract.SDK_TREE, common_tree=contract.COMMON_TREE, sdk_unmodified=True,
            dirty_asm_excluded=True, all_runtime_objects_recompiled=True, cases=contract.CASES,
            order=contract.ORDER, runs=12, expected_commands=3680, per_call_commands=contract.CALL_COMMANDS,
            image_contract=contract.IMAGE, capture=str(contract.CAPTURE), payloads=contract.PAYLOADS,
            original_data_receipt=str(contract.ORIGIN),
            toolchain=dict(target=str(contract.CC), host=str(contract.HOST_CC), zcc=False)).items()),
            'Boundary build/version/scope contract mismatch')
    pinfile, elf, inputs = directory / 'source-pins.json', directory / 'akv_pair_boundary.elf', directory / 'inputs'
    require(m['source_pins'] == str(pinfile) and sha(pinfile) == m['source_pins_sha256'] and
            m['elf'] == str(elf) and sha(elf) == m['elf_sha256'], 'ELF/source inventory identity')
    pins = read_json(pinfile)
    contract.verify(pins)
    contract.verify(m['artifacts'])
    required = {**contract.validate_data(), **{str(HERE / n): sha(HERE / n) for n in contract.OWN_FILES}}
    for p, digest in required.items():
        require(pins.get(p) == digest, 'Missing mandatory source/data pin: ' + p)
    require(not any(str(HERE.parent / n) in pins for n in ('build.py', 'main.c', 'check.py', 'run.py',
                                                         'test_eval.py', 'reference.c')),
            'Boundary must not seal another owner')
    for tool, digest in ((contract.CC, contract.CC_SHA), (contract.HOST_CC, contract.HOST_CC_SHA),
                         (contract.GIT, contract.GIT_SHA)):
        require(pins.get(str(tool.resolve())) == digest, 'Missing pinned GNU tool')
    archive = inputs / 'sdk-785084122.tar'
    require(m['sdk_archive'] == str(archive) and m['sdk_archive_sha256'] == contract.ARCHIVE_SHA and
            sha(archive) == contract.ARCHIVE_SHA, 'Wrong exact git archive')
    members = contract.archive_members(archive.read_bytes())
    actual_files = {str(p.relative_to(inputs)) for p in inputs.rglob('*') if p.is_file()}
    require(actual_files == {*members, archive.name}, 'Unexpected/missing archive input file')
    for name, content in members.items():
        p = inputs / name
        digest = contract.hashlib.sha256(content).hexdigest()
        require(sha(p) == digest and pins.get(str(p)) == digest and
                m['artifacts'].get(str(p)) == digest, 'Archive/helper changed: ' + name)
    sdk_pins = {n: contract.hashlib.sha256(b).hexdigest() for n, b in members.items()
                if n.startswith('software/akv/')}
    require(sdk_pins and m['SDKpins'] == sdk_pins and
            m['harness'] == dict(path=str(inputs / contract.HARNESS),
                sha256=contract.LEGACY[contract.HARNESS], body='boundary_body'), 'SDK/harness mapping')
    for n, content in {'expected.h': contract.expected_header(), 'data.S': contract.data_assembly(),
                       'link.ld': contract.linker_script(inputs / 'apps/common')}.items():
        require((directory / n).read_text() == content and pins.get(str(directory / n)) == sha(directory / n),
                'Generated input substitution: ' + n)
    commands_path = directory / 'commands.json'
    require(m['compile_commands'] == str(commands_path), 'Missing actual commands inventory')
    commands = read_json(commands_path)
    labels = (['tree-akv', 'tree-common', 'archive', 'gnu-version', 'hosttests'] +
              ['locate-' + n for n in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a',
                                       'cc1', 'as', 'ld', 'collect2')] +
              [f'compile-{i:02d}' for i in range(16)] + ['link', 'objdump', 'readelf'])
    require([c['label'] for c in commands] == labels, 'Incomplete actual tool/config command inventory')
    require(commands and all(c['returncode'] == 0 and c['cwd'] == str(directory) and
            c['env'] == commands[0]['env'] and c['env']['PATH'] == '/usr/bin:/bin' and
            set(c['env']) == {'PATH', 'HOME', 'LC_ALL', 'TMPDIR', 'PYTHONDONTWRITEBYTECODE'}
            for c in commands), 'Compiler command/environment drift')
    compiles = [c['argv'] for c in commands if c['label'].startswith('compile-')]
    links = [c['argv'] for c in commands if c['label'] == 'link']
    require(compiles == contract.compile_recipe(directory) and links == [contract.link_recipe(directory)] and
            m['objects'] == [c[-1] for c in compiles] and m['objects_recompiled'] == len(compiles) == 16,
            'Not a complete fresh compile/link of the pinned SDK/harness')
    require([c['argv'] for c in commands if c['label'] == 'archive'] ==
            [[str(contract.GIT), '-C', str(contract.ROOT), 'archive', contract.SDK_COMMIT,
              *contract.ARCHIVE_PATHS]], 'Missing exact git archive command')
    for c in commands:
        require(m['artifacts'].get(c['log']) == sha(c['log']), 'Missing actual command log')
        if c['label'].startswith('locate-'):
            p = Path(c['log']).read_text().strip()
            require(pins.get(str(Path(p).resolve())) == sha(p), 'Missing SDK library/tool pin')
    for name, switches in (('objdump', ['-d']), ('readelf', ['-lW'])):
        tool = contract.CC.with_name(contract.CC.name.replace('gcc', name))
        require(pins.get(str(tool.resolve())) == sha(tool) and
                [c['argv'] for c in commands if c['label'] == name] ==
                [[str(tool), *switches, str(elf)]], 'Unpinned actual ELF inspection tool')
    for dep in [Path(c[-1]).with_suffix('.d') for c in compiles]:
        require(m['artifacts'].get(str(dep)) == sha(dep), 'Missing actual dependency receipt')
        for p in contract.dependency_inputs(dep):
            require(pins.get(str(p)) == sha(p), 'Unpinned compiler input: ' + str(p))
    require(str(inputs / contract.HARNESS) in
            {str(p) for p in contract.dependency_inputs(Path(compiles[0][-1]).with_suffix('.d'))},
            'Wrapper did not compile the exact original harness')
    for p in [elf, pinfile, commands_path, archive, directory / 'link.map', *map(Path, m['objects'])]:
        require(m['artifacts'].get(str(p)) == sha(p), 'Missing mandatory build artifact: ' + str(p))
    maptext = (directory / 'link.map').read_text()
    require(all(re.search(r'^LOAD ' + re.escape(p) + r'$', maptext, re.M) for p in m['objects']),
            'Actual link map omits an object')
    m['elf_link_checks'] = check_elf(elf)
    return m


def check_payload_log(text, legacy):
    suite_line = text.splitlines().index(legacy.SUITE)
    terminal_line = text.splitlines().index(legacy.s.TERMINAL)
    selected = [(i, line) for i, line in enumerate(text.splitlines()) if 'AKV_BOUNDARY_' in line]
    require(len(selected) == 4 and all(suite_line < i < terminal_line for i, _ in selected),
            'Missing/duplicate/early/late payload records')
    result = {}
    for (index, line), (name, item) in zip(selected[:3], contract.PAYLOADS.items()):
        expected = (f'AKV_BOUNDARY_PAYLOAD name={name} bytes={item["bytes"]} '
                    f'fnv={item["fnv64"]:016x} expected={item["fnv64"]:016x} errors=0')
        require(line == expected, 'Full original payload signature mismatch: ' + name)
        result[name] = dict(bytes=item['bytes'], fnv64=f'{item["fnv64"]:016x}',
                            sha256=item['sha256'], log_line=index + 1)
    require(selected[-1][1] == 'AKV_BOUNDARY_DONE body=0 checks=3 errors=0', 'Original body/payload EOC mismatch')
    return result


def check_run(log_path, build_dir):
    build = verify_build(build_dir)
    text = Path(log_path).read_text(errors='strict')
    require(not re.search(r'Error-|\$fatal', text), 'Simulator failure')
    legacy = load_legacy(Path(build_dir).resolve() / 'inputs')
    original = legacy.check_log(text)
    payloads = check_payload_log(text, legacy)
    return dict(state='PASS', kind='boundary', performance_measured=False, whole_model=False,
                native_commands=3680, runs=12, original_checks=original, payload_checks=payloads,
                elf_link_checks=build['elf_link_checks'], log_sha256=sha(log_path),
                elf_sha256=build['elf_sha256'], source_pins_sha256=build['source_pins_sha256'],
                independent_protocol_checked=False,
                scope='Functional/path regression of four derived shapes from one Qwen2.5 capture; '
                      'not four models, independent full Attention oracle, performance or RTL protocol acceptance')


def vector_workcounts(vector_path):
    path = Path(vector_path)
    calls = expected_vector_calls()
    expected = [word for call in calls for word in call]
    actual, counts, configs, last_cycle, last_seq = [], Counter(), 0, -1, -1
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields = set('cycle event arch_seq insn nr_lanes vlen_bits'.split())
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and
                fields <= set(reader.fieldnames), 'Malformed vector schema')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'Malformed vector row')
            require(all(re.fullmatch('[0-9]+', row[k]) for k in ('cycle', 'arch_seq')) and
                    re.fullmatch('[0-9a-fA-F]{8}', row['insn']), 'Invalid vector numeric fields')
            cycle = int(row['cycle'])
            require(cycle >= last_cycle and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'),
                    'Vector cycle/image/configuration drift')
            last_cycle = cycle
            if row['event'] == 'config':
                require(configs == 0 and not actual and cycle == 0, 'Extra/late vector configuration')
                configs += 1
            require(row['event'] != 'reset', 'Mid-run vector reset')
            if row['event'] != 'alloc':
                continue
            require(configs == 1, 'Allocation before vector configuration')
            word = int(row['insn'], 16)
            if word & 0x7f != 0x5b:
                continue
            require(word in SIGNATURE_NAMES, 'Unexpected custom/lifecycle instruction signature')
            seq = int(row['arch_seq'])
            require(seq > last_seq, 'Duplicate/replayed boundary allocation')
            last_seq = seq
            require(len(actual) < len(expected) and word == expected[len(actual)],
                    'Vector panel/column/D64/D96/D128/lifecycle order mismatch at ' + str(len(actual)))
            actual.append(word)
            counts[SIGNATURE_NAMES[word]] += 1
    require(configs == 1 and actual == expected and dict(counts) == EXPECTED_COUNTS,
            'Incomplete boundary vector instruction work: ' + str(counts))
    return dict(counts=dict(counts), panel_commands=counts['panel4'],
                column_commands=counts['column_v8'] + counts['column_v9'],
                d64_commands=counts['row_d64'], d96_commands=counts['row_d96'],
                d128_commands=counts['row_d128'] + counts['row_d128_gqa6'],
                lifecycle_commands=counts['full'] + counts['refill'] + counts['release'],
                native_commands=3680, replay_commands=3653, per_call_commands=list(map(len, calls)),
                ordered_signatures_checked=True, life_signatures_checked=True, trace_sha256=sha(path))


def check_vector_workcounts(vector_path, build_dir):
    build = verify_build(build_dir)
    return dict(vector_workcounts(vector_path), elf_sha256=build['elf_sha256'],
                source_pins_sha256=build['source_pins_sha256'], performance_measured=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    directory = args.build.parent if args.build.name == 'build.json' else args.build
    result = check_run(args.log, directory)
    result['vector_workcounts'] = check_vector_workcounts(args.trace, directory)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
