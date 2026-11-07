#!/usr/bin/env python3
"""New-SDK identity gates with the sealed primary numerical/native-work checks."""
import argparse
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('auto_integration_build_contract', HERE/'build.py')
contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contract)
require, sha = contract.require, contract.sha


def check_elf(path):
    raw = Path(path).read_bytes()
    require(len(raw) >= 64 and raw[:7] == b'\x7fELF\x02\x01\x01', 'Not ELF64 little endian')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    _, kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, _ = header
    require(kind == 2 and machine == 243 and version == 1 and ehsize == 64 and flags & 6 == 4 and
            phsize == 56 and phnum > 0 and phoff+phsize*phnum <= len(raw) and
            shsize == 64 and shnum > 0 and shoff+shsize*shnum <= len(raw), 'Native ELF header mismatch')
    programs = [struct.unpack_from('<IIQQQQQQ', raw, phoff+i*phsize) for i in range(phnum)]
    loads = [p for p in programs if p[0] == 1]
    require(loads and all(p[0] not in (2, 3) for p in programs), 'Not a static native ELF')
    require(all(p[5] <= p[6] and p[2]+p[5] <= len(raw) and 0x80000000 <= p[3] and
                p[3]+p[6] < 0x80ff0000 for p in loads), 'ELF outside L2/stack reserve')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, shoff+i*shsize) for i in range(shnum)]
    required = {'_start', 'main', 'getenv', 'akv_decode_execute', 'akv_attention_execute_v2_native',
                'akv_attention_execute_v2_native_auto'}
    functions = {}
    for sec in sections:
        if sec[1] != 2:
            continue
        require(sec[9] == 24 and sec[5] % 24 == 0 and sec[4]+sec[5] <= len(raw) and sec[6] < shnum,
                'ELF symbol table bounds')
        strings = sections[sec[6]]
        require(strings[4]+strings[5] <= len(raw), 'ELF string table bounds')
        names = raw[strings[4]:strings[4]+strings[5]]
        for off in range(sec[4], sec[4]+sec[5], 24):
            name, info, _, index, value, size = struct.unpack_from('<IBBHQQ', raw, off)
            end = names.find(b'\0', name)
            require(name < len(names) and end >= name, 'ELF symbol name bounds')
            text = names[name:end].decode('ascii')
            if text not in required:
                continue
            require(index < shnum and info >> 4 in (1, 2) and
                    (text == '_start' or info & 15 == 2 and size > 0), 'ELF function symbol mismatch')
            target = sections[index]
            require(target[2] & 4 and target[3] <= value and value+size <= target[3]+target[5],
                    'Function not in executable section')
            require(text not in functions, 'Duplicate ELF function')
            functions[text] = value
    require(required <= functions.keys() and functions['_start'] == entry, 'Missing actual native auto link')
    return dict(native_elf_checked=True, auto_api_symbols_checked=True, elf_sha256=sha(path))


def verify_build(build_dir):
    directory = Path(build_dir).resolve(strict=True)
    old, _, base, mandatory = contract.base_inputs()
    m = json.loads((directory/'build.json').read_text())
    require(m.get('schema') == contract.SCHEMA, 'Not a native-auto integration receipt')
    sdk, raw, members = contract.sdk_contract(m['sdk_new'])
    expected = contract.manifest_fields(directory, sdk, base)
    require(all(m.get(k) == v for k, v in expected.items()), 'New SDK/build/scope contract mismatch')
    pinfile = directory/'source-pins.json'
    require(sha(pinfile) == m['source_pins_sha256'], 'Pin inventory changed')
    pins = json.loads(pinfile.read_text())
    mandatory.update({str(HERE/n): sha(HERE/n) for n in contract.OWN_FILES})
    mandatory[str(contract.GIT.resolve())] = sha(contract.GIT.resolve())
    archive = directory/'inputs/sdk-auto.tar'
    require(archive.read_bytes() == raw and sha(archive) == sdk['sdk_archive_sha256'], 'Not the exact new Git archive')
    mandatory[str(archive)] = sha(archive)
    for name, content in members.items():
        p = directory/'inputs'/name
        require(p.read_bytes() == content, 'Extracted SDK/common differs from archive: '+name)
        mandatory[str(p)] = contract.hashlib.sha256(content).hexdigest()
    require({str(p.relative_to(directory/'inputs')) for p in (directory/'inputs').rglob('*') if p.is_file()} ==
            {*members, 'sdk-auto.tar'}, 'Unexpected SDK input file')
    require(all(pins.get(p) == digest for p, digest in mandatory.items()), 'Missing required base/new input pin')
    require(not any(Path(p).is_relative_to(contract.ROOT/'software/akv') for p in pins),
            'Live/dirty SDK input forbidden')
    contract.verify(pins)
    contract.verify(m['artifacts'])
    actual = {str(p): sha(p) for p in directory.rglob('*') if p.is_file() and p != directory/'build.json'}
    require(actual == m['artifacts'], 'Incomplete/extra build artifact inventory')
    commands_path = directory/'commands.json'
    commands = json.loads(commands_path.read_text())
    recipe = contract.target_recipe(directory)
    targets = [dict(label=c['label'], argv=c['argv']) for c in commands if
               c['label'].startswith('compile-') or c['label'] in ('link', 'disassembly', 'segments')]
    require(targets == recipe and all(c['returncode'] == 0 for c in commands),
            'Not all sixteen fresh compiles and exact accepted link recipe')
    require(len(commands) == 21 and commands[0]['label'] == 'archive' and
            commands[0]['argv'] == [str(contract.GIT), '-C', str(contract.ROOT), 'archive', sdk['sdk_new'],
                                    'software/akv', 'apps/common'] and
            commands[1]['label'] == 'hosttests' and
            commands[1]['argv'] == [commands[1]['argv'][0], '-B', str(HERE/'test_integration.py'), '-v'],
            'Missing archive/hosttest command provenance')
    for c in commands:
        require(c['cwd'] == str(contract.ROOT if c['label'] == 'archive' else directory) and
                m['artifacts'].get(c['log']) == sha(c['log']), 'Actual command cwd/log mismatch')
        if c['label'] != 'archive':
            require(c['env'] == commands[1]['env'] and set(c['env']) ==
                    {'PATH', 'HOME', 'LC_ALL', 'PYTHONDONTWRITEBYTECODE'} and
                    c['env']['PATH'] == '/usr/bin:/bin' and c['env']['LC_ALL'] == 'C' and
                    c['env']['PYTHONDONTWRITEBYTECODE'] == '1', 'Compiler environment drift')
    dependencies = []
    for obj in map(Path, m['objects']):
        require(obj.parent == directory and m['artifacts'].get(str(obj)) == sha(obj), 'Missing fresh object')
        dep = obj.with_suffix('.d')
        require(m['artifacts'].get(str(dep)) == sha(dep), 'Missing actual compiler dependency inventory')
        paths = old.dependency_inputs(dep)
        dependencies.extend(paths)
        require(all(pins.get(str(p)) == sha(p) for p in paths), 'Unpinned compiler source/header')
        if obj.name == '00_main.o':
            require({HERE/'main.c', contract.PRIMARY/'main.c', contract.BASE/'expected.h',
                     directory/'inputs/software/akv/include/akv/akv.h'} <= set(paths),
                    'Wrapper did not compile the sealed caller with new SDK headers')
    require(directory/'inputs/software/akv/experimental/paired_heads/auto_policy.h' in dependencies,
            'New auto policy not compiled')
    maptext = (directory/'link.map').read_text()
    require(all(re.search(r'^LOAD '+re.escape(p)+r'$', maptext, re.M) for p in m['objects']),
            'Actual link omits fresh objects')
    elf = directory/contract.ELF_NAME
    require(sha(elf) == m['elf_sha256'], 'ELF drift')
    m['elf_link_checks'] = check_elf(elf)
    return m


def check_run(log_path, build_dir):
    log_path, directory = Path(log_path).resolve(), Path(build_dir).resolve()
    m = verify_build(directory)
    _, original = contract.sealed_modules()
    text = log_path.read_text()
    result = original.check_log(text, Path(m['golden']['captured']).read_bytes(),
        Path(m['golden']['native_tile64']).read_bytes(), m['memory_expected'])
    work = original.check_hardware_work(text)
    require(all(c['busy_cycles'] <= elapsed for c, elapsed in zip(work['calls'], result['measured_total_cycles'])),
            'Native work exceeds full-call ROI')
    result.update(state='PASS', kind='qwen3_abba', work=work, full_call_count=4,
        sdk_new=m['sdk_new'], baseSDK=m['baseSDK'], sdk_diffset=m['sdk_diffset'],
        environment=m['environment'], elf_link_checks=m['elf_link_checks'],
        build=str(directory/'build.json'), build_sha256=sha(directory/'build.json'),
        elf_sha256=m['elf_sha256'], source_pins_sha256=m['source_pins_sha256'],
        log=str(log_path), log_sha256=sha(log_path), image_contract=m['image_contract'],
        independent_vector_work_checked=False, independent_protocol_checked=False,
        scope=m['scope'], acceptance_scope='Auto API plain F16 correctness/native work only; '
        'runner must check current image, vector and independent UVM. No production/default approval.')
    return result


def vector_workcounts(path):
    _, original = contract.sealed_modules()
    actual, counts, configs, last = [], Counter(), 0, -1
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = set('cycle event insn nr_lanes vlen_bits'.split())
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and
                required <= set(reader.fieldnames), 'Vector trace schema mismatch')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'Malformed vector row')
            require(re.fullmatch('[0-9]+', row['cycle']) and
                    re.fullmatch('[0-9a-fA-F]{8}', row['insn']), 'Invalid vector numeric field')
            cycle = int(row['cycle'])
            require(last <= cycle < 1 << 64 and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'),
                    'Vector image/cycle drift')
            last = cycle
            if row['event'] == 'config':
                require(configs == 0 and not actual and cycle == 0, 'Late/duplicate vector configuration')
                configs += 1
            require(row['event'] != 'reset', 'Mid-run vector reset')
            if row['event'] != 'alloc':
                continue
            require(configs == 1, 'Allocation before vector configuration')
            insn = int(row['insn'], 16)
            if insn & 0x707f not in (0x305b, 0x705b):
                continue
            require(insn in (0x0005745b, 0x0205745b, 0x0205345b), 'Unexpected replay signature')
            actual.append(insn)
            counts[{0x0005745b:'k_column_commands', 0x0205745b:'k_panel4_commands',
                    0x0205345b:'v_row_commands'}[insn]] += 1
    require(configs == 1 and actual == original.expected_vector_signatures() and
            counts == dict(k_column_commands=1536, k_panel4_commands=192, v_row_commands=822),
            'Independent auto/generic signature/order/count mismatch')
    return dict(counts=dict(counts), replay_commands=2550, native_commands_with_lifecycle=2566,
                per_call_commands=[1046, 237, 237, 1046], ordered_signatures_checked=True,
                trace_sha256=sha(path))


def check_vector_workcounts(vector_trace_path, build_dir):
    m = verify_build(build_dir)
    return dict(vector_workcounts(vector_trace_path), sdk_new=m['sdk_new'], baseSDK=m['baseSDK'],
                elf_sha256=m['elf_sha256'], source_pins_sha256=m['source_pins_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    directory = args.build.parent if args.build.name == 'build.json' else args.build
    result = check_run(args.log, directory)
    result['vector_command_work'] = check_vector_workcounts(args.trace, directory)
    print(json.dumps(result, indent=2))
