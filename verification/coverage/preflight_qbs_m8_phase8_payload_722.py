#!/usr/bin/env python3
"""Static routing + native-byte oracle only; not an ELF or coverage admission."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from closure_point_inventory import definition, points, read_xml
import collect_gap104_strict_v2 as old

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'verification/out/gap104-offline-admitted-722-20261006-02'
SEAL = 'b9ad9d11e0eeb709ebcf3e4bd6d5ccbdd94d4a229e9c80b144ef10cf8213415a'
SCOPE = ('ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.'
         'i_compute_engine.i_block_adapter_bank1.i_payload_buffer')
TARGETS = (
    (6475, 2884, 219, '111'), (6613, 2935, 261, '11'), (6616, 2936, 262, '11'),
    (6911, 3051, 219, '111'), (7049, 3102, 261, '11'), (7052, 3103, 262, '11'),
    (7347, 3218, 219, '111'), (7485, 3269, 261, '11'), (7488, 3270, 262, '11'),
    (7783, 3385, 219, '111'), (7921, 3436, 261, '11'), (7924, 3437, 262, '11'))
SOURCES = ('hardware/include/qbs_pkg.sv', 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv',
           'hardware/src/vlsu/qbs/qbs_block_adapter.sv',
           'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
           'hardware/src/vlsu/qbs/qbs_read_engine.sv')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_fixture():
    weight = (struct.pack('<HH', 0x3c00, 0) + bytes([1]*4 + [0]*4 + [1]*4)
              + bytes(32) + bytes([0x11]*128))
    rows = []
    for context in range(8):
        q = context + 1
        rows.append(struct.pack('<f', 1.0) + bytes([q]*256)
                    + struct.pack('<16h', *([16*q]*16)))
    packed = bytearray(8*292)
    for context, row in enumerate(rows):
        for byte, value in enumerate(row):
            offset = (4*context + byte if byte < 4 else
                      32 + 8*(byte-4) + context if byte < 260 else
                      2080 + 16*((byte-260)//2) + 2*context + (byte & 1))
            packed[offset] = value
    return weight, rows, bytes(packed)


def native_dot(weight, activation):
    require(len(weight) == 176 and len(activation) == 292, 'native block size')
    scale, minimum = struct.unpack('<ee', weight[:4])
    ad = struct.unpack('<f', activation[:4])[0]
    qs = struct.unpack('<256b', activation[4:260])
    sums = struct.unpack('<16h', activation[260:])
    require(all(sum(qs[16*i:16*i+16]) == sums[i] for i in range(16)), 'bsum differs')
    dot = correction = 0
    s = weight[4:16]
    for group in range(8):
        sc = s[group] & 63 if group < 4 else (s[group+4] & 15) | ((s[group-4] >> 6) << 4)
        mn = s[group+4] & 63 if group < 4 else (s[group+4] >> 4) | ((s[group] >> 6) << 4)
        for i in range(32):
            quant = ((weight[48 + 32*(group//2) + i] >> (4*(group & 1))) & 15)
            quant |= ((weight[16+i] >> group) & 1) << 4
            dot += sc * quant * qs[32*group+i]
        correction += mn * (sums[2*group] + sums[2*group+1])
    value = ad * (scale * dot - minimum * correction)
    return struct.unpack('<I', struct.pack('<f', value))[0]


def crossing(phase, boundary=32):
    """Reader's compact beat positions, not physical AXI byte lane positions."""
    require(phase in (0, 4, 8, 12), 'activation ABI alignment')
    require(boundary in range(32, 256, 32), 'interior SRAM boundary')
    offsets = [0] + list(range(16-phase if phase else 16, 2336, 16))
    start = next(o for o in offsets if o <= 32+8*(boundary-1)+4 < o+16)
    entries = []
    for row in range(4):
        ctx = row + 4
        previous = 32 + 8*(boundary-1) + ctx
        current = 32 + 8*boundary + ctx
        if start <= previous < current < start+16:
            entries.append(dict(row=row, context=ctx, beat_offset=start,
                old_byte=previous-start, pending_byte=current-start,
                old_word=(boundary-1)//32, pending_word=boundary//32,
                quant_index=boundary))
    return entries


def validate_point(point, expected, row):
    raw, native, line, vector = expected
    require((point['raw_index'], point['native_id'], point['line'], point['vector']) ==
            (raw, str(native), str(line), vector), 'compiled identity differs')
    require(point['spec']['generate_info'] == 'slot=0,p=2,r=%d,b=%d' % (row, row+12),
            'compiled generated coordinate differs')
    require(point['attributes']['condregid'] == str(native), 'condition ID differs')


def prepare(out):
    require(not out.exists(), 'output exists')
    pins = {}

    def pin(path, expected=None):
        path = path.resolve(strict=True)
        actual = digest(path)
        require(expected is None or actual == expected, 'pin differs: '+str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'conflicting pin')
        pins[str(path)] = actual
        return path

    def bound(path, expected):
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'bound JSON differs')
        pin(path, expected)
        return json.loads(raw)

    manifest = bound(BASE/'admission-manifest.json', SEAL)
    bits = bound(BASE/'combined-bits.json', manifest['output_pins'][str(BASE/'combined-bits.json')])
    book = bound(BASE/'evidence-pins.json', manifest['output_pins'][str(BASE/'evidence-pins.json')])
    for relative in SOURCES:
        path = ROOT/relative
        require(str(path) in book, 'unbound old source')
        pin(path, book[str(path)])
    db = old.DESIGN/'snps/coverage/db'
    for relative, expected in bits['design'].items():
        pin(db/relative, expected)
    info = db/'shape/cond.verilog.info.xml'
    pin(info, book[str(info)])
    checksum = {n.get('name'): n.get('chksum') for n in read_xml(info).iter('instance_data')}
    metric = bits['metrics']['cond'][SCOPE]
    require(metric['width'] == 21503 and str(metric['checksum']) == '2947893042', 'metric differs')
    require(checksum[SCOPE] == str(metric['checksum']), 'native info checksum differs')
    design = old.shared.proof.old.shared.Design(old.DESIGN)
    node = definition(read_xml(db/'shape/cond.verilog.shape.xml'), design.hierarchy[SCOPE], metric['checksum'])
    mapped = {p['raw_index']: p for p in points('cond', node, metric['width'])}
    targets = []
    for index, expected in enumerate(TARGETS):
        point = mapped[expected[0]]
        validate_point(point, expected, index//3)
        require(not int(metric['bits'], 16) & (1 << (metric['width']-1-expected[0])), 'target already hit')
        targets.append(point)
    crossings = [crossing(8, boundary) for boundary in range(32, 256, 32)]
    require(all([e['pending_byte'] for e in events] == [12, 13, 14, 15]
                for events in crossings), 'phase8 transport prediction differs')
    require([e['pending_byte'] for e in crossing(4)] == [8, 9, 10, 11], 'phase4 control differs')
    weight, rows, packed = native_fixture()
    expected = [native_dot(weight, row) for row in rows]
    require(expected == [struct.unpack('<I', struct.pack('<f', 256*(i+1)))[0]
                         for i in range(8)], 'independent fixture decode differs')
    pin(Path(__file__))
    pin(Path(__file__).with_name('test_preflight_qbs_m8_phase8_payload_722.py'))
    for path, sha in pins.items():
        require(digest(Path(path)) == sha, 'input changed during prepare')
    record = dict(status='STATIC_NATIVE_BYTE_PREFLIGHT_NOT_ELF_NOT_COVERAGE_ADMISSION',
        baseline=str(BASE), baseline_seal=SEAL, scope=SCOPE, checksum=metric['checksum'],
        shape=dict(m=8, n=1, k_blocks=1, activation_layout='M8_INTERLEAVED',
                   weight_profile='Q5_K', activation_profile='Q8_K', activation_phase=8),
        targets=targets, crossing_predictions=crossings, control_phase4=crossing(4),
        expected_bits=expected, exact_arithmetic_fflags=0, input_pins=pins,
        coverage_gain_measured=False, vcs_launched=False, rtl_changed=False,
        limitations=['No cycle/state probe; pending replay is a source-derived prediction.',
                     'No ELF, Spike, full-VRF/CSR/guards software contract executed.'])
    out.mkdir(parents=True)
    for name, raw in [('weight-native.bin', weight), ('activation-row-native.bin', b''.join(rows)),
                      ('activation-m8-native.bin', packed)]:
        (out/name).write_bytes(raw)
    record['fixture_pins'] = {str(out/name): digest(out/name) for name in
        ('weight-native.bin', 'activation-row-native.bin', 'activation-m8-native.bin')}
    path = out/'preflight.json'
    path.write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(path), seal=digest(path), targets=len(targets))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    prepare(parser.parse_args().out.resolve())
