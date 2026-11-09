#!/usr/bin/env python3
"""Strict boundary numerical/work audit; independent protocol audit still required."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from cases import (PV_INSN, QBS_INSN, VADD_INSN, FILL_INSN, RELEASE_INSN,
                   SCHEMA, attempts, instruction_flow, native_indices)
from generate import require, verify

CASE_FIELDS = ('id phase d heads tokens rm prep_fcsr before_fcsr before_vstart after_fcsr '
               'after_vstart traps cause pc mtval trap_fcsr trap_vstart unexpected guard_errors '
               'before_mstatus trap_mstatus after_mstatus before_vl before_vtype after_vl after_vtype trap_csrs_valid').split()
CASE_HEX = ('pc', 'mtval', 'before_mstatus', 'trap_mstatus', 'after_mstatus', 'before_vtype', 'after_vtype')
PERF_FIELDS = ('seq vid control tokens words heads cycles error flags source_words seed_words '
               'coefficients value_words result_words final_acks row_reads').split()
LANE_FIELDS = 'lane vid tokens elements heads issued returned writes flags error'.split()


def fields(payload, names, hex_fields=(), strings=()):
    result = {}
    for word in payload.split():
        require(word.count('=') == 1, 'Malformed record field')
        key, value = word.split('=')
        require(key in names and key not in result, 'Unknown/duplicate record field')
        if key in strings:
            require(re.fullmatch('[a-zA-Z0-9_]+', value) is not None, 'Malformed string field')
            result[key] = value
        else:
            require(re.fullmatch('[0-9a-fA-F]{16}' if key in hex_fields else '[0-9]+', value)
                    is not None, 'Malformed numeric field')
            result[key] = int(value, 16 if key in hex_fields else 10)
    require(set(result) == set(names), 'Missing/extra record fields')
    return result


def unpack(bits, width, count):
    require(re.fullmatch('[0-9a-fA-F]{'+str(width*count)+'}', bits) is not None,
            'Wrong bit-data width or unknown value')
    return [int(bits[i:i+width], 16) for i in range(0, len(bits), width)]


def check_log(text, vectors, fault_pc):
    records = []
    for line in text.splitlines():
        if 'PV_BOUNDARY_' not in line:
            continue
        require(line.startswith('PV_BOUNDARY_') and ' ' in line, 'Malformed boundary record')
        tag, data = line[len('PV_BOUNDARY_'):].split(' ', 1)
        require(tag in ('BEGIN', 'CASE', 'DATA', 'COMPAT', 'DONE'), 'Unknown/failure boundary record')
        records.append((tag, data))
    require(records and records[0][0] == 'BEGIN', 'Missing boundary BEGIN')
    begin = fields(records[0][1], ('cases', 'vlenb', 'data'), strings=('data',))
    require(begin == dict(cases=21, vlenb=128, data=vectors['data_identity_sha256']), 'Boundary identity drift')
    position = 1
    for s in attempts(vectors['cases']):
        require(position+1 < len(records) and [r[0] for r in records[position:position+2]] == ['CASE', 'DATA'],
                'Missing/duplicate/out-of-order boundary attempt')
        r = fields(records[position][1], CASE_FIELDS, hex_fields=CASE_HEX)
        want = dict(id=s['id'], phase=s['phase'], d=s['dimension'], heads=s['heads'],
                    tokens=s['tokens'], rm=s['rm'], traps=s['error'], unexpected=0, guard_errors=0)
        require(all(r[k] == v for k, v in want.items()), 'Boundary shape/trap/guard mismatch')
        prep = (s['rm'] << 5) | s['initial_flags'] | s['prepared_flags']
        bad_rm = 5 if s['error'] and s['kind'] == 'frm' else s['rm']
        bad_start = int(s['error'] and s['kind'] == 'vstart')
        before = (bad_rm << 5) | (prep & 31)
        require(r['prep_fcsr'] == prep and r['before_fcsr'] == before and r['before_vstart'] == bad_start,
                'Preparation/issue CSR mismatch')
        require(r['after_fcsr'] == (before if s['error'] else s['expected_fcsr']) and
                r['after_vstart'] == bad_start, 'PV accrued flags or raw vstart mismatch')
        if s['error']:
            pc = fault_pc[str(s['instruction'])] if isinstance(fault_pc, dict) else fault_pc
            require(r['cause'] == 2 and r['pc'] == pc, 'Trap is not exact armed PC/cause')
            status_off = s['kind'] in ('fs_off', 'vs_off')
            require(r['trap_csrs_valid'] == int(not status_off), 'Unsafe/missing trap CSR capture')
            if status_off:
                mask = 0x6000 if s['kind'] == 'fs_off' else 0x600
                require(not (r['before_mstatus'] | r['trap_mstatus'] | r['after_mstatus']) & mask and
                        r['trap_fcsr'] == r['trap_vstart'] == r['mtval'] == 0, 'Off-state trap read unavailable CSRs')
            else:
                require(r['trap_fcsr'] == before and r['trap_vstart'] == bad_start, 'Raw fault CSR changed before capture')
            # mtval is recorded but may legitimately be zero for backend illegal.
        else:
            require(all(r[k] == 0 for k in ('cause', 'pc', 'mtval', 'trap_fcsr', 'trap_vstart')),
                    'Unexpected successful-command trap state')
            require(r['before_vl'] == r['after_vl'] and r['before_vtype'] == r['after_vtype'],
                    'PV modified architectural VL/VTYPE')
            if s['vtype_mode']:
                require(r['after_vl'] == 0 and r['after_vtype'] == (0xc0 if s['vtype_mode'] == 1 else 1 << 63),
                        'VL0/vill test was not actually established')
        data = fields(records[position+1][1], ('id', 'phase', 'kind', 'bits'), strings=('kind', 'bits'))
        require((data['id'], data['phase']) == (s['id'], s['phase']), 'Misattributed boundary DATA')
        if s['error']:
            require(data['kind'] == 'dest32' and unpack(data['bits'], 8, 128) == vectors['destination_pattern'],
                    'Failure modified destination value/old EW32 interpretation')
        else:
            require(data['kind'] == 'result' and
                    unpack(data['bits'], 4, s['dimension']*s['heads']) == s['expected'], 'PV output mismatch')
        position += 2
        if s['kind'] == 'mixed':
            for kind, width, expected in (('source', 4, s['source']), ('guard64', 16, vectors['guard_pattern'])):
                require(position < len(records) and records[position][0] == 'DATA', 'Missing mixed-source capture')
                data = fields(records[position][1], ('id', 'phase', 'kind', 'bits'), strings=('kind', 'bits'))
                require((data['id'], data['phase'], data['kind']) == (s['id'], 1, kind) and
                        unpack(data['bits'], width, len(expected)) == expected, 'Mixed source/guard changed')
                position += 1
    require([r[0] for r in records[position:]] == ['COMPAT', 'DONE'], 'Incomplete/extra boundary terminal')
    compat = fields(records[position][1], ('qbs_fcsr', 'rvv_fcsr', 'qbs', 'rvv'), strings=('qbs', 'rvv'))
    require(compat['qbs_fcsr'] == compat['rvv_fcsr'] == 0 and
            unpack(compat['qbs'], 8, 32) == [0x43800000, 0x44000000, 0x44400000]+[0]*29 and
            unpack(compat['rvv'], 8, 32) == [0x10203041+3*i for i in range(32)], 'QBS/RVV postlude mismatch')
    require(fields(records[-1][1], ('cases', 'successes', 'rejected', 'compat', 'errors')) ==
            dict(cases=21, successes=21, rejected=12, compat=1, errors=0), 'Boundary terminal failure')
    return dict(scenarios=21, successful_pv=21, rejected_pv=12, compat_postludes=1,
                numerical_checked=True, phases_checked=True)


def check_probes(text, specs):
    admitted = [s for s in specs if not s['error'] or s['rejection'] == 'backend']
    lane, records = {}, []
    for line in text.splitlines():
        if line.startswith('[RESIDENT_PV_LANE]'):
            r = fields(line[len('[RESIDENT_PV_LANE]'):], LANE_FIELDS)
            require(r['lane'] in range(4) and r['lane'] not in lane, 'Duplicate/out-of-range lane')
            lane[r['lane']] = r
        elif line.startswith('[RESIDENT_PV_PERF]'):
            r = fields(line[len('[RESIDENT_PV_PERF]'):], PERF_FIELDS)
            i = len(records)
            require(i < len(admitted), 'Extra resident terminal')
            s = admitted[i]
            words, writes = s['dimension']//16, s['dimension']//4*s['heads']
            expected = dict(seq=i+1, control=s['control'], tokens=s['tokens'], words=words,
                            heads=s['heads'], error=s['error'], source_words=96,
                            flags=0 if s['error'] else s['pv_flags'])
            require(all(r[k] == v for k, v in expected.items()) and
                    r['vid'] in range(8) and r['cycles'] > 0, 'Resident terminal shape/status mismatch')
            want = dict(seed_words=writes, coefficients=4*s['tokens'],
                        value_words=4*s['tokens']*words, result_words=writes,
                        final_acks=writes, row_reads=s['tokens']*words)
            if s['error']:
                want = dict.fromkeys(want, 0)
                require(not lane, 'Rejected backend command launched lane arithmetic')
            else:
                require(set(lane) == set(range(4)), 'Missing accepted four-lane completion')
                for l, record in lane.items():
                    w = dict(lane=l, vid=r['vid'], tokens=s['tokens'], elements=s['dimension']//4,
                             heads=s['heads'], issued=words*s['heads']*s['tokens'],
                             returned=words*s['heads']*s['tokens'], writes=writes//4,
                             flags=s['lane_flags'][l], error=0)
                    require(record == w, 'Lane accepted/returned/write/flags mismatch')
            require(all(r[k] == v for k, v in want.items()), 'Resident payload/result/final counts mismatch')
            records.append(r)
            lane = {}
        elif '[RESIDENT_PV_' in line:
            raise ValueError('Unknown/malformed resident probe')
    require(len(records) == len(admitted) == 24 and not lane, 'Incomplete/extra resident probes')
    return records


def csv_rows(path):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)), 'Ambiguous CSV header')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'Malformed CSV row')
            yield row


def word16(values, lane, word):
    return sum(values[idx] << (16*part) for part, idx in enumerate(native_indices(lane, word)))


def audit_uop(rows, vd, vl, eew, data, source=4, writes=True):
    require(rows and rows[0]['event'] == 'alloc' and rows[-1]['event'] == 'done', 'Unclosed backend uop')
    first = rows[0]
    seen = set()
    for i, row in enumerate(rows):
        require(row['arch_seq'] == first['arch_seq'] and row['vid'] == first['vid'] and
                tuple(int(row[k]) for k in ('use_vd', 'vd', 'vl', 'eew', 'vstart')) ==
                (1, vd, vl, eew, 0), 'Backend uop identity/geometry drift')
        if i in (0, len(rows)-1):
            continue
        require(row['event'] == 'write' and int(row['source']) == source and int(row['be'], 16) == 255,
                'Wrong actual VRF writer/grant/byte enable')
        key = (int(row['lane']), int(row['addr']))
        require(key in data and key not in seen and
                re.fullmatch('[0-9a-fA-F]{16}', row['wdata']) is not None and
                int(row['wdata'], 16) == data[key], 'Wrong/duplicate/out-of-range architectural VRF write')
        seen.add(key)
    require(seen == (set(data) if writes else set()), 'Incomplete or forbidden architectural writes')
    return int(first['vid'])


def split_uops(rows):
    result, live = [], None
    for row in rows:
        if row['event'] == 'alloc':
            require(live is None, 'Overlapping PV maintenance/final allocation')
            live = [row]
        else:
            require(live is not None, 'Unowned/late PV write/done')
            live.append(row)
            if row['event'] == 'done':
                result.append(live)
                live = None
    require(live is None, 'Unfinished backend uop')
    return result


def check_work(vector_path, commit_path, text, vectors):
    specs = attempts(vectors['cases'])
    probes = check_probes(text, specs)
    def pv(insn):
        return insn & 0x707f == 0x705b and insn >> 25 == 2
    cpu, flow = [], []
    for r in csv_rows(commit_path):
        insn = int(r['insn'], 16)
        if pv(insn):
            cpu.append(r)
        context_command = insn & 0x7f == 0x5b and (insn >> 12) & 7 in (5, 6)
        if r['event'] == 'retire' and (pv(insn) or context_command or insn in (QBS_INSN, VADD_INSN)):
            flow.append(insn)
            if not pv(insn):
                require(int(r['trap']) == 0, 'Context/postlude instruction trapped')
    require(flow == instruction_flow(vectors['cases']),
            'Context lifetime/recovery drift: forbidden RELEASE/FILL/REFILL or wrong instruction order')
    retired = [r for r in cpu if r['event'] == 'retire']
    offered = [r for r in cpu if r['event'] == 'arch_start']
    require(len(retired) == len(specs) == 33, 'Missing/extra retired PV attempts')
    arch, consumed, previous_retire = [], set(), -1
    for s, retire in zip(specs, retired):
        cycle = int(retire['cycle'])
        require(int(retire['insn'], 16) == s['instruction'] and int(retire['trap']) == s['error'],
                'Wrong architectural PV encoding/trap outcome')
        selected = [r for r in offered if previous_retire < int(r['cycle']) <= cycle]
        if s['error'] and s['kind'] in ('fs_off', 'vs_off'):
            require(not selected, 'Disabled FS/VS request escaped CPU first-pass admission')
            arch.append(None)
        else:
            require(len(selected) == 1 and int(selected[0]['insn'], 16) == s['instruction'],
                    'Missing/extra PV architectural request')
            seq = int(selected[0]['order'])
            require(seq not in consumed, 'Repeated architectural identity')
            consumed.add(seq)
            arch.append(seq)
        previous_retire = cycle
    require(len(offered) == len(consumed), 'Unconsumed PV architectural requests')
    groups, qbs_rows, vadd_rows = defaultdict(list), [], []
    previous, config = -1, 0
    for row in csv_rows(vector_path):
        cycle, event, insn = int(row['cycle']), row['event'], int(row['insn'], 16)
        require(cycle >= previous and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'), 'Trace epoch/config drift')
        previous = cycle
        if event == 'config':
            require(config == 0 and cycle == 0, 'Repeated vector epoch')
            config += 1
            continue
        require(config == 1 and event in ('alloc', 'write', 'done'), 'Unknown vector event/reset')
        if pv(insn):
            groups[int(row['arch_seq'])].append(row)
        elif insn == QBS_INSN:
            qbs_rows.append(row)
        elif insn == VADD_INSN:
            vadd_rows.append(row)
    require(config == 1 and set(groups) <= consumed, 'Unowned PV allocation/write')
    probe_index, maintenance = 0, 0
    for seq, s in zip(arch, specs):
        rows = groups.get(seq, [])
        if s['error'] and s['rejection'] == 'frontend':
            require(not rows, 'Frontend illegal reached backend allocation/write')
            continue
        uops = split_uops(rows)
        expected_maintenance = 6 if s['kind'] == 'mixed' else 0
        require(len(uops) == 1+expected_maintenance, 'Unexpected PV maintenance/final allocation count')
        for index, uop in enumerate(uops[:-1]):
            reg = 8+index
            chunk = s['source'][(reg-8)*64:(reg-7)*64]
            data = {(l, reg*4+w): word16(chunk, l, w) for l in range(4) for w in range(4)}
            audit_uop(uop, reg, 64, 1, data, source=3)
            maintenance += 1
        data = {(l, h*8+w): word16(s['expected'][h*s['dimension']:(h+1)*s['dimension']], l, w)
                for l in range(4) for h in range(s['heads']) for w in range(s['dimension']//16)}
        vid = audit_uop(uops[-1], 0, 256, 1, data, writes=not s['error'])
        require(vid == probes[probe_index]['vid'], 'PV probe/vector VID mismatch')
        probe_index += 1
    require(qbs_rows and int(qbs_rows[0]['cycle']) > max(int(r['cycle']) for rs in groups.values() for r in rs),
            'QBS did not follow all PV commands')
    qbs_data = [0x43800000, 0x44000000, 0x44400000]+[0]*29
    data = {(l, 32+w): qbs_data[8*w+l] | (qbs_data[8*w+l+4] << 32)
            for l in range(4) for w in range(4)}
    audit_uop(qbs_rows, 8, 32, 2, data)
    require(vadd_rows and int(vadd_rows[0]['cycle']) > int(qbs_rows[-1]['cycle']), 'RVV did not follow QBS done')
    data = {(l, 64+w): (0x10203041+3*(8*w+l)) | ((0x10203041+3*(8*w+l+4)) << 32)
            for l in range(4) for w in range(4)}
    audit_uop(vadd_rows, 16, 32, 2, data, source=0)
    return dict(admitted_pv=24, frontend_rejected=9, backend_rejected=3,
                maintenance_uops=maintenance, actual_qbs_alloc_done=1, actual_rvv_alloc_done=1,
                command_local_flags_checked=True, actual_vrf_data_checked=True,
                same_context_recoveries=11, released_context_reloads=1,
                actual_fill_retirements=flow.count(FILL_INSN), actual_release_retirements=flow.count(RELEASE_INSN))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--vector', type=Path, required=True)
    p.add_argument('--commit', type=Path, required=True)
    a = p.parse_args()
    receipt = json.loads((a.build/'build.json').read_text())
    verify(json.loads((a.build/'source-pins.json').read_text()))
    verify(receipt['artifacts'])
    vectors = json.loads((a.build/'vectors/vectors.json').read_text())
    text = a.log.read_text()
    print(json.dumps(dict(schema=SCHEMA, numerical=check_log(text, vectors, receipt['fault_pc']),
        work=check_work(a.vector, a.commit, text, vectors), protocol_checked=False,
        scope='Supplement only; independent CPU/backend/AXI protocol audit required'), indent=2))
