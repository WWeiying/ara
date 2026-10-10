#!/usr/bin/env python3
"""Strict RVFI/ELF checks for the two frozen scalar FENCE.T capture sequences.

The legacy CVA6 tracer retains issue-queue identities across microreset. Use
hardware-commit-PC RVFI instead; do not repair, filter or deduplicate its log.
This module does not grant coverage admission by itself.
"""
import csv
import io

MASK64 = (1 << 64) - 1
FIELDS = ('cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,'
          'mem_rmask,mem_wmask,mem_wdata,trap').split(',')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse_trace(text):
    reader = csv.DictReader(io.StringIO(text))
    require(reader.fieldnames == FIELDS, 'RVFI schema differs')
    rows = []
    for raw in reader:
        require(None not in raw and all(raw[k] is not None for k in FIELDS), 'Malformed RVFI row')
        row = {k: raw[k] if k == 'event' else int(raw[k], 16 if k in
               ('pc', 'insn', 'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata') else 10)
               for k in FIELDS}
        require(row['event'] == 'retire' and row['trap'] == 0, 'Unexpected RVFI event or trap')
        require(row['trans_id'] == -1, 'Frozen monitor transaction placeholder differs')
        require(row['order'] == len(rows), 'Skipped/duplicate RVFI retirement order')
        require(row['cycle'] >= 0 and row['port'] in (0, 1) and 0 <= row['rd'] < 32,
                'Invalid retirement coordinates')
        require(not rows or (row['cycle'], row['port']) > (rows[-1]['cycle'], rows[-1]['port']),
                'RVFI cycle/port order differs')
        for name in ('pc', 'rd_wdata', 'mem_addr', 'mem_wdata'):
            require(0 <= row[name] <= MASK64, 'Out-of-range RVFI data')
        require(0 <= row['mem_rmask'] <= 255 and 0 <= row['mem_wmask'] <= 255,
                'Out-of-range memory byte mask')
        rows.append(row)
    require(rows, 'Empty RVFI stream')
    return rows


def elf_instructions(metadata, blob):
    result = {}
    for item in metadata['Sections']:
        sec = item['Section']
        if not sec['Flags']['Value'] & 4:
            continue
        data = blob[sec['Offset']:sec['Offset'] + sec['Size']]
        require(len(data) == sec['Size'], 'Truncated ELF section')
        offset = 0
        while offset < len(data):
            half = int.from_bytes(data[offset:offset + 2], 'little')
            length = 4 if half & 3 == 3 else 2
            require(offset + length <= len(data) and (length == 2 or half & 31 != 31),
                    'Unsupported/truncated ELF instruction')
            pc = sec['Address'] + offset
            require(pc not in result, 'Overlapping executable sections')
            result[pc] = int.from_bytes(data[offset:offset + length], 'little')
            offset += length
    require(result, 'No executable ELF instructions')
    return result


def seed(round_id, reg, fp):
    base = 0x3ff13579bdf02468 if fp else 0x91a2b3c4d5e6f780
    return (base ^ (0x0102040810204081 * (reg + 1)) ^
            (0x5a963ce18742b0df if round_id else 0)) & MASK64


def audit_rows(rows, metadata, blob, sites):
    code = elf_instructions(metadata, blob)
    syms = {s['Symbol']['Name']['Name']: s['Symbol'] for s in metadata['Symbols']}
    trap = syms['gap36_trap']
    require(trap['Size'] > 0, 'Missing trap-handler extent')
    require(sum(r['pc'] == 0x80000000 for r in rows) == 1 and rows[0]['pc'] == 0x80000000,
            'Missing/duplicate boot')
    for row in rows:
        require(code.get(row['pc']) == row['insn'], 'RVFI opcode/PC differs from ELF')
        require(not trap['Value'] <= row['pc'] < trap['Value'] + trap['Size'],
                'Unexpected trap-handler execution')
    observed = syms['observed']['Value'] + 8
    require(syms['observed']['Size'] == 536 and syms['probe_stack']['Size'] == 1024,
            'Capture object/stack layout differs')
    stack = syms['probe_stack']['Value'] + syms['probe_stack']['Size']
    require(len(sites) == 2, 'Two capture sites required')
    returns = [i for i, r in enumerate(rows) if r['insn'] in (0x30200073, 0x10200073, 0x7b200073)]
    require(returns and rows[returns[0]]['insn'] == 0x30200073, 'Missing/changed initial MRET')
    actual_fences = [i for i, row in enumerate(rows) if row['insn'] & 0x7f == 0x0b]
    rounds, positions = [], []
    for round_id, site in enumerate(sites):
        pc = int(site['fence_pc'], 16)
        resume, auipc = int(site['resume_pc'], 16), int(site['auipc_pc'], 16)
        require(resume == pc + 4 and auipc == pc + 8, 'Capture layout differs')
        indices = [i for i, row in enumerate(rows) if row['pc'] == pc]
        require(len(indices) == 1, 'Missing/duplicate FENCE.T retirement')
        index = indices[0]
        require(index < returns[0] and rows[index]['insn'] == 0x0b,
                'Fence outside reset-M region or noncanonical opcode')
        require(rows[index]['port'] == rows[index]['rd'] == rows[index]['mem_rmask'] ==
                rows[index]['mem_wmask'] == 0, 'FENCE.T port or architectural side effect differs')
        # 67 straight-line instructions: 65 distinct stores, AUIPC, FENCE.
        capture = rows[index + 1:index + 68]
        require(len(capture) == 67, 'Truncated capture')
        expected_pcs = [resume + 4 * i for i in range(67)]
        require([r['pc'] for r in capture] == expected_pcs, 'Capture control flow differs')
        require(capture[0]['cycle'] > rows[index]['cycle'], 'Resume overlaps serializing FENCE.T')
        wanted = set(expected_pcs)
        require(sum(r['pc'] in wanted for r in rows) == 67, 'Duplicate capture retirement')
        require(capture[1]['rd'] == 30 and capture[1]['rd_wdata'] == auipc,
                'AUIPC architectural result differs')
        stores = {}
        for row in capture:
            word = row['insn']
            if word & 0x7f in (0x23, 0x27):
                require((word >> 12) & 7 == 3 and (word >> 15) & 31 == 31,
                        'Not expected 64-bit capture store')
                offset = ((word >> 25) << 5) | ((word >> 7) & 31)
                require(offset < 2048 and row['mem_addr'] == observed + offset,
                        'Capture store address differs')
                require(row['mem_wmask'] == 255 and row['mem_rmask'] == 0 and row['rd'] == 0,
                        'Capture store masks/destination differ')
                require(row['port'] == 0, 'Store cannot retire on frozen CVA6 port one')
                require(offset not in stores, 'Duplicate capture location')
                reg = (word >> 20) & 31
                if word & 0x7f == 0x27:
                    require(offset == 256 + 8 * reg, 'Wrong FPR capture offset')
                    value = seed(round_id, reg, True)
                elif offset == 512:
                    require(reg == 30, 'Wrong PC capture source')
                    value = auipc
                else:
                    require(offset == 8 * reg, 'Wrong GPR capture offset')
                    value = 0 if reg == 0 else stack if reg == 2 else observed if reg == 31 else seed(round_id, reg, False)
                require(row['mem_wdata'] == value, 'Capture architectural store data differs')
                stores[offset] = {'cycle': row['cycle'], 'pc': hex(row['pc']), 'data': hex(value)}
            else:
                require(row['mem_rmask'] == row['mem_wmask'] == 0, 'Unexpected capture memory event')
                if word & 0x7f == 0x0f:
                    require(row['rd'] == 0, 'FENCE cannot write an architectural register')
        require(set(stores) == set(range(0, 520, 8)), 'Missing capture register/PC store')
        rounds.append({'round': round_id, 'fence_order': index, 'fence_cycle': rows[index]['cycle'],
                       'resume_cycle': capture[0]['cycle'], 'capture_instructions': 67,
                       'checked_stores': stores})
        positions.append(index)
    require(positions == sorted(positions) and positions == actual_fences, 'Extra/reordered custom instruction')
    return {'status': 'PASS', 'retired_records': len(rows), 'opcode_elf_matches': len(rows),
            'rounds': rounds, 'exact_pc4_resume': True, 'capture_stores_checked': 130,
            'privilege_evidence': 'Both sites before first xRET after reset-M, plus M-CSR selfchecks; CSV has no mode field',
            'legacy_trace_used_as_oracle': False,
            'scope': 'RVFI/ELF and capture values; also requires UART and native controller activity'}


def audit(text, metadata, blob, sites):
    return audit_rows(parse_trace(text), metadata, blob, sites)
