#!/usr/bin/env python3
"""Strict QK raw-bit/CSR/retirement/VRF/probe checks; protocol is independent."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import cases
import elf
from generate import need, sha, verify

FIELDS = ('id phase d heads tokens base rm before_fcsr before_vstart after_fcsr after_vstart traps cause pc mtval '
          'trap_fcsr trap_vstart unexpected guard_errors before_mstatus trap_mstatus after_mstatus before_vl '
          'before_vtype after_vl after_vtype trap_csrs_valid').split()
HEX = 'pc mtval before_mstatus trap_mstatus after_mstatus before_vtype after_vtype'.split()
READS = ('before_vl', 'before_vtype', 'before_fcsr', 'before_vstart', 'before_mstatus',
         'after_mstatus', 'after_vl', 'after_vtype', 'after_fcsr', 'after_vstart')
CSRS = dict(before_vl=0xc20, before_vtype=0xc21, before_fcsr=3, before_vstart=8,
            before_mstatus=0x300, after_mstatus=0x300, after_vl=0xc20, after_vtype=0xc21,
            after_fcsr=3, after_vstart=8)
TRAP = (('cause', 0x1c, 0x342, 6), ('pc', 0x24, 0x341, 7),
        ('trap_mstatus', 0x2c, 0x300, 28), ('mtval', 0x4c, 0x343, 28),
        ('trap_fcsr', 0x54, 3, 28), ('trap_vstart', 0x5c, 8, 28))


def fields(text, names, hex_fields=(), strings=(), binary=()):
    result = {}
    for item in text.split():
        need(item.count('=') == 1, 'Malformed key/value')
        k, v = item.split('=')
        need(k in names and k not in result, 'Extra/duplicate field')
        pattern = r'[a-zA-Z0-9_]+' if k in strings else r'[0-9a-fA-F]{16}' if k in hex_fields else r'[01]+' if k in binary else r'[0-9]+'
        need(re.fullmatch(pattern, v), 'Malformed value: ' + k)
        result[k] = v if k in strings else int(v, 16 if k in hex_fields else 2 if k in binary else 10)
    need(set(result) == set(names), 'Missing fields')
    return result


def bits(text, width, count):
    need(re.fullmatch('[0-9a-fA-F]{' + str(width * count) + '}', text), 'Bad raw-bit width')
    return [int(text[i:i + width], 16) for i in range(0, len(text), width)]


def csv_rows(path):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        need(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames), 'Duplicate CSV columns')
        for row in reader:
            need(None not in row and all(v is not None for v in row.values()), 'Malformed CSV')
            yield row


def checked_build(build):
    build = Path(build).resolve(strict=True)
    m = json.loads((build / 'build.json').read_text())
    need(m['state'] == 'QK_BOUNDARY_SOFTWARE_BUILT_NOT_EXECUTED' and m['post_pins_match'] and
         not m['eda_started'] and m['source_pins_sha256'] == sha(build / 'source-pins.json'), 'Software receipt mismatch')
    need(Path(m['elf']) == build / 'resident_qk_boundary.elf' and sha(m['elf']) == m['elf_sha256'], 'ELF identity')
    verify(json.loads((build / 'source-pins.json').read_text()))
    verify(m['artifacts'])
    actual = {str(p): sha(p) for p in build.rglob('*') if p.is_file() and p != build / 'build.json'}
    need(actual == m['artifacts'], 'Software artifact inventory mismatch')
    v = json.loads((build / 'vectors/vectors.json').read_text())
    need(v['schema'] == cases.SCHEMA and len(v['cases']) == 23, 'Vector schema')
    c = elf.contract(Path(m['elf']).read_bytes())
    for name, word in cases.WORDS.items():
        need(c['words'][elf.pc(c, name)] == word, 'ELF opcode mismatch')
    for field in READS:
        need(c['words'][elf.pc(c, 'qk_read_' + field)] == CSRS[field] << 20 | 6 << 7 | 0x2073,
             'ELF CSR PC mismatch')
    trap = elf.pc(c, 'boundary_trap')
    need(c['words'][trap + 0xb8] == 0x30200073, 'Frozen trap handler changed')
    for _, offset, csr, rd in TRAP:
        need(c['words'][trap + offset] == csr << 20 | rd << 7 | 0x2073, 'Trap CSR ELF mismatch')
    need(c['words'][elf.pc(c, 'qk_helper_fcsr_pc')] == 0x00302573, 'Parent helper CSR binding')
    return m, v, c


def numerical(text, vectors, c):
    tagged = [line for line in text.splitlines() if line.startswith('QK_BOUNDARY_')]
    need(not any('QK_BOUNDARY_' in line and not line.startswith('QK_BOUNDARY_') for line in text.splitlines()),
         'Malformed boundary prefix')
    begin = 'QK_BOUNDARY_BEGIN cases=23 vlenb=128 data=' + vectors['data_identity_sha256']
    need(tagged and tagged[0] == begin and tagged.count(begin) == 1, 'Missing/duplicate BEGIN/identity')
    records = [fields(line[len('QK_BOUNDARY_CASE '):], FIELDS, HEX)
               for line in tagged if line.startswith('QK_BOUNDARY_CASE ')]
    data = [fields(line[len('QK_BOUNDARY_DATA '):], ('id', 'phase', 'kind', 'bits'), strings=('kind', 'bits'))
            for line in tagged if line.startswith('QK_BOUNDARY_DATA ')]
    specs = cases.attempts(vectors['cases'])
    need(len(specs) == len(records) == len(data) == 35, 'Attempt/data count')
    for s, r, d in zip(specs, records, data):
        want = dict(id=s['id'], phase=s['phase'], d=s['dimension'], heads=s['heads'], tokens=s['tokens'],
                    base=s['query_base'], rm=s['rm'], traps=s['error'], unexpected=0, guard_errors=0)
        need(all(r[k] == v for k, v in want.items()), 'Attempt attribution/guards')
        rm = 5 if s['error'] and s['kind'] == 'frm' else s['rm']
        start = int(s['error'] and s['kind'] == 'vstart')
        before = rm << 5 | s['initial_flags']
        need(r['before_fcsr'] == before and r['before_vstart'] == start and
             r['after_fcsr'] == (before if s['error'] else s['expected_fcsr']) and
             r['after_vstart'] == start, 'Command-local flags/rounding/vstart')
        need(r['before_vl'] == r['after_vl'] and r['before_vtype'] == r['after_vtype'], 'VL/VTYPE changed')
        need((d['id'], d['phase']) == (s['id'], s['phase']), 'Misattributed DATA')
        if s['error']:
            fault = next(elf.pc(c, name) for name, word in cases.WORDS.items() if word == s['instruction'])
            need(r['cause'] == 2 and r['pc'] == fault, 'Not exact illegal PC/cause')
            off = s['kind'] in ('fs_off', 'vs_off')
            need(r['trap_csrs_valid'] == int(not off), 'Unavailable/missing trap CSR read')
            if off:
                mask = 0x6000 if s['kind'] == 'fs_off' else 0x600
                need(not (r['before_mstatus'] | r['trap_mstatus'] | r['after_mstatus']) & mask and
                     r['trap_fcsr'] == r['trap_vstart'] == r['mtval'] == 0, 'Off-state mutation/CSR access')
            else:
                need(r['trap_fcsr'] == before and r['trap_vstart'] == start, 'Fault changed flags/vstart')
            need(d['kind'] == 'dest32' and bits(d['bits'], 8, 384) == vectors['destination_pattern'],
                 'Rejected destination/adjacent registers changed')
        else:
            need(all(r[k] == 0 for k in ('traps', 'cause', 'pc', 'mtval', 'trap_fcsr', 'trap_vstart', 'trap_csrs_valid')),
                 'Successful command trapped')
            if s['mode'] in (1, 2):
                need(r['after_vl'] == 0 and r['after_vtype'] == (0xc0 if s['mode'] == 1 else 1 << 63), 'VL0/vill not established')
            need(d['kind'] == 'result' and bits(d['bits'], 8, len(s['expected'])) == s['expected'], 'QK raw result mismatch')
    for prefix, expected_count in (('QK_BOUNDARY_PV ', 2), ('QK_BOUNDARY_HELPER ', 1)):
        selected = [line[len(prefix):] for line in tagged if line.startswith(prefix)]
        need(len(selected) == expected_count, 'Missing/extra coexistence/helper')
        for i, line in enumerate(selected):
            keys = ('id', 'fcsr', 'bits') if expected_count == 2 else ('id', 'fcsr', 'guard_errors', 'bits')
            r = fields(line, keys, strings=('bits',))
            expected = [0x3e00] * 64 if expected_count == 2 else vectors['cases'][0]['expected']
            flags = 0 if expected_count == 2 else vectors['cases'][0]['qk_flags']
            need(r['id'] == i and r['fcsr'] == flags and not r.get('guard_errors', 0) and
                 bits(r['bits'], 4 if expected_count == 2 else 8, len(expected)) == expected, 'PV/helper oracle mismatch')
    done = 'QK_BOUNDARY_DONE cases=23 successes=24 rejected=12 helper=1 pv=2 compat=1 errors=0'
    need(tagged[-1] == done and tagged.count(done) == 1 and len(tagged) == 75, 'Unknown/duplicate/missing terminal record')
    compat = [line[len('PV_BOUNDARY_COMPAT '):] for line in text.splitlines() if line.startswith('PV_BOUNDARY_COMPAT ')]
    need(len(compat) == 1, 'Missing/extra QBS/RVV postlude')
    r = fields(compat[0], ('qbs_fcsr', 'rvv_fcsr', 'qbs', 'rvv'), strings=('qbs', 'rvv'))
    need(r['qbs_fcsr'] == r['rvv_fcsr'] == 0 and
         bits(r['qbs'], 8, 32) == [0x43800000, 0x44000000, 0x44400000] + [0] * 29 and
         bits(r['rvv'], 8, 32) == [0x10203041 + 3 * i for i in range(32)], 'QBS/RVV raw data or flags')
    return specs, records


def qk(word):
    return word & 0x707f == 0x705b and word >> 25 == 3


def sample(rows, pc, expected, c, rd=6):
    selected = [r for r in rows if int(r['pc'], 16) == pc]
    need(len(selected) == 1, 'Missing/extra exact-PC sample')
    r = selected[0]
    need(int(r['insn'], 16) == c['words'][pc] and int(r['rd']) == rd and int(r['trap']) == 0 and
         int(r['rd_wdata'], 16) == expected, 'CSR/counter retire PC/insn/rd/value')


def architecture(path, specs, records, c):
    windows, pv_windows, pv_pending, flow, rows, offered, active = [], [], [], [], [], [], None
    previous, last_order, direct, helper, trap_count, helper_csr = -1, -1, 0, 0, 0, 0
    issue, ret = elf.pc(c, 'qk_issue'), elf.pc(c, 'qk_issue_return')
    hlo, hhi = elf.extent(c, 'akv_experimental_resident_qk')
    trap, thi = elf.extent(c, 'boundary_trap')
    consumed = set()
    for r in csv_rows(path):
        cycle, word, pc = int(r['cycle']), int(r['insn'], 16), int(r['pc'], 16)
        need(cycle >= previous, 'Nonmonotone CPU trace')
        previous = cycle
        if r['event'] == 'arch_start' and word == cases.PV:
            need(not pv_pending, 'Overlapping PV ownership')
            pv_pending.append(dict(arch_seq=int(r['order']), begin=cycle))
        if r['event'] == 'arch_start' and qk(word):
            need(active is not None, 'Unowned QK request')
            offered.append(r)
        if r['event'] != 'retire':
            continue
        need(int(r['order']) > last_order and int(r['trap']) == 0, 'Out-of-order/invalid retirement')
        last_order = int(r['order'])
        if pc == elf.pc(c, 'qk_helper_fcsr_pc'):
            need(helper == 1 and word == 0x00302573 and int(r['rd']) == 10 and
                 int(r['rd_wdata'], 16) == specs[0]['qk_flags'], 'Actual parent-helper FCSR mismatch')
            helper_csr += 1
        if word in (cases.FILL, cases.RELEASE, cases.PV, cases.QBS, cases.VADD):
            flow.append(word)
        if word == cases.PV:
            need(pv_pending and pc == elf.pc(c, 'qk_pv_pc'), 'Unowned/wrong-PC PV retirement')
            pv_windows.append(dict(pv_pending.pop(), end=cycle))
        if pc in (issue, hlo):
            need(active is None, 'Nested QK calls')
            active = 'helper' if pc == hlo else 'direct'
            rows, offered = [], []
        if active is None:
            need(not qk(word) and not trap <= pc < thi, 'Unowned QK retire/handler')
            continue
        allowed = hlo <= pc < hhi if active == 'helper' else issue <= pc <= ret or trap <= pc < thi
        need(allowed and word == c['words'].get(pc), 'CPU flow differs from exact ELF')
        rows.append(r)
        end = pc == hhi - 4 if active == 'helper' else pc == ret
        if not end:
            continue
        s = dict(specs[0], id=-1, instruction=cases.QK, mode=0) if active == 'helper' else specs[direct]
        record = None if active == 'helper' else records[direct]
        off = s['error'] and s['kind'] in ('fs_off', 'vs_off')
        need(len(offered) == (0 if off else 1), 'Wrong QK request count, including FS/VS-off')
        seq = int(offered[0]['order']) if offered else None
        if offered:
            need(int(offered[0]['insn'], 16) == s['instruction'] and seq >= 0 and seq not in consumed,
                 'Request identity mismatch/reuse')
            consumed.add(seq)
        retired = [r for r in rows if qk(int(r['insn'], 16))]
        handler = [r for r in rows if trap <= int(r['pc'], 16) < thi]
        if record is not None:
            for field in READS:
                sample(rows, elf.pc(c, 'qk_read_' + field), record[field], c)
            sample(rows, elf.pc(c, 'qk_read_traps'), s['error'], c, 10)
        if s['error']:
            need(not retired, 'Illegal QK must not be fabricated as RVFI retirement')
            path_pcs = list(range(trap, trap + 0xbc, 4))
            if off:
                first = 0x40 if s['kind'] == 'fs_off' else 0x4c
                path_pcs = [p for p in path_pcs if not trap + first <= p < trap + 0x6c]
            need([int(r['pc'], 16) for r in handler] == path_pcs, 'Incorrect trap/recovery path')
            for field, offset, _, rd in TRAP[:3] if off else TRAP:
                sample(handler, trap + offset, record[field], c, rd)
            fault = record['pc']
            for offset, rd, value in ((0x6c, 6, 2), (0x78, 28, fault), (0x80, 28, 1),
                                      (0x8c, 28, 0), (0x9c, 6, elf.pc(c, 'qk_resume'))):
                sample(handler, trap + offset, value, c, rd)
            trap_count += 1
        else:
            need(not handler and len(retired) == 1 and int(retired[0]['insn'], 16) == s['instruction'],
                 'Missing/extra successful QK retire')
            if active == 'direct':
                expected_pc = next(elf.pc(c, n) for n, w in cases.WORDS.items() if w == s['instruction'])
                need(int(retired[0]['pc'], 16) == expected_pc, 'Wrong successful exact PC')
        flow.append(s['instruction'])  # Logical trap token, never a manufactured retire row.
        windows.append(dict(spec=s, arch_seq=seq, begin=int(rows[0]['cycle']), end=cycle,
                            offer_cycle=int(offered[0]['cycle']) if offered else None))
        if active == 'helper':
            helper += 1
        else:
            direct += 1
        active = None
    expected_flow = []
    for row in cases.scenarios():
        expected_flow.append(cases.FILL)
        if row['id'] == 0:
            expected_flow.append(cases.PV)
        if row['rejection']:
            if row['kind'] == 'no_context':
                expected_flow.append(cases.RELEASE)
            expected_flow.append(row['bad_instruction'])
            if row['kind'] == 'no_context':
                expected_flow.append(cases.FILL)
        expected_flow.append(row['instruction'] if not row['rejection'] else cases.QK)
        if row['id'] == 0:
            expected_flow += [cases.QK, cases.PV]
        expected_flow.append(cases.RELEASE)
    expected_flow += [cases.QBS, cases.VADD]
    need(active is None and not pv_pending and len(pv_windows) == 2 and
         direct == 35 and helper == 1 and helper_csr == 1 and trap_count == 12 and len(consumed) == 34,
         'Incomplete CPU success/trap/request closure')
    need(flow == expected_flow, 'Context reload/lifetime or coexistence flow changed')
    return dict(qk=windows, pv=pv_windows)


def audit_uop(rows, vd, vl, eew, expected, source=4):
    need(rows and rows[0]['event'] == 'alloc' and rows[-1]['event'] == 'done' and
         sum(r['event'] == 'alloc' for r in rows) == sum(r['event'] == 'done' for r in rows) == 1,
         'Unclosed/extra backend allocation')
    seen = set()
    for i, r in enumerate(rows):
        need((r['arch_seq'], r['vid']) == (rows[0]['arch_seq'], rows[0]['vid']) and
             tuple(int(r[k]) for k in ('use_vd', 'vd', 'vl', 'eew', 'vstart')) == (1, vd, vl, eew, 0),
             'Backend allocation geometry/identity')
        if i in (0, len(rows) - 1):
            continue
        key = int(r['lane']), int(r['addr'])
        need(r['event'] == 'write' and int(r['source']) == source and key in expected and key not in seen,
             'Unowned/duplicate VRF write')
        value, mask = expected[key]
        need(int(r['be'], 16) == mask and re.fullmatch('[0-9a-fA-F]{16}', r['wdata']), 'Wrong actual byte enable/data')
        bitmask = sum(255 << (8 * b) for b in range(8) if mask >> b & 1)
        need(int(r['wdata'], 16) & bitmask == value & bitmask, 'Wrong active result raw bits')
        seen.add(key)
    need(seen == set(expected), 'Missing result writes')
    return int(rows[0]['vid'])


def work(vector, text, trace):
    windows = trace['qk']
    groups, pv_groups, qbs_rows, vadd_rows = defaultdict(list), defaultdict(list), [], []
    epoch, previous = 0, -1
    for r in csv_rows(vector):
        cycle, word = int(r['cycle']), int(r['insn'], 16)
        need(cycle >= previous and (r['nr_lanes'], r['vlen_bits']) == ('4', '1024'), 'Vector epoch/configuration')
        previous = cycle
        if r['event'] == 'config':
            need(epoch == 0 and cycle == 0, 'Reset/extra epoch')
            epoch += 1
            continue
        need(epoch == 1 and r['event'] in ('alloc', 'write', 'done'), 'Unknown vector event')
        if qk(word): groups[int(r['arch_seq'])].append(r)
        elif word == cases.PV: pv_groups[int(r['arch_seq'])].append(r)
        elif word == cases.QBS: qbs_rows.append(r)
        elif word == cases.VADD: vadd_rows.append(r)
    need(epoch == 1, 'Missing vector configuration')
    perf_fields = ('seq vid tokens dimensions heads query_base active cycles error flags source_words seed_words '
                   'coefficients value_words result_words final_acks query_reads columns').split()
    probes = [fields(line[len('[RESIDENT_QK_PERF]'):], perf_fields, binary=('active',))
              for line in text.splitlines() if line.startswith('[RESIDENT_QK_PERF]')]
    need(all(a['seq'] < b['seq'] for a, b in zip(probes, probes[1:])), 'Duplicate/out-of-order QK probes')
    consumed, pi = set(), 0
    for window in windows:
        s, seq = window['spec'], window['arch_seq']
        rows = groups.get(seq, [])
        if s['error'] and s['rejection'] == 'frontend':
            need(not rows, 'Frontend illegal allocated or wrote')
            continue
        need(rows and window['offer_cycle'] <= int(rows[0]['cycle']) <= int(rows[-1]['cycle']) <= window['end'],
             'QK work outside CPU owner window')
        vd = 28 if s['instruction'] == cases.WORDS['qk_rd28_pc'] else 0
        vid = audit_uop(rows, vd, 128, 2, {} if s['error'] else cases.writes(s))
        need(pi < len(probes), 'Missing QK terminal probe')
        p = probes[pi]; pi += 1
        want = cases.geometry(s)
        want.update(vid=vid, dimensions=s['dimension'], tokens=s['tokens'], heads=s['heads'],
                    query_base=s['query_base'], error=s['error'], flags=0 if s['error'] else s['qk_flags'])
        if s['error']:
            for k in ('seed_words', 'coefficients', 'value_words', 'result_words', 'final_acks', 'query_reads', 'columns'):
                want[k] = 0
        need(all(p[k] == value for k, value in want.items()) and p['cycles'] > 0, 'QK actual service work/flags')
        consumed.add(seq)
    need(pi == len(probes) == 28 and set(groups) == consumed and len(pv_groups) == 2, 'Unowned/extra/missing QK/PV work')
    pv_names = ('seq vid control tokens words heads cycles error flags source_words seed_words '
                'coefficients value_words result_words final_acks row_reads').split()
    pv_probes = [fields(line[len('[RESIDENT_PV_PERF]'):], pv_names)
                 for line in text.splitlines() if line.startswith('[RESIDENT_PV_PERF]')]
    need(len(pv_probes) == 2 and set(pv_groups) == {w['arch_seq'] for w in trace['pv']}, 'PV source ownership/probes')
    for window, p in zip(trace['pv'], pv_probes):
        rows = pv_groups[window['arch_seq']]
        need(window['begin'] <= int(rows[0]['cycle']) <= int(rows[-1]['cycle']) <= window['end'], 'PV outside CPU ownership')
        data = {(lane, w): (0x3e003e003e003e00, 255) for lane in range(4) for w in range(4)}
        vid = audit_uop(rows, 0, 256, 1, data)
        want = dict(vid=vid, control=0, tokens=1, words=4, heads=1, error=0, flags=0, source_words=96,
                    seed_words=16, coefficients=4, value_words=16, result_words=16, final_acks=16, row_reads=4)
        need(all(p[k] == v for k, v in want.items()) and p['cycles'] > 0, 'PV source/drain/flags mismatch')
    need(qbs_rows and int(qbs_rows[0]['cycle']) > max(int(rs[-1]['cycle']) for rs in (*groups.values(), *pv_groups.values()))
         and vadd_rows and int(vadd_rows[0]['cycle']) > int(qbs_rows[-1]['cycle']), 'Coexistence ordering')
    data = [0x43800000, 0x44000000, 0x44400000] + [0] * 29
    audit_uop(qbs_rows, 8, 32, 2, {(l, 32 + w): (data[8 * w + l] | data[8 * w + l + 4] << 32, 255)
                                for l in range(4) for w in range(4)})
    audit_uop(vadd_rows, 16, 32, 2, {(l, 64 + w): ((0x10203041 + 3 * (8 * w + l)) |
               (0x10203041 + 3 * (8 * w + l + 4)) << 32, 255) for l in range(4) for w in range(4)}, source=0)
    return dict(admitted_qk=28, successful_qk=24, rejected_qk=12, source_words=0,
                frontend_rejected=8, backend_rejected=4, pv=2, qbs=1, rvv=1,
                allocation_and_actual_masked_data_checked=True, numerical_checked=True,
                convention='Illegal CVA6 instructions do not retire; 12 real CSR handler groups required')


def check(build, log, vector, commit):
    _, v, c = checked_build(build)
    inputs = [Path(build) / 'build.json', Path(build) / 'source-pins.json', Path(log), Path(vector), Path(commit), Path(__file__)]
    pins = {str(p.resolve()): sha(p) for p in inputs}
    text = Path(log).read_text()
    specs, records = numerical(text, v, c)
    windows = architecture(commit, specs, records, c)
    result = work(vector, text, windows)
    verify(pins)
    return dict(schema=cases.SCHEMA, numerical_checked=True, architecture_checked=True,
                work=result, protocol_checked=False, evidence_sha256=pins)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('build', 'log', 'vector', 'commit'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(check(a.build, a.log, a.vector, a.commit), sort_keys=True))
