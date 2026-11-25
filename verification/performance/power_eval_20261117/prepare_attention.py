#!/usr/bin/env python3
"""Prepare isolated RVV/native-AKV attention firmware; check logs without monitors."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REAL = HERE.parent / 'operator_eval_20261115/attention_real'
sys.path.insert(0, str(REAL))
from contract import OUT, require, save, sha, verify, load, ELF

FROZEN = OUT / 'operator_attention_real_prepare_20261115_t137_balanced_02'
FROZEN_SHA = '85dad4290e173a936135964ba875fbe110597397a7a68372a60e1b8c6078d9ed'
SCHEMA = 'power-attention-single-mode-firmware-20261117-v1'
ROLES = ('query', 'key', 'value', 'mask', 'golden', 'model_golden')
MODES = {'rvv': 0, 'akv': 1}
L2_START, L2_END, STACK_BYTES = 0x80000000, 0x80100000, 65536


def checker():
    return load(REAL / 'check.py', 'power_attention_numerical')


def paired_data(inputs):
    hashes = {role: sha(inputs / (role + '.bin')) for role in ROLES}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    return dict(files=hashes, sha256=digest,
                definition='SHA256 of canonical sorted compact JSON role-to-SHA256 map')


def replace_once(text, old, new):
    require(text.count(old) == 1, 'Frozen template drift: ' + old[:70])
    return text.replace(old, new)


def adapt_header(text, mode):
    text, n = re.subn(r'^#define ATTN_CALLS UINT64_C\(0xa\)$',
                      '#define ATTN_CALLS UINT64_C(0x2)', text, flags=re.M)
    require(n == 1, 'Frozen call count drift')
    text = replace_once(text,
        'static const unsigned attention_order[ATTN_CALLS] = {0,1,4,2,3,3,2,4,1,0};',
        'static const unsigned attention_order[ATTN_CALLS] = {%d,%d};' % (mode, mode))
    return replace_once(text, '#define ATTN_PRINT_VALUES 64', '#define ATTN_PRINT_VALUES 256')


def adapt_linker(text):
    text = replace_once(text, 'LENGTH = 0x01000000', 'LENGTH = 0x00100000')
    # Include function/data-section BSS explicitly, before checking the stack gap.
    text = replace_once(text, '*(.bss)', '*(.bss .bss.*) *(COMMON)')
    return replace_once(text, '  .comment :', '''  __power_image_end = .;
  __power_stack_top = ORIGIN(L2) + LENGTH(L2);
  __power_stack_bottom = __power_stack_top - 0x10000;
  ASSERT(__power_image_end <= __power_stack_bottom, "Image overlaps 64 KiB stack")

  .comment :''')


def adapt_crt(text):
    return replace_once(text, '    la      t0, dram_end_address_reg\n    ld      sp, 0(t0)',
                        '    la      sp, __power_stack_top')


def adapt_main(text, mode):
    start = text.index('  if (c->mode == 0) return attention_rvv_group')
    end = text.index('\n}', start)
    dispatch = ('  return attention_rvv_group(p,&workspace.value);' if mode == 0 else
                '  return akv_attention_execute_v2_native_auto(c->device,p,&workspace.value);')
    text = text[:start] + dispatch + text[end:]
    if mode == 0:
        text = replace_once(text, 'akv_device_query(akv_native_info,NULL,&device)',
                            'akv_device_init_reference(&device)')
    return text


def custom_instructions(text):
    instructions = re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s', text, re.M)
    require(instructions, 'No disassembled instructions')
    return [dict(pc=int(pc, 16), word=int(word, 16)) for pc, word in instructions
            if int(word, 16) & 0x7f in (0x0b, 0x2b, 0x5b, 0x7b)]


def elf_bounds(path):
    raw = path.read_bytes()
    require(raw[:7] == b'\x7fELF\x02\x01\x01', 'Expected ELF64 little endian')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(h[2] == 243 and h[9] == 56, 'ELF machine/program header')
    segments = []
    for i in range(h[10]):
        p = struct.unpack_from('<IIQQQQQQ', raw, h[5] + i * h[9])
        if p[0] != 1:
            continue
        require(p[3] == p[4] and L2_START <= p[3] < p[3] + p[6] <= L2_END - STACK_BYTES,
                'ELF load segment outside image region')
        require(p[5] <= p[6] and p[2] + p[5] <= len(raw), 'ELF segment file bounds')
        segments.append(dict(address=p[3], file_bytes=p[5], memory_bytes=p[6]))
    require(segments, 'No load segments')
    return segments


def build(mode, output=None):
    require(mode in MODES, 'Mode must be rvv or akv')
    output = Path(output or OUT / ('power_attention_prepare_20261117_%s_01' % mode)).absolute()
    require(output == output.resolve() and output.parent == OUT.resolve() and
            re.fullmatch(r'power_attention_prepare_20261117_' + mode + r'_[A-Za-z0-9_.-]+', output.name)
            and not output.exists(), 'Fresh owned signoff output required')
    for key in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH',
                'LD_PRELOAD', 'LD_LIBRARY_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH',
                'CFLAGS', 'LDFLAGS'):
        require(not os.environ.get(key), 'Compiler environment injection: ' + key)
    require(sha(FROZEN / 'build.json') == FROZEN_SHA, 'Frozen receipt drift')
    old = checker().receipt(FROZEN)
    c = old['fixture']['case']
    require((c['dimension'], c['heads'], c['kv_heads'], c['tokens'], c['capacity']) ==
            (128, 2, 1, 137, 256) and c['original_t137'], 'Wrong captured shape')
    output.mkdir()
    inputs = output / 'inputs'
    shutil.copytree(FROZEN / 'inputs', inputs)
    commands = []
    env = dict(PATH='/usr/bin:/bin', HOME=str(output), LC_ALL='C', TZ='UTC',
               PYTHONDONTWRITEBYTECODE='1')
    pins = json.loads((FROZEN / 'source-pins.json').read_text())
    pins[str(FROZEN / 'build.json')] = FROZEN_SHA
    pins.update(old['artifacts'])
    for p in (Path(__file__).resolve(), HERE / 'test_prepare_attention.py', REAL / 'check.py'):
        pins[str(p)] = sha(p)

    def run(label, argv):
        argv = list(map(str, argv))
        p = subprocess.run(argv, cwd=output, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=180)
        (output / (label + '.log')).write_bytes(p.stdout)
        commands.append(dict(label=label, argv=argv, returncode=p.returncode))
        require(p.returncode == 0, 'Command failed: ' + label + '\n' + p.stdout[-2000:].decode(errors='replace'))

    fixture = copy.deepcopy(old['fixture'])
    fixture.update(order=[MODES[mode]] * 2, printed_values=256)
    header = inputs / 'fixture.h'
    header.write_text(adapt_header(header.read_text(), MODES[mode]))
    main_source = inputs / 'main.c'
    main_source.write_text(adapt_main(main_source.read_text(), MODES[mode]))
    save_fixture = inputs / 'fixture.json'
    save_fixture.write_text(json.dumps(fixture, indent=2, sort_keys=True) + '\n')
    link = inputs / 'link.ld'
    link.write_text(adapt_linker(link.read_text()))
    crt = inputs / 'sdk/apps/common/crt0.S'
    crt.write_text(adapt_crt(crt.read_text()))
    data = paired_data(inputs)
    require(data == paired_data(FROZEN / 'inputs'), 'Captured data changed')
    old_commands = {r['label']: r['argv'] for r in json.loads((FROZEN / 'commands.json').read_text())}

    def relocated(argv):
        return [s.replace(str(FROZEN), str(output)) for s in argv]

    reused = {}
    for i in range(22):
        argv = old_commands['compile-%02d' % i]
        obj = Path(argv[argv.index('-o') + 1])
        if i in (0, 6):
            run('compile-%02d' % i, relocated(argv))
        else:
            shutil.copyfile(obj, output / obj.name)
            reused[str(obj)] = sha(obj)
    run('link', relocated(old_commands['link']))
    for name in ('objdump', 'readelf'):
        run(name, relocated(old_commands[name]))
    custom = custom_instructions((output / 'objdump.log').read_text())
    require(not custom if mode == 'rvv' else bool(custom), 'Unexpected custom opcode inventory')
    elf = output / 'attention.elf'
    segments = elf_bounds(elf)
    reader = load(ELF, 'power_attention_elf')
    parsed = reader.contract(elf.read_bytes())
    require(reader.pc(parsed, '__power_stack_top') == L2_END and
            reader.pc(parsed, '__power_stack_bottom') == L2_END - STACK_BYTES and
            reader.pc(parsed, '__power_image_end') <= L2_END - STACK_BYTES, 'Stack/image bounds')
    # Bind each payload and golden directly to the linked image, not only its input file.
    raw = elf.read_bytes()
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    ph = [struct.unpack_from('<IIQQQQQQ', raw, h[5] + i * h[9]) for i in range(h[10])]
    for role in ROLES:
        addr = reader.pc(parsed, 'fixture_' + role)
        blob = (inputs / (role + '.bin')).read_bytes()
        matches = [p for p in ph if p[0] == 1 and p[3] <= addr and addr + len(blob) <= p[3] + p[5]]
        require(len(matches) == 1, 'Payload not in one ELF segment: ' + role)
        offset = matches[0][2] + addr - matches[0][3]
        require(raw[offset:offset + len(blob)] == blob, 'ELF payload drift: ' + role)
    verify(pins)
    pins.update({str(p): sha(p) for p in inputs.rglob('*') if p.is_file()})
    save(output / 'source-pins.json', pins)
    save(output / 'commands.json', commands)
    overlays = {rel: sha(inputs / 'sdk' / rel) for rel in old['sdk_overlays']}
    require(overlays == old['sdk_overlays'], 'SDK overlay drift')
    report = dict(schema=SCHEMA, state='BUILT_NOT_EXECUTED', mode=MODES[mode],
        mode_name=mode, order=fixture['order'], fixture=fixture, paired_source_data=data,
        elf=str(elf), elf_sha256=sha(elf), l2_bytes=1048576, load_segments=segments,
        stack=dict(top=L2_END, bottom=L2_END - STACK_BYTES, reserved_bytes=STACK_BYTES,
                   placement='Copied crt0 uses linker __power_stack_top; no CTRL/FPGA fixed stack'),
        parent=dict(receipt=str(FROZEN / 'build.json'), sha256=FROZEN_SHA,
                    source_pins_sha256=old['source_pins_sha256']),
        sdk_provenance=dict(archive_commit=old['sdk_commit'], reviewed_overlays=overlays,
            native_assembly_sha256=old['archive_native_assembly_sha256'],
            dirty_asm_excluded=old['dirty_asm_excluded'],
            source='Verified frozen inputs, not live SDK',
            successor_overlay=dict(path='apps/common/crt0.S',
                parent_sha256=sha(FROZEN / 'inputs/sdk/apps/common/crt0.S'), sha256=sha(crt))),
        rebuilt_objects=['00_main.o', '06_crt0.o'], reused_objects=reused,
        main_adaptation=dict(sha256=sha(main_source), single_dispatch=mode,
            device_initialization=('Reference capability metadata for software descriptor validation only; '
                                   'not hardware discovery or admission' if mode == 'rvv' else
                                   'Unchanged native capability query')),
        custom_opcode_inventory=custom, rvv_has_no_custom_opcodes=not custom,
        scalar_expf_audit=old['scalar_expf_audit'],
        source_pins_sha256=sha(output / 'source-pins.json'), post_pins_match=True,
        rtl_executed=False, target_executed=False, performance_measured=False,
        protocol_checked=False, execution_path_checked=False, power_acceptance=False,
        scope='Firmware preparation only; log checker enforces numerics/flags/guards/EOC. '
              'Parent must independently check image, protocol, execution path and activity.')
    save(output / 'run-plan.json', dict(cases=[dict(id='power_attention_' + mode,
        category='attention', elf=str(elf), elf_sha256=sha(elf),
        source_pins=str(output / 'source-pins.json'), timeout_seconds=10800, plusargs=[],
        checker=[str(Path(sys.executable).resolve()), '-B', str(Path(__file__).resolve()),
                 'check', '--build', str(output), '--log', '{log}', '--output', '{result}'])]))
    report['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    save(output / 'build.json', report)
    return report


def receipt(directory):
    directory = Path(directory).resolve(strict=True)
    m = json.loads((directory / 'build.json').read_text())
    require(m['schema'] == SCHEMA and m['state'] == 'BUILT_NOT_EXECUTED' and
            m['mode_name'] in MODES and m['mode'] == MODES[m['mode_name']] and
            m['order'] == m['fixture']['order'] == [m['mode']] * 2 and
            m['fixture']['printed_values'] == 256 and m['l2_bytes'] == 1048576 and
            m['post_pins_match'] is True and not m['rtl_executed'] and
            not m['target_executed'], 'Successor firmware contract mismatch')
    require(m['elf'] == str(directory / 'attention.elf') and sha(m['elf']) == m['elf_sha256'] and
            sha(directory / 'source-pins.json') == m['source_pins_sha256'], 'Firmware identity drift')
    verify(json.loads((directory / 'source-pins.json').read_text()))
    verify(m['artifacts'])
    require({str(p): sha(p) for p in directory.rglob('*') if p.is_file() and p.name != 'build.json'} ==
            m['artifacts'], 'Artifact membership drift')
    require(paired_data(directory / 'inputs') == m['paired_source_data'], 'Paired source data drift')
    require(json.loads((directory / 'inputs/fixture.json').read_text()) == m['fixture'],
            'Receipt/compiled fixture mismatch')
    original = json.loads((FROZEN / 'inputs/fixture.json').read_text())
    original.update(order=[m['mode']] * 2, printed_values=256)
    require(m['fixture'] == original and m['parent']['sha256'] == FROZEN_SHA and
            sha(FROZEN / 'build.json') == FROZEN_SHA, 'Independent golden/parent contract drift')
    require(custom_instructions((directory / 'objdump.log').read_text()) == m['custom_opcode_inventory'],
            'Custom opcode inventory drift')
    return m


def check_text(text, fixture):
    numerical = checker()
    severity = load(numerical.LEGACY, 'power_attention_severity').classify_simulator(text)
    measured = numerical.numerical(text, fixture)
    return dict(state='PASS', trials=measured, simulator=severity,
                bitexact_output_values=len(fixture['result']['bits']) * len(fixture['order']),
                flags_checked=True, guards_checked=True, all_outputs_checked=True,
                protocol_checked=False, image_checked=False, execution_path_checked=False,
                activity_checked=False, performance_acceptance=False, power_acceptance=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build', allow_abbrev=False)
    p.add_argument('--mode', required=True, choices=MODES)
    p.add_argument('--output', type=Path)
    p = sub.add_parser('check', allow_abbrev=False)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'build':
            m = build(args.mode, args.output)
            print(json.dumps({k: m[k] for k in ('state', 'elf', 'elf_sha256', 'paired_source_data')}))
            return 0
        m = receipt(args.build)
        result = check_text(args.log.read_text(), m['fixture'])
        result.update(build_sha256=sha(args.build / 'build.json'), log_sha256=sha(args.log),
                      paired_source_data=m['paired_source_data'])
    except Exception as exc:
        result = dict(state='FAIL', error=str(exc), performance_acceptance=False, power_acceptance=False)
    if args.command == 'check':
        save(args.output, result)
    print(json.dumps(result))
    return result['state'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
