"""Read existing compilation/Host artifacts only; never dispatch tests."""
import hashlib
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
P = HERE.parent / 'full_e8_mf2_packed_prepare01'
ARCH = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def elf(path):
    raw = Path(path).read_bytes()
    assert raw[:6] == b'\x7fELF\x02\x01'
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    assert header[2] == 243
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, header[6] + i * header[11])
                for i in range(header[12])]

    def at(pc, size):
        for s in sections:
            if s[1] != 8 and s[3] <= pc and pc + size <= s[3] + s[5]:
                off = s[4] + pc - s[3]
                return raw[off:off + size]
        raise ValueError(('ELF address absent', hex(pc), size))

    code = {}
    for s in sections:
        if not s[2] & 4:
            continue
        pc, end = s[3], s[3] + s[5]
        while pc < end:
            first = int.from_bytes(at(pc, 2), 'little')
            size = 4 if first & 3 == 3 else 2
            assert pc + size <= end
            code[pc] = int.from_bytes(at(pc, size), 'little')
            pc += size
    return at, code


def main():
    pins = read(P / 'pins.json')
    assert len(pins) == 129
    for path, digest in pins.items():
        assert sha(path) == digest, path
    proof = read(P / 'proof.json')
    status = read(P / 'software_status.json')
    assert status['pins_sha256'] == sha(P / 'pins.json')
    assert status['host_runs'] == 20
    original = ARCH / 'overlay/opt/ara-tests/rvv_matrix_e8_mf2'
    assert sha(original) == sha(HERE.parent / 'recovery22/rvv_matrix_e8_mf2')
    assert sha(original) == '2e16fe0a09238c14efb89b28326190c15225b10680138e7339f07c8541f38093'
    _, oldcode = elf(original)
    result = {'status': 'HOST_COMPILE_ARTIFACTS_ACCEPTED_NOT_REFERENCE_NOT_DUT',
              'verified_pins': len(pins), 'host_receipts': [], 'backends': {}}
    for variant in ('original', 'packed'):
        base = P / ('host_' + variant)
        assert read(base / 'compile.log.exit.json')['returncode'] == 0
        for n in range(10):
            log = base / f'case{n}.log'
            receipt = read(Path(str(log) + '.exit.json'))
            expected_rc = -4 if n == 8 else (0 if n == 0 else 1)
            assert type(receipt['returncode']) is int and receipt['returncode'] == expected_rc
            assert log.read_bytes() == (P / 'host_original' / log.name).read_bytes()
            if n != 8:
                text = log.read_text()
                assert 'HOST_FULL4095 positions=262080 guards=8190 masks=524160 calls=4095' in text
                assert ('RVV_MATRIX_PASS' in text) == (n == 0)
                assert ('RVV_MATRIX_FAILED' in text) == (n != 0)
            result['host_receipts'].append({'variant': variant, 'mutation': n,
                                           **receipt, 'log_sha256': sha(log)})
    sequence = read(P / 'sequence.json')
    assert len(sequence) == 4095
    expected_order = []
    kinds = [0] * 19 + [1, 1, 1, 2, 3, 0]
    for seed in range(3):
        for op in range(25):
            for li, vl in enumerate((0, 1, 2, 3, 32, 63, 64)):
                for mode in range(3):
                    for si in range(3 if kinds[op] == 0 else 1):
                        start = (0, vl // 2, vl if vl < 64 else 63)[si]
                        expected_order.append((seed, op, li, vl, mode, si, start))
    for i, (row, expected) in enumerate(zip(sequence, expected_order)):
        assert row['ordinal'] == i + 1
        assert tuple(row[k] for k in ('seed', 'op', 'li', 'vl', 'mode', 'si', 'start')) == expected
        assert len(row['words']) == 9 and 0 <= row['words'][-1] < 65536
    rom = b''.join(struct.pack('<9Q', *row['words']) for row in sequence)
    for backend in ('soc', 'spike'):
        base = P / backend
        assert read(base / 'compile.log.exit.json')['returncode'] == 0
        actual, code = elf(base / 'program.elf')
        b = proof['backends'][backend]
        assert sha(base / 'program.elf') == b['sha256']
        symbols = read(base / 'symbols.json')
        allowed = set()
        count = 0
        for name in ['capacity'] + [f'op_{n}' for n in range(25)]:
            oldpc = 0x10856 if name == 'capacity' else 0x1085e + 0x30 * int(name[3:])
            pc = symbols[name]
            window = b['helpers'][name]
            assert len(window) == (3 if name == 'capacity' else 13)
            for row in window:
                insn = code[pc]
                assert row == {'pc': pc, 'insn': insn}
                assert insn == oldcode[oldpc]
                allowed.add(pc)
                size = 4 if insn & 3 == 3 else 2
                oldpc += size
                pc += size
                count += 1
            assert insn in (0x8082, 0x00008067)
        extra = [hex(pc) for pc, insn in code.items() if insn & 3 == 3 and
                 ((insn & 127) == 0x57 or ((insn & 127) in (7, 39) and
                  (insn >> 12) & 7 in (0, 5, 6, 7))) and pc not in allowed]
        assert not extra, extra
        assert actual(symbols['expected_words'], len(rom)) == rom
        assert b['stack_top'] - b['bss_end'] == b['stack_gap'] > 65536
        result['backends'][backend] = {'sha256': b['sha256'], 'helper_instructions_matched': count,
                                      'extra_RVV': extra, 'ROM_bytes_matched': len(rom),
                                      'stack_gap': b['stack_gap']}
    result['inputs'] = {name: sha(P / name) for name in
                       ('software_status.json', 'proof.json', 'pins.json', 'compiled_review.json',
                        'prepare.py', 'model.py', 'host.c', 'packed.h', 'source.diff', 'sequence.json')}
    result['scope'] = {'calls': 4095, 'results': 262080, 'guards': 8190, 'vstart': 4095}
    out = HERE / 'artifact_result.json'
    with out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps({'status': result['status'], 'pins': len(pins), 'host_receipts': 20,
                      'backends': result['backends'], 'result_sha256': sha(out)}, indent=2))


if __name__ == '__main__':
    main()
