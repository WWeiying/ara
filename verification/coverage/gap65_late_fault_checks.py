"""Read-only gap65 ELF, numerical, memory-layout and future evidence checks."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
NAME = 'qbs_gap65_late_fault'
BASE = ROOT / 'verification/out/gap59-current-20261004-01'
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine'
TARGET_SCOPE = PREFIX + '.i_compute_engine'
TARGET = dict(scope=TARGET_SCOPE, metric='fsm', definition_checksum='2676500856',
              fsm_checksum='3121563879', fsm_id='0', fsm_name='state_q',
              transition_ordinal=3, fromid='1', toid='3', raw_index=15,
              width=43, source_line=555, native_identity_qualified=False)
GUARD = 0x6b28d391a45ef007


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def exact_float(value):
    packed = struct.pack('<f', float(value))
    require(Fraction.from_float(struct.unpack('<f', packed)[0]) == value, 'inexact scalar stage')
    return int.from_bytes(packed, 'little')


def vectors():
    """Pack native bytes and independently dequantize every scalar operand."""
    weights, activations = bytearray(), bytearray()
    for row in range(4):
        scales = [3 + (row + 7 * group) % 61 for group in range(8)]
        mins = [(row + 11 * group) % 37 for group in range(8)]
        packed = bytearray(12)
        for g in range(4):
            packed[g] = scales[g] | ((scales[g + 4] >> 4) << 6)
            packed[g + 4] = mins[g] | ((mins[g + 4] >> 4) << 6)
            packed[g + 8] = (scales[g + 4] & 15) | ((mins[g + 4] & 15) << 4)
        qs = bytearray(128)
        for k in range(256):
            g, lane = divmod(k, 32)
            qs[(g // 2) * 32 + lane] |= ((3 * k + 5 * row + g) % 16) << (4 * (g % 2))
        weights += struct.pack('<HH', 0x3800, 0x3400) + packed + qs
    for context in range(4):
        q = [(5 * k + 7 * context) % 31 - 15 for k in range(256)]
        activations += struct.pack('<f', (context + 1) / 4) + struct.pack('<256b', *q)
        activations += struct.pack('<16h', *(sum(q[g:g + 16]) for g in range(0, 256, 16)))
    expected, scalar = scalar_oracle(weights, activations)
    require(len(set(expected)) == 16 and all(x & 0x7fffffff for x in expected), 'weak numerical vectors')
    guard = b''.join(struct.pack('<Q', GUARD ^ i) for i in range(8))
    return dict(weight_hex=weights.hex(), activation_hex=activations.hex(), expected_bits=expected,
                weight_image=(guard + weights).hex(), activation_image=(guard + activations + guard).hex(),
                scalar=scalar, scope='host-reference-only', full_scalar_elements=4096,
                rounding='all individual conversion, multiplication, sum and final stages exactly representable')


def scalar_oracle(weights, activations):
    require(len(weights) == 576 and len(activations) == 1168, 'native byte lengths')
    results, details = [], []
    for context in range(4):
        a = activations[context * 292:(context + 1) * 292]
        a_scale = Fraction.from_float(struct.unpack('<f', a[:4])[0])
        signed = struct.unpack('<256b', a[4:260])
        sums = struct.unpack('<16h', a[260:])
        require(list(sums) == [sum(signed[g:g + 16]) for g in range(0, 256, 16)], 'bsum differs')
        for row in range(4):
            w = weights[row * 144:(row + 1) * 144]
            d, dm = (Fraction.from_float(struct.unpack('<e', w[i:i + 2])[0]) for i in (0, 2))
            dot, correction, direct = 0, 0, Fraction(0)
            for k, av in enumerate(signed):
                g, lane = divmod(k, 32)
                scale = w[4 + g] & 63 if g < 4 else (w[8 + g] & 15) | ((w[g] >> 6) << 4)
                minimum = w[8 + g] & 63 if g < 4 else (w[8 + g] >> 4) | ((w[4 + g] >> 6) << 4)
                q = (w[16 + (g // 2) * 32 + lane] >> (4 * (g % 2))) & 15
                dot += scale * q * av
                correction += minimum * av
                direct += (d * scale * q - dm * minimum) * a_scale * av
            for value in (Fraction(dot), Fraction(correction), d * a_scale, dm * a_scale,
                          d * a_scale * dot, direct):
                exact_float(value)
            require(direct == d * a_scale * dot - dm * a_scale * correction, 'scalar reduction mismatch')
            results.append(exact_float(direct))
            details.append(dict(context=context, row=row, dot=dot, correction=correction,
                                exact_numerator=direct.numerator, exact_denominator=direct.denominator))
    return results, details


def elf_proof(metadata, blob):
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in metadata['Symbols']}
    sections = [r['Section'] for r in metadata['Sections']]
    fixed = {'_start': 0x80000000, '__gap65_stack_guard_low': 0x80100000,
             '__gap65_stack_bottom': 0x80100040, '__gap65_stack_top': 0x80110000,
             '__gap65_stack_guard_high': 0x80110000, '__gap65_tail_guard': 0x801ffd80,
             '__gap65_tail_weights': 0x801ffdc0, '__gap65_tail_end': 0x80200000}
    require(all(symbols[n]['Value'] == address for n, address in fixed.items()), 'linker boundary drift')
    allowed = {'.text', '.rodata', '.data', '.sdata', '.bss', '.l2', '.gap65_stack', '.gap65_tail'}
    for s in sections:
        if not s['Size'] or not s['Flags']['Value'] & 2:
            continue
        name = s['Name']['Name']
        require(name in allowed, 'orphan allocated section: ' + name)
        start, end = s['Address'], s['Address'] + s['Size']
        if name == '.gap65_stack':
            require((start, end) == (0x80100000, 0x80110040) and s['Type']['Name'] == 'SHT_NOBITS', 'stack allocation')
        elif name == '.gap65_tail':
            require((start, end) == (0x801ffd80, 0x80200000) and s['Type']['Name'] == 'SHT_NOBITS', 'tail allocation')
        else:
            require(0x80000000 <= start < end <= 0x800e0000, 'application overlaps reservation')
    for row in metadata['ProgramHeaders']:
        segment = row['ProgramHeader']
        if segment['Type']['Name'] == 'PT_LOAD':
            require(0x80000000 <= segment['VirtualAddress'] and
                    segment['VirtualAddress'] == segment['PhysicalAddress'] and
                    segment['VirtualAddress'] + segment['MemSize'] <= 0x80200000, 'load segment outside RAM')
            if segment['FileSize']:
                require(segment['VirtualAddress'] + segment['FileSize'] <= 0x800e0000, 'file bytes in reserved RAM')

    def word(address):
        matches = [s for s in sections if s['Flags']['Value'] & 4 and
                   s['Address'] <= address and address + 4 <= s['Address'] + s['Size']]
        require(len(matches) == 1, 'ambiguous code coordinate')
        s = matches[0]
        offset = s['Offset'] + address - s['Address']
        return int.from_bytes(blob[offset:offset + 4], 'little')

    sites = {}
    for name in ('gap65_fault_site', 'gap65_recovery_site'):
        address = symbols[name]['Value']
        require(word(address) == 0x06b5045b, 'wrong M4 custom instruction')
        sites[name] = address
    require(len(set(sites.values())) == 2, 'custom sites alias')
    entry = symbols['rvtest_init']['Value']
    require(word(entry) == 0x00010393, 'entry no longer saves initial SP without memory')
    hi, lo = word(entry + 4), word(entry + 8)
    require(hi & 0xfff == 0x117 and lo & 0xfffff == 0x10113, 'entry SP relocation instruction drift')
    immediate = lo >> 20
    if immediate & 0x800:
        immediate -= 4096
    signed_hi = hi & 0xfffff000
    if signed_hi & 0x80000000:
        signed_hi -= 1 << 32
    require(entry + 4 + signed_hi + immediate == fixed['__gap65_stack_top'], 'entry does not relocate SP')
    sizes = {'gap65_seed': 640, 'gap65_observed': 640, 'gap65_activation': 1296,
             'gap65_descriptor': 144, 'gap65_csrs': 224, 'gap65_trap': 160, 'gap65_boot': 40}
    for name, size in sizes.items():
        s = symbols[name]
        require(s['Size'] == size and s['Value'] % 64 == 0 and
                0x80000000 <= s['Value'] < s['Value'] + size <= 0x800e0000, 'buffer layout: ' + name)
    return dict(status='STATIC_ELF_NOT_EXECUTED', fixed_symbols=fixed, sites=sites,
                buffer_symbols={n: symbols[n] for n in sizes}, entry=entry,
                tail_bytes=640, high_guard=0xbffffd80, high_weight=0xbffffdc0,
                ram_alias_mask=0x1fffff, stack_relocated_before_C=True, orphan_policy='error')


def check_runtime_log(log, proof):
    require('FAILED:' not in log and not re.search(r'(?m)^(?:Fatal:|Error:)', log), 'runtime failure')
    pattern = (r'GAP65 traps=1 cause=5 tval=c0000000 pc=([0-9a-f]+) '
               r'fault_vrf=128 recovery_vrf=128 numerical=16 errors=0')
    matches = re.findall(pattern, log)
    require(len(matches) == 1 and int(matches[0], 16) == proof['sites']['gap65_fault_site'], 'trap/site/inspection record')
    require(log.splitlines().count('PASSED: ' + NAME + ' checks=49 errors=0') == 1, 'runtime complete PASS')


def check_target_delta(before, after):
    def bits(record):
        require(record['checksum'] == '2676500856' and record['width'] == 43, 'FSM identity')
        value = int(record['bits'], 16)
        require(0 <= value < 1 << 43, 'FSM width overflow')
        return format(value, '043b')
    b, a = bits(before), bits(after)
    require(b[15] == '0' and a[15] == '1', 'exact target not newly hit')
    return dict(target=TARGET, scope='raw diagnostic only; require separate live-state witness')


def check_state_samples(samples):
    """Input is normalized read-only probe data; no aggregate-counter shortcut."""
    require(len(samples) >= 2, 'missing state samples')
    for previous, current in zip(samples, samples[1:]):
        require(current['cycle'] == previous['cycle'] + 1, 'nonconsecutive samples')
        require(previous['rst_n'] == current['rst_n'] == 1, 'reset in witness')
    for previous, current in zip(samples, samples[1:]):
        if previous['state'] == 3 and previous['next_state'] == 10 and previous['fault'] == 1:
            require(current['state'] == 10, 'fault arc not registered')
            return True
    raise ValueError('missing COMPUTE_TILE fault transition witness')
