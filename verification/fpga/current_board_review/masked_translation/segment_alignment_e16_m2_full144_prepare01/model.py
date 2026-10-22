"""Original complete144 geometry and independent byte oracle; no DUT imports."""
import hashlib
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
C = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
R = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
A = C / 'rvv_segment_alignment01'
NAME = 'rvv_segment_alignment_e16_m2'
SIZE, CAP = 8192, 128
FILL = bytes([0x5b]) * SIZE
INPUT = bytes(((i * 73 + (i >> 4) * 37) ^ 0x85) & 255 for i in range(SIZE))
MEMORY = bytes(((i * 19 + (i >> 3) * 43) ^ 0xd3) & 255 for i in range(SIZE))

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def cases():
    result = []
    for op in range(8):
        nf = 3 + op // 4
        for reverse in range(2 if op % 4 >= 2 else 1):
            for offset in (0, 1):
                for vl in (0, 1, CAP):
                    for off in (0, 1):
                        stride = (nf + (2 if op % 4 >= 2 else 0)) * 2
                        base = 64 + offset + ((CAP - 1) * stride if reverse else 0)
                        result.append(dict(id=len(result), op=op, nf=nf, reverse=reverse,
                                           offset=offset, vl=vl, off=off, base=base,
                                           stride=-stride if reverse else stride, store=op % 2))
    require(len(result) == 144, 'Original144, not prefix')
    return result

def expected(c):
    """Literal original byte-coordinate oracle, independent of packed ROM copy."""
    out = bytearray(FILL)
    if not c['off']:
        for i in range(c['vl']):
            for f in range(c['nf']):
                for b in range(2):
                    packed = 64 + (f * CAP + i) * 2 + b
                    at = c['base'] + i * c['stride'] + 2 * f + b
                    require(0 <= at < SIZE and 0 <= packed < SIZE, 'Original bounds')
                    out[at if c['store'] else packed] = INPUT[packed] if c['store'] else MEMORY[at]
    return bytes(out)

def independent_expected(c):
    """Halfword gather/scatter construction, not the original nested byte loop."""
    out = bytearray(FILL)
    if c['off']:
        return bytes(out)
    for field in range(c['nf']):
        for element in range(c['vl']):
            flat = 64 + 256 * field + 2 * element
            physical = c['base'] + 2 * field + c['stride'] * element
            source, src, dst = (INPUT, flat, physical) if c['store'] else (MEMORY, physical, flat)
            value = struct.unpack_from('<H', source, src)[0]
            struct.pack_into('<H', out, dst, value)
    return bytes(out)

def tables():
    rows, ids = [], []
    for c in cases():
        row = expected(c)
        require(row == independent_expected(c), 'Independent oracle disagreement')
        if row not in rows:
            rows.append(row)
        ids.append(rows.index(row))
    return rows, ids

def header():
    rows, ids = tables()
    lines = ['/* Generated exact-byte ROM; no target-output-derived values. */', '#include <stdint.h>',
             'struct config { uint64_t op,nf,reverse,offset,vl,off,base; int64_t stride; uint64_t oracle; };']
    def array(name, data):
        vals = struct.unpack('<1024Q', data)
        lines.append('static const uint64_t ' + name + '[1024] __attribute__((aligned(64))) = {')
        lines.extend(','.join('UINT64_C(0x%016x)' % x for x in vals[i:i+4]) + ',' for i in range(0, 1024, 4))
        lines.append('};')
    array('rom_input', INPUT)
    array('rom_memory', MEMORY)
    for i, row in enumerate(rows):
        array('rom_expected_%d' % i, row)
    lines.append('static const uint64_t *const rom_expected[] = {' + ','.join('rom_expected_%d' % i for i in range(len(rows))) + '};')
    lines.append('static const struct config configs[144] = {')
    for c, rid in zip(cases(), ids):
        lines.append('{%d,%d,%d,%d,%d,%d,%d,%d,%d},' % tuple([c[k] for k in ('op','nf','reverse','offset','vl','off','base','stride')] + [rid]))
    lines.append('};')
    return '\n'.join(lines) + '\n'
