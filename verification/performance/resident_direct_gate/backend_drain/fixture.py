"""Known dyadic inputs; exact rational golden, no RTL/SDK arithmetic helper."""
from fractions import Fraction as F
import json
from pathlib import Path
import struct

CASES = {
    "row": dict(insn=0x02053c5b, vd=24, eew=1, vl=128, csr_rd=28, early=True),
    "column": dict(insn=0x0205785b, vd=16, eew=1, vl=256, csr_rd=29, early=True),
    "qk": dict(insn=0x0605705b, vd=0, eew=2, vl=128, csr_rd=30, early=False),
    "pv": dict(insn=0x0485705b, vd=0, eew=1, vl=256, csr_rd=31, early=False),
}


def exact(value, fmt):
    raw = struct.pack("<" + fmt, float(value))
    if F(struct.unpack("<" + fmt, raw)[0]) != value:
        raise ValueError("Fixture intermediate is not exactly representable")
    return raw


def fixture():
    q = [[F((d + h) % 5 - 2, 2) for d in range(128)] for h in range(2)]
    k = [[F(t % 7 + d % 5 - 5, 8) for d in range(128)] for t in range(64)]
    v = [[F(t % 5 + d % 9 - 6, 8) for d in range(128)] for t in range(64)]
    seed = [[F((h + 1) * (d % 7 - 3), 16) for d in range(128)] for h in range(2)]
    coeff = [[F(t % 3 - 1, 8), F(2 if t % 2 else -1, 16)] for t in range(64)]
    scores, result = [], []
    for h in range(2):
        for t in range(64):
            total = F(0)
            for d in range(128):
                total += q[h][d] * k[t][d]
                exact(total, "f")
            scores.append(exact(total, "f"))
        for d in range(128):
            total = seed[h][d]
            for t in range(64):
                total += coeff[t][h] * v[t][d]
                exact(total, "e")
            result.append(exact(total, "e"))
    half = lambda rows: b"".join(exact(x, "e") for row in rows for x in row)
    source = half(seed) + half(coeff) + bytes.fromhex("5aa5") * 128
    data = dict(query_data=half(q), key_data=half(k), value_data=half(v), pv_source=source)
    expected = dict(row=half([v[63]]), column=half([[k[t][d] for t in range(64)] for d in range(20, 24)]),
                    qk=b"".join(scores), pv=b"".join(result), source=source)
    return data, expected


def generate(directory):
    directory = Path(directory)
    data, expected = fixture()
    assembly = ['.section .rodata']
    for name, raw in data.items():
        path = directory / (name + ".bin")
        path.write_bytes(raw)
        assembly += ['.balign 64', '.globl ' + name, name + ':', '.incbin ' + json.dumps(str(path))]
    for name, raw in expected.items():
        path = directory / ('expected_' + name + '.bin')
        path.write_bytes(bytes([0xa5]) * 64 + raw + bytes([0xa5]) * 64)
        assembly += ['.balign 64', '.globl expected_' + name, 'expected_' + name + ':',
                     '.incbin ' + json.dumps(str(path))]
    assembly += ['.section .note.GNU-stack,"",@progbits']
    (directory / 'data.S').write_text('\n'.join(assembly) + '\n')
    golden = dict(schema=1, geometry=dict(lanes=4, vlen=1024, D=128, T=64, H=2),
                  arithmetic='exact rational sums; each PV FMA result exactly FP16, each QK result exactly FP32',
                  fcsr=1, cases=CASES, expected={k: v.hex() for k, v in expected.items()})
    (directory / 'golden.json').write_text(json.dumps(golden, indent=2) + '\n')
    return golden
