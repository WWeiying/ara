#!/usr/bin/env python3
"""Read-only audit of prepared01; never compiles, simulates, or writes files."""
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parent / 'prepared01'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def instruction(path, pc):
    data = path.read_bytes()
    require(data[:6] == b'\x7fELF\x02\x01', 'Expected little-endian ELF64')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    stride, count = struct.unpack_from('<HH', data, 54)
    for i in range(count):
        segment = struct.unpack_from('<IIQQQQQQ', data, phoff + i * stride)
        if segment[0] == 1 and segment[3] <= pc and pc + 4 <= segment[3] + segment[5]:
            return struct.unpack_from('<I', data, segment[2] + pc - segment[3])[0]
    raise ValueError('PC absent from file-backed load segments')


def main():
    complete = read(ROOT / 'complete.json')
    require(complete['status'] == 'PREPARED_HOST_SPIKE_PREFIX195_PASS_NOT_DUT' and
            complete['VCS_started'] is False and complete['RTL_modified'] is False, 'Wrong scope')
    require(sha(ROOT / 'pins.json') == complete['pins_sha256'], 'Pins ledger drift')
    pins = read(ROOT / 'pins.json')
    for path, expected in pins.items():
        require(sha(Path(path)) == expected, 'Pin drift: ' + path)
    require(len(pins) == complete['pin_count'], 'Pin cardinality')
    identity = read(ROOT / 'identity.json')
    require(sha(ROOT / 'original/original_rebuilt.elf') == identity['original_elf_sha256'] ==
            'd8abfc1bfebe188b1045a786e2ce17ba571e523c363b365ed28b805c99881710', 'Original ELF identity')
    require(instruction(ROOT / 'original/original_rebuilt.elf', 0x10666) == 0x5c805c57, 'Original target identity')
    source = (ROOT / 'original/fp_move_oracle.c').read_text()
    prefix = source.replace('        ++cases;\n    }\n',
        '        ++cases;\n        if(cases==195)goto prefix_done;\n    }\nprefix_done:\n')
    require((ROOT / 'prefix.c').read_text() == prefix, 'More than an original prefix cut')
    oracle = source[source.index('        unsigned long control='):source.index('        ++cases;')]
    require(oracle in (ROOT / 'case.c').read_text(), 'Original call/oracle drift')
    rows = read(ROOT / 'call_sequence.json')
    expected = []
    for vl in (0, 1, 2, 3, 256, 511, 512):
        for mode in range(4):
            for start in (1, vl // 2, vl, 511):
                for sticky in (0, 1):
                    expected.append((vl, mode, start, sticky))
    require(len(rows) == 195 and [(r['vl'], r['mode'], r['vstart'], r['sticky']) for r in rows] == expected[:195],
            'Prefix order/cardinality')
    require(all((r['index'], r['seed'], r['scalar'], r['invalid'], r['op']) == (i, 0, 0, 0, 0)
                for i, r in enumerate(rows)), 'Wrong original loop coordinates')
    require(rows[-1] == identity['boundary'], 'Boundary mismatch')
    full, short = ROOT / 'host/full.capture', ROOT / 'host/prefix.capture'
    require(full.read_bytes() == short.read_bytes() and full.stat().st_size == 195 * 2228, 'Predecessor input mismatch')
    host = read(ROOT / 'host.json')
    require(len(host['results']) == 11, 'Host coverage cardinality')
    for row in host['results']:
        text = (ROOT / 'host' / (row['name'] + '.log')).read_text()
        if row['name'].startswith('negative'):
            require(row['returncode'] == 1 and 'RVV_FP_MOVE_FAIL' in text and 'RVV_FP_MOVE_DETAIL' in text,
                    'Negative did not reject')
        else:
            marker = f'RVV_FP_MOVE_PASS sew=16 cases={row["calls"]} errors=0'
            require(row['returncode'] == 0 and text.splitlines().count(marker) == 1 and 'FAIL' not in text,
                    'Host positive did not pass')
    programs = read(ROOT / 'programs.json')
    for backend, entry in programs.items():
        require(entry['calls'] == 195 and sha(Path(entry['path'])) == entry['sha256'], 'Prepared ELF drift')
        require(instruction(Path(entry['path']), int(entry['target']['pc'], 16)) == 0x5c805c57, 'Actual target opcode drift')
    reference = read(ROOT / 'reference.json')
    text = (ROOT / 'spike/fp_merge_prefix195.spike.log').read_text()
    values = [int(x, 16) for x in re.findall(r'^0x([0-9a-f]+)$', text, re.M)]
    require(len(values) == 1758 and reference['returncode'] == values[-1] == 0, 'Reference exit/cardinality')
    require(reference['retired'] == values[-2] - values[0] == 3382750, 'Reference cost drift')
    require(reference['elf_sha256'] == programs['spike']['sha256'] and reference['target_calls_observed'] == 195,
            'Reference ELF/count binding')
    for i, row in enumerate(rows):
        state = values[1 + i * 9:1 + (i + 1) * 9]
        wanted = [row['vl'], row['vstart'], row['sticky'], (row['sticky'] << 32) | row['vstart']]
        require(state[:4] == wanted and state[4] & ((1 << 64) - 1) == 0xffffffffffff0000 and
                state[5:] == [0, row['sticky'], row['sticky'] << 32, 0], 'Target state/boxing/CSR mismatch')
    require(not re.search(r'FAIL|DETAIL|TRAP', text) and all(text.splitlines().count(m) == 1
            for m in programs['spike']['pass_markers']), 'Raw reference failure or missing/duplicate PASS')
    print(json.dumps(dict(status='READ_ONLY_AUDIT_PASS_NOT_DUT', pins=len(pins), calls=195,
        original_partition_calls=21504, spike_retired=reference['retired'],
        boundary=rows[-1], soc_elf_sha256=programs['soc']['sha256']), indent=2))


if __name__ == '__main__':
    main()
