"""Host-only synthetic RVFI, actual SoC specs and full original model counts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

sys.dont_write_bytecode = True
import checker as c
import replay as r


def records(spec, gold, mutation=None):
    s, code = spec['backend']['symbols'], {int(k): v for k, v in spec['backend']['code'].items()}
    helper_pcs = {x['pc'] for rows in spec['backend']['helpers'].values() for x in rows}
    width = spec['config']['sew'] // 8
    assignments = {}
    stores, loads, candidates = {}, {}, []
    for pc, insn in code.items():
        if pc in helper_pcs or pc in (s['_start'], s['main'], s['failure']):
            continue
        if insn & 3 == 3 and insn & 127 in (0x13, 0x1b, 0x17, 0x37, 0x33, 0x3b):
            assignments.setdefault((insn >> 7) & 31, pc)
        d = c.memory_op(insn)
        if pc >= s['selected'] and d and d['base'] != d['register'] and d['base'] and d['register']:
            candidates.append((pc, d))
    for pc, d in candidates:
        if d['base'] in assignments and d['register'] in assignments:
            (stores if d['kind'] == 'write' else loads).setdefault(d['size'], (pc, d))
    order = 0
    cached = {}
    def row(pc, rd=0, value=0, addr=0, rm=0, wm=0, data=0):
        nonlocal order
        out = dict(cycle=str(order + 1), event='retire', order=str(order), port='0', trans_id='-1',
                   pc=f'{pc:016x}', insn=f'{code[pc]:08x}', rd=str(rd), rd_wdata=f'{value & c.MASK64:016x}',
                   mem_addr=f'{addr:016x}', mem_rmask=f'{rm:02x}', mem_wmask=f'{wm:02x}',
                   mem_wdata=f'{data & c.MASK64:016x}', trap='0')
        order += 1
        return out
    def setreg(reg, value):
        return row(assignments[reg], reg, value)
    def write(addr, value, size, pc=None, desc=None):
        # Host fixture optimization only: every call still checks every setup byte.
        if 0x80000000 <= addr < 0x90000000:
            data = [(value >> (8 * j)) & 255 for j in range(size)]
            if all(cached.get(addr + j) == byte for j, byte in enumerate(data)):
                return
            cached.update({addr + j: byte for j, byte in enumerate(data)})
        pc, d = (pc, desc) if pc is not None else stores[size]
        yield setreg(d['base'], addr - d['offset'])
        if d['register']:
            yield setreg(d['register'], value)
        yield row(pc, addr=addr, wm=((1 << size) - 1) << (addr % 8), data=value)
    def text(text):
        for byte in text.encode('ascii'):
            yield from write(spec['uart'], byte, 1)
    yield row(s['_start'], 3, 0)
    for pc in spec['csr_prelude'][:5]:
        yield row(pc)
    yield setreg(6, s['__bss_end'])
    for addr in range(s['__bss_start'], s['__bss_end'], 8):
        yield setreg(5, addr)
        yield row(spec['bss_store'], addr=addr, wm=255, data=0)
    yield row(s['main'])
    pc = spec['csr_prelude'][5]
    yield row(pc, (code[pc] >> 7) & 31, 128)
    yield from text('BOARD_CASE_BEGIN ' + spec['config']['id'] + '\n')
    for i, x in enumerate(spec['backend']['helpers']['capacity']):
        yield row(x['pc'], 5 if i == 0 else 10 if i == 1 else 0, c.MASK64 if i == 0 else c.CAP if i == 1 else 0)
    for ordinal, g in enumerate(gold):
        for name, values, size in (('a', g['a'], width), ('b', g['b'], width), ('mask', g['mask'], 1), ('out', [91] * (c.CAP + 2), width)):
            for j, value in enumerate(values):
                if mutation == 'fp_setup' and g['op'] == 25 and name == 'a' and j == 0:
                    value ^= 1
                yield from write(s[name] + j * size, value, size)
        args = [s['a'], s['b'], s['out'] + width, g['vl'], c.CAP, s['mask'], g['vstart']]
        if mutation == 'args' and ordinal == 0:
            args[1] += width
        for reg, value in enumerate(args, 10):
            yield setreg(reg, value)
        window = spec['backend']['helpers'][f'op_{g["op"]}']
        for i, x in enumerate(window):
            rd, val = 0, 0
            if i in (0, 5, 10):
                rd, val = 5, g['vl'] if i == 5 else c.CAP
            if i == 6:
                rd, val = 28, 7
            if i == 9:
                rd, val = 10, 1 if mutation == 'vstart' and ordinal == 0 else 0
            item = row(x['pc'], rd, val)
            if mutation == 'encoding' and ordinal == 0 and i == 8:
                item['insn'] = 'deadbeef'
            if mutation == 'duplicate_window' and ordinal == 0 and i == 12:
                yield row(window[8]['pc'])
            yield item
        if mutation == 'early_end' and ordinal == 0:
            return
        pc, d = loads[width]
        for element in range(c.CAP + 2):
            expected = 91 if element in (0, c.CAP + 1) else g['expected'][element - 1]
            lane = element - 1
            if 0 <= lane < c.CAP and g['op'] == 0:
                active = g['vstart'] <= lane < g['vl'] and (g['mask'][lane // 8] >> (lane % 8)) & 1
                inactive = g['vstart'] <= lane < g['vl'] and not (g['mask'][lane // 8] >> (lane % 8)) & 1
                if ((mutation == 'active' and active) or (mutation == 'inactive' and inactive) or
                        (mutation == 'prestart' and lane < g['vstart']) or (mutation == 'tail' and lane >= g['vl'])):
                    expected ^= 1
            if mutation == 'result' and ordinal == 0 and element == 1:
                expected ^= 1
            if mutation == 'guard' and ordinal == 0 and element == c.CAP + 1:
                expected ^= 1
            if mutation == 'last_guard' and ordinal == len(gold) - 1 and element == c.CAP + 1:
                expected ^= 1
            if mutation == 'missing_tail' and ordinal == 0 and element == c.CAP:
                continue
            address = s['out'] + element * width
            yield setreg(d['base'], address - d['offset'])
            value = c.loaded_value(expected, width, d['signed'])
            item = row(pc, d['register'], value, addr=address, rm=((1 << width) - 1) << (address % 8))
            if mutation == 'wrong_rmask' and ordinal == 0 and element == 1:
                item['mem_rmask'] = 'ff'
            if mutation == 'wrong_sign' and ordinal == 0 and element == 1:
                item['rd_wdata'] = f'{value | (1 << 63):016x}'
            yield item
    for name, value in (('checks', len(gold)), ('elements', c.CAP * len(gold)), ('errors', 0)):
        yield from write(s[name], value, 8)
    yield from text(c.marker(spec['config']) + '\nARITHMETIC_FULL_PASS ' + spec['config']['id'] + '\nBOARD_REPLAY_PASS\n')
    pc = spec['exit_store']
    yield from write(spec['ctrl'], 1 if mutation == 'htif1' else 0, 8, pc, c.memory_op(code[pc]))
    yield row(spec['park'])
