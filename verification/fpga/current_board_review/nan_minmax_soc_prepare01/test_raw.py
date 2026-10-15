"""Corrupt actual raw effects in memory; never alter archived/reference logs."""
import time
from common import *
from check_reference import extract, specification, LINE, VECTOR, CSR, REG


def run(dest, raw):
    spec = specification(dest)
    helper = spec['helper']
    cases = [
        ('raw_input_vector', 4, 'vector', 0),
        ('raw_seed_vector', 1, 'vector', 0),
        ('raw_mask_vector', 5, 'vector', 0xffffffff),
        ('raw_result_payload_canonical_swap', 11, 'vector',
         (spec['config']['expected'] ^ 0x12345) | (int.from_bytes(b'\x5b'*124,'little') << 32)),
        ('raw_result_infinity', 11, 'vector',
         0x7f800000 | (int.from_bytes(b'\x5b'*124,'little') << 32)),
        ('raw_result_flags', 11, 'fflags', 16),
        ('raw_result_vstart', 11, 'vstart', 1),
        ('raw_full144_guard', None, 'register', 0),
        ('raw_wrong_opcode', 11, 'opcode', 0x14881c57),
    ]
    rows = []
    for name, index, field, value in cases:
        pc = spec['output_lbu'][0] if index is None else helper[index][0]
        changed = [False]
        def mutation(line):
            m = LINE.fullmatch(line.rstrip('\n'))
            if changed[0] or not m or int(m[1],16) != pc:
                return line
            changed[0] = True
            if field == 'vector':
                require(VECTOR.search(line) is not None, 'raw witness has vector effect')
                return VECTOR.sub(lambda m:f'v{m[1]} 0x{value:0256x}', line, count=1)
            if field in ('fflags','vstart'):
                require(any(m[1] == field for m in CSR.finditer(line)), 'raw witness has CSR effect')
                return CSR.sub(lambda m:m[0] if m[1] != field else
                               m[0].split(' 0x')[0]+f' 0x{value:016x}',line)
            if field == 'register':
                require(REG.search(line) is not None, 'raw witness has LBU result')
                return REG.sub(lambda m:f'x{m[1]} 0x{value:016x}',line,count=1)
            return line.replace(m[2], f'0x{value:08x}', 1)
        started = time.monotonic()
        try:
            extract(dest, raw, mutation)
        except ValueError as error:
            require(changed[0], 'raw mutation did not reach authentic target')
            reason = str(error)
            expected = ('raw full144B oracle byte' if field == 'register' else
                        'actual ELF PC/encoding' if field == 'opcode' else
                        'raw bitwise result/flags/vstart' if index == 11 else
                        'raw vector input/seed/mask/old-vd data')
            require(reason == expected, 'raw negative first-cause: '+reason)
            rows.append({'negative':name,'rejected':reason,'elapsed_s':time.monotonic()-started})
        else:
            raise ValueError('raw negative accepted: '+name)
    return {'status':'PASS_HOST_RAW_NEGATIVES_ONLY','source_raw_sha256':sha(raw),
            'source_raw_unchanged':True,'negatives':rows,'DUT_run':False}
