#!/usr/bin/env python3
"""Strict four-arm GGML functional evidence check, never a timing oracle."""
import hashlib
import math
from pathlib import Path
import re
import struct

ARMS = ('m8', 'm4', 'shape', 'rvv')
K, N, KB, Q8 = 2048, 64, 8, 292
# Frozen GGML test-ara-q4k-repack.cpp graph tolerance, fixed before execution.
RVV_ATOL, RVV_RTOL = 2e-4, 2e-5


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(line, prefix):
    require(line.startswith(prefix + ' '), 'Wrong record prefix')
    pairs = [part.split('=', 1) for part in line[len(prefix)+1:].split()]
    require(all(len(p) == 2 for p in pairs) and len({p[0] for p in pairs}) == len(pairs),
            'Malformed/duplicate fields')
    return dict(pairs)


def geometry(arm):
    require(arm in ARMS, 'Unknown arm')
    rows = 4 if arm == 'shape' else 8
    tm, tn = (8, 16) if arm == 'm8' else (4, 32)
    return rows, tm, tn


def command_shapes(arm):
    rows, tm, tn = geometry(arm)
    return [] if arm == 'rvv' else [(r, c, tm, tn) for r in range(0, rows, tm)
                                  for c in range(0, N, tn)]


def check_arm(arm, text, oracle):
    oracle = Path(oracle)
    text = text.replace('\r', '')
    require(not re.search(r'G4_FAIL|\bSKIP\b|Kernel panic|Illegal instruction|Segmentation fault|'
                          r'Assertion .*failed|terminate called|timed out', text, re.I),
            'Guest failure/skip')
    rows, tm, tn = geometry(arm)
    shapes = command_shapes(arm)
    lines = [line for line in text.splitlines() if line.startswith('G4_')]
    require(lines and lines[0].startswith('G4_META ') and
            lines[-1] == f'G4_EXIT arm={arm} code=0', 'Missing terminal/metadata')
    meta = fields(lines[0], 'G4_META')
    expected = dict(arm=arm, m=str(rows), n='64', k='2048', wide=str(int(arm == 'm8')),
                    qbs=str(int(arm != 'rvv')), graph_calls='1', commands=str(len(shapes)),
                    workspace_bytes=str(rows*KB*Q8), flags_probe='1')
    require(set(meta) == set(expected) | {'info_calls'} and
            all(meta[k] == v for k, v in expected.items()), 'Wrong actual dispatch metadata')
    require(meta['info_calls'].isdigit() and
            (int(meta['info_calls']) == 0 if arm == 'rvv' else int(meta['info_calls']) > 0),
            'Wrong native probe count')
    byte_lines, commands = {}, []
    end = False
    for line in lines[1:-1]:
        require(not end, 'Record after PASS')
        if line.startswith('G4_BYTES '):
            f = fields(line, 'G4_BYTES')
            require(set(f) == {'kind', 'command', 'offset', 'hex'} and
                    f['command'].isdigit() and f['offset'].isdigit() and
                    re.fullmatch(r'(?:[0-9a-f]{2}){1,32}', f['hex']), 'Malformed bytes')
            key = (f['kind'], int(f['command']))
            data = byte_lines.setdefault(key, bytearray())
            require(int(f['offset']) == len(data) and len(data) % 32 == 0,
                    'Missing/duplicate/out-of-order byte chunk')
            data.extend(bytes.fromhex(f['hex']))
        elif line.startswith('G4_COMMAND '):
            commands.append(fields(line, 'G4_COMMAND'))
        elif line == f'G4_PASS arm={arm} outputs={rows*N} integrity=1 cycles_measured=0':
            end = True
        else:
            raise ValueError('Unknown/duplicate G4 record: ' + line[:160])
    require(end and len(commands) == len(shapes), 'Incomplete commands/PASS')
    mode = 'm4' if arm == 'rvv' else arm
    packed = (oracle / f'workspace_{mode}.bin').read_bytes()
    golden = (oracle / 'output.bin').read_bytes()[:rows*N*4]
    require(len(packed) == rows*KB*Q8 and len(golden) == rows*N*4, 'Oracle dimensions')
    expected_keys = {('workspace', 0), ('output', 0)} | {
        (kind, i) for i in range(len(shapes)) for kind in ('activation', 'command_output')}
    require(set(byte_lines) == expected_keys, 'Unexpected/missing byte streams')
    require(byte_lines['workspace', 0] == packed, 'Complete quantization bytes differ')
    result = bytes(byte_lines['output', 0])
    require(len(result) == len(golden), 'Output byte count')
    if arm != 'rvv':
        require(result == golden, 'QBS matrix output differs bitwise')
        flags = struct.unpack('<'+'I'*len(shapes), (oracle / f'flags_{arm}.bin').read_bytes())
        headers = struct.unpack('<'+'Q'*len(shapes), (oracle / f'headers_{arm}.bin').read_bytes())
        for i, ((row, col, m, n), actual) in enumerate(zip(shapes, commands)):
            seed = 8 if i % 2 else 0
            want = dict(id=str(i), m=str(m), n=str(n), kb='8', woff=str(col*KB*144),
                        aoff=str(row*KB*Q8), stride='64', seed=str(seed),
                        flags=str(flags[i] | seed), status='0', header=f'{headers[i]:016x}')
            require(actual == want, f'Descriptor/count/flags differ at command {i}')
            require(byte_lines['activation', i] == packed[row*KB*Q8:(row+m)*KB*Q8],
                    'SDK activation differs from complete GGML workspace')
            want_output = b''.join(golden[((row+r)*N+col)*4:((row+r)*N+col+n)*4]
                                   for r in range(m))
            require(byte_lines['command_output', i] == want_output, 'Native command output differs')
    else:
        for a, b in zip(struct.unpack('<'+'f'*(rows*N), result),
                        struct.unpack('<'+'f'*(rows*N), golden)):
            require(math.isfinite(a) and math.isfinite(b) and
                    abs(a-b) <= RVV_ATOL + RVV_RTOL*abs(b), 'Ordinary RVV fallback numerical mismatch')
    traces = re.findall(r'(?m)^GGML_RISCV_QBS_COMMAND ([^\n]+)$', text)
    require(len(traces) == len(shapes), 'Native trace command count')
    for trace, (_, _, m, n) in zip(traces, shapes):
        f = fields('TRACE '+trace, 'TRACE')
        require(all(f.get(k) == v for k, v in dict(weight_type='q4_K', m=str(m), n=str(n),
                    k_blocks='8', access='0', segmented='0', emulated='0').items()), 'Native trace geometry')
    require(('GGML_RISCV_QBS_CALL' not in text) if arm == 'rvv' else
            bool(re.search(r'GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=2048 .*split_k=0', text)),
            'Wrong backend call path')
    repacks = re.findall(r'(?m)^GGML_RISCV_REPACK=([^\n]+)$', text)
    wanted_repack = 'Q4_K_32x1_Q8_K shape=2048x64' if arm == 'rvv' else 'QBS type=q4_K shape=2048x64'
    require(repacks and set(repacks) == {wanted_repack}, 'Wrong real repack/fallback trait')
    return dict(state='PASS', arm=arm, quantized_bytes=len(packed), outputs=rows*N,
                actual_sdk_commands=len(shapes), complete_quantization_checked=True,
                native_bitexact_checked=arm != 'rvv', native_fflags_checked=arm != 'rvv',
                rvv_tolerance=[RVV_ATOL, RVV_RTOL] if arm == 'rvv' else None,
                workspace_sha256=hashlib.sha256(packed).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(), cycles_evidence=False)
