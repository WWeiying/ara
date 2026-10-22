#!/usr/bin/env python3
"""Offline complete original-single raw audit; never runs a simulator."""
from collections import Counter
import copy
import json
import re
import sys

sys.dont_write_bytecode = True
from prepare import HERE, MARKER, sha, save

OUT = HERE / 'reference03M'
LINE = re.compile(r'^core\s+0:\s+3\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)$')
REG = re.compile(r'\bx(\d+)\s+(0x[0-9a-f]+)')
CSR = re.compile(r'\bc\d+_(\w+)\s+(0x[0-9a-f]+)')
MEM = re.compile(r'\bmem\s+(0x[0-9a-f]+)(?:\s+(0x[0-9a-f]+))?')
VECTOR = re.compile(r'\bv(\d+)\s+(0x[0-9a-f]+)')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def extract():
    syms = json.loads((HERE / 'spike/symbols.json').read_text())
    proof = json.loads((HERE / 'sourceproof.json').read_text())
    expected_helper = proof['helper_windows']['spike']['op_0']['new']
    helper_map = {r[0]: i for i, r in enumerate(expected_helper)}
    fixture = [(int(a, 16), int(b)) for a, b in re.findall(
        r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}',
        (HERE / 'prepared/fixtures.h').read_text())]
    regs = [0] * 32
    memory = {}
    counts = Counter()
    pcs = Counter()
    reads, helper, fixture_reads, selected_fixture = [], [], [], []
    setup = None
    terminal = None
    park = 0
    total = 0
    firmware = 0
    tracked = [(syms[n], syms[n] + size) for n, size in
               [('input', 1024), ('seed', 128), ('mask', 64), ('output', 144), ('replay_log', 8192)]]

    def getbytes(name, size):
        return [memory.get(syms[name] + i) for i in range(size)]

    with (OUT / 'commits.log').open() as stream:
        for line in stream:
            match = LINE.fullmatch(line.rstrip('\n'))
            require(match is not None, 'unparsed raw line: ' + line[:160])
            pc, insn, suffix = int(match[1], 16), int(match[2], 16), match[3]
            total += 1
            firmware += pc >= 0x80000000
            pcs[pc] += 1
            writes = {int(r): int(v, 16) for r, v in REG.findall(suffix)}
            csrs = {n: int(v, 16) for n, v in CSR.findall(suffix)}
            vectors = {n: int(v, 16).to_bytes(128, 'little').hex()
                       for n, v in VECTOR.findall(suffix)}
            mem = [[int(a, 16), int(v, 16) if v else None] for a, v in MEM.findall(suffix)]
            if terminal is not None:
                require(pc == 0x8000007e and insn == 0xa001 and not
                        (writes or csrs or vectors or mem), 'post-HTIF instruction is not original empty park')
                park += 1
            if pc == syms['op_0']:
                require(setup is None, 'duplicate helper')
                setup = {'args': regs[10:18], 'input': getbytes('input', 32),
                         'seed': getbytes('seed', 128), 'mask': getbytes('mask', 64),
                         'output': getbytes('output', 144), 'ordinal': total}
            if pc in helper_map:
                helper.append({'index': helper_map[pc], 'ordinal': total, 'pc': pc,
                               'insn': f'{insn:0{len(expected_helper[helper_map[pc]][1])}x}',
                               'regs': {str(k): v for k, v in writes.items()},
                               'csrs': csrs, 'vectors': vectors, 'memory': mem})
            require(pc not in (syms['op_1'], syms['op_2'], syms['trap_entry']), 'unexpected helper/trap')
            if pc in (0x8000050e, 0x80000510):
                require(len(mem) == 1 and mem[0][1] is None and len(writes) == 1, 'fixture load format')
                offset = mem[0][0] - syms['fixtures']
                row, field = divmod(offset, 16)
                require(3360 <= row < 6720 and field in (0, 8), 'fixture bank/address')
                value = next(iter(writes.values()))
                require(value == fixture[row][field // 8], 'fixture value')
                fixture_reads.append([row, field])
                if row == 4905:
                    selected_fixture.append({'pc': pc, 'address': mem[0][0], 'value': value})
            if pc == 0x800005d6:
                require(insn == 0x00064803 and len(mem) == 1, 'LBU encoding')
                require(len(writes) == 1 and 16 in writes and mem[0][1] is None, 'LBU result')
                reads.append([mem[0][0] - syms['output'], writes[16]])
            for address, value in mem:
                if value is None:
                    continue
                if address == syms['tohost']:
                    require(terminal is None and pc == 0x8000007a and insn == 0x00a2b023,
                            'HTIF exit origin')
                    terminal = {'ordinal': total, 'firmware_retired': firmware, 'pc': pc, 'value': value}
                if pc == 0x80000782:
                    size = 2
                elif insn & 0x7f == 0x23:
                    size = 1 << ((insn >> 12) & 7)
                    require(size <= 8, 'scalar store width')
                elif insn & 3 in (0, 2) and insn >> 13 in (6, 7):
                    size = 4 if insn >> 13 == 6 else 8
                else:
                    require(not any(lo <= address < hi for lo, hi in tracked), 'unclassified tracked store')
                    continue
                if any(lo <= address < hi for lo, hi in tracked):
                    for i, byte in enumerate(value.to_bytes(size, 'little')):
                        memory[address + i] = byte
                if pc in (0x800003f8, 0x8000043a, 0x8000052e, 0x80000566):
                    counts[hex(pc)] += 1
            for reg, value in writes.items():
                regs[reg] = value
            regs[0] = 0
    console = bytes(getbytes('replay_log', 8192)).split(b'\0', 1)[0].decode('ascii')
    require(fixture_reads == [[r, f] for r in range(3360, 6720) for f in (0, 8)], 'complete fixture traversal')
    return {'setup': setup, 'helper': helper, 'output_reads': reads,
            'selected_fixture': selected_fixture, 'fixture_fields_checked': len(fixture_reads),
            'initialization_counts': dict(counts), 'console': console, 'terminal': terminal,
            'retired_total': total, 'firmware_retired_including_park': firmware,
            'parking_retired': park, 'capacity_calls': pcs[syms['capacity']],
            'mask_loop_retired': sum(pcs[pc] for pc in
                (0x8000051c, 0x80000520, 0x80000524, 0x80000526, 0x8000052a,
                 0x8000052e, 0x80000532, 0x80000534)),
            'seed_loop_retired': sum(n for pc, n in pcs.items() if
                0x8000041c <= pc <= 0x8000043e or 0x80000082 <= pc <= 0x8000009c)}


def validate(data):
    syms = json.loads((HERE / 'spike/symbols.json').read_text())
    proof = json.loads((HERE / 'sourceproof.json').read_text())
    original = proof['helper_windows']['spike']['op_0']['new']
    setup = data['setup']
    require(setup is not None, 'missing setup')
    require(setup['args'] == [syms['input'], syms['seed'], syms['output'] + 8,
                             8, 16, syms['mask'], 0, 0], 'helper arguments')
    require(setup['input'] == list(bytes.fromhex('007c00fc') * 8), 'full input16')
    require(setup['seed'] == list(bytes.fromhex('007c') * 64), 'full seed64')
    require(setup['mask'] == [0x24] * 64, 'full mask64')
    require(setup['output'] == [0x5b] * 144, 'full old output144')
    require(data['initialization_counts'] == {'0x800003f8': 128, '0x8000043a': 512,
            '0x8000052e': 215040, '0x80000566': 144}, 'original initialization loops')
    require(data['capacity_calls'] == 1 and data['fixture_fields_checked'] == 6720, 'original traversal')
    require(data['mask_loop_retired'] == 1612800 and data['seed_loop_retired'] == 122368,
            'static loop accounting')
    require(data['selected_fixture'] == [
        {'pc': 0x8000050e, 'address': syms['fixtures'] + 4905 * 16, 'value': 0x7e00},
        {'pc': 0x80000510, 'address': syms['fixtures'] + 4905 * 16 + 8, 'value': 16}], 'bank1 row1545')
    helper = data['helper']
    require(len(helper) == 21, '21 helper instructions')
    for i, row in enumerate(helper):
        require(row['index'] == i and row['pc'] == original[i][0] and
                row['insn'] == original[i][1] and row['ordinal'] == setup['ordinal'] + i,
                'helper identity/order')
    vtype = None
    for i, vl, expected_vtype in [(0, 64, 8), (3, 16, 14), (6, 8, 14), (18, 64, 8)]:
        c = helper[i]['csrs']
        vtype = c.get('vtype', vtype)
        require(helper[i]['regs'] == {'5': vl} and c.get('vl') == vl and
                vtype == expected_vtype and c.get('vstart') == 0, 'vset/SEW/LMUL/VL')
    for i, reg, expected, addresses in [
        (1, '16', bytes.fromhex('007c') * 64, range(syms['seed'], syms['seed'] + 128, 2)),
        (2, '24', bytes([0x5b]) * 128, range(syms['output'] + 8, syms['output'] + 136, 2)),
        (4, '8', bytes(setup['input']), range(syms['input'], syms['input'] + 32, 2)),
        (5, '0', b'\x24\x24', range(syms['mask'], syms['mask'] + 2))]:
        actual = bytes.fromhex(helper[i]['vectors'].get(reg, ''))
        require(len(actual) == 128 and actual[:len(expected)] == expected, 'vector setup payload')
        require(helper[i]['memory'] == [[a, None] for a in addresses], 'vector load footprint')
    require(helper[7]['regs'] == {'29': 0} and helper[8]['regs'] == {'30': 0}, 'saved CSR')
    require(helper[9]['csrs'].get('frm') == 0 and helper[10]['csrs'].get('fflags') == 0, 'requested CSR')
    result = b'\x00\x7e' + b'\x5b' * 126
    require(helper[11]['vectors'].get('24') == result.hex() and
            helper[11]['csrs'].get('fflags') == 16 and helper[11]['csrs'].get('vstart') == 0, 'reduction result/NV')
    require(helper[12]['regs'] == {'10': 0} and helper[13]['regs'] == {'6': 16} and
            helper[14]['regs'] == {'6': 16 << 32} and helper[15]['regs'] == {'10': 16 << 32}, 'returned flags/vstart')
    require(helper[16]['csrs'].get('frm') == 0 and helper[17]['csrs'].get('fflags') == 0, 'CSR restoration')
    require(helper[19]['memory'] == [[syms['output'] + 8 + i, int.from_bytes(result[i:i+2], 'little')]
                                   for i in range(0, 128, 2)], 'complete destination store')
    expected_output = b'\x5b' * 8 + result + b'\x5b' * 8
    require(data['output_reads'] == [[i, v] for i, v in enumerate(expected_output)], '144 original LBU oracle')
    console = data['console']
    require(not re.search(r'FAIL|DETAIL|TRAP|MISMATCH', console), 'raw diagnostic veto')
    require(console == 'BOARD_CASE_BEGIN original_e16_mf4\n' + MARKER + '\n' +
            'BOARD_CASE_PASS original_e16_mf4\nBOARD_REPLAY_PASS\n', 'complete original oracle console')
    require(data['terminal'] and data['terminal']['value'] == 1, 'actual HTIF success')
    require(1801190 < data['terminal']['firmware_retired'] < 2070768 and
            data['retired_total'] <= 3000000, 'retired bound')


def main():
    require(not (OUT / 'audit.json').exists(), 'preserve previous audit')
    execution = json.loads((OUT / 'execution.json').read_text())
    approval = json.loads((OUT / 'approval.json').read_text())
    require(execution['approval_sha256'] == sha(OUT / 'approval.json'), 'approval drift')
    require(execution['returncode'] == 0 and execution['error'] is None and
            execution['elapsed_s'] < 120, 'reference execution boundary')
    for path, digest in approval['pins'].items():
        require(sha(path) == digest, 'input drift: ' + path)
    for name, value in execution['raw'].items():
        require(sha(OUT / name) == value['sha256'] and
                (OUT / name).stat().st_size <= 256 * 1024 * 1024, 'raw drift/bound')
    data = extract()
    save(OUT / 'ledger.json', data)
    validate(data)
    # Revalidate one extracted witness with host-only mutations. Never reexecute Spike.
    negatives = {
        'missing_NV': lambda d: d['helper'][13]['regs'].update({'6': 0}),
        'wrong_NaN': lambda d: d['helper'][11]['vectors'].update({'24': '017e' + '5b' * 126}),
        'wrong_vstart': lambda d: d['helper'][12]['regs'].update({'10': 1}),
        'missing_guard': lambda d: d['output_reads'].pop(),
        'tail_corruption': lambda d: d['output_reads'][100].__setitem__(1, 0),
        'wrong_bank': lambda d: d['selected_fixture'][0].update({'value': 0x7c00}),
        'wrong_type': lambda d: d['helper'][3]['csrs'].update({'vtype': 22}),
        'missing_seed_word': lambda d: d['setup']['seed'].pop(),
        'wrong_mask': lambda d: d['setup']['mask'].__setitem__(0, 0),
        'CSR_restore': lambda d: d['helper'][17]['csrs'].update({'fflags': 16}),
        'short_store': lambda d: d['helper'][19]['memory'].pop(),
        'missing_HTIF': lambda d: d.update({'terminal': None}),
        'truncated_oracle': lambda d: d['output_reads'].pop(70),
        'wrong_encoding': lambda d: d['helper'][11].update({'insn': '04881c57'}),
    }
    results = []
    for name, mutate in negatives.items():
        changed = copy.deepcopy(data)
        mutate(changed)
        try:
            validate(changed)
        except ValueError as error:
            results.append({'negative': name, 'rejected': str(error)})
        else:
            raise ValueError('negative falsely accepted: ' + name)
    save(OUT / 'checker_host.json', {'status': 'PASS_15', 'positive': True, 'negatives': results})
    (OUT / 'runtime.log').write_text(data['console'])
    save(OUT / 'audit.json', {'status': 'PASS_ORIGINAL_SINGLE_REFERENCE_ONLY_PENDING_INDEPENDENT_REVIEW',
        'target_calls': 1, 'original_byte_oracle_checks': 144,
        'fixture_bank': 1, 'fixture_row': 1545, 'NV': 16, 'vstart': 0, 'result': '0x7e00',
        'firmware_retired_to_HTIF': data['terminal']['firmware_retired'],
        'total_commits': data['retired_total'], 'parking_retired': data['parking_retired'],
        'target_ordinal': data['helper'][11]['ordinal'], 'target_PC': hex(data['helper'][11]['pc']),
        'elapsed_s': execution['elapsed_s'], 'pins_unchanged': True,
        'checker_sha256': sha(HERE / 'check_reference.py'),
        'evidence': {str(p): sha(p) for p in [OUT / n for n in
                     ('ledger.json', 'checker_host.json', 'runtime.log', 'commits.log',
                      'approval.json', 'execution.json')]},
        'VCS_run': False, 'Linux_run': False, 'full6720_accepted': False})


if __name__ == '__main__':
    main()
