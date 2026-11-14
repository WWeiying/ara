"""Backend-only evidence. A missing early-ack/CSR window is NOT a pass."""
import csv
import json
from pathlib import Path
import re


class InvalidEvidence(ValueError):
    pass


class InsufficientWindow(InvalidEvidence):
    pass


def require(condition, reason):
    if not condition:
        raise InvalidEvidence(reason)


def rows(path, kind):
    hexadecimal = ({'pc', 'insn', 'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'}
                   if kind == 'commit' else {'insn', 'be', 'wdata'})
    fields = ('cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'
              if kind == 'commit' else
              'cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits')
    with Path(path).open() as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == fields.split(','), 'Unexpected ' + kind + ' trace schema')
        result = []
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'Truncated CSV row')
            result.append({k: v if k == 'event' else int(v, 16 if k in hexadecimal else 10)
                           for k, v in row.items()})
    require(result and all(a['cycle'] <= b['cycle'] for a, b in zip(result, result[1:])),
            'Empty/nonmonotonic trace or reset')
    return result


def transactions(commit):
    tx, front, requests = {}, None, {}
    responses = []
    for r in commit:
        event = r['event']
        require(event in {'arch_start', 'cvx_req', 'cvx_resp', 'retire', 'uop_alloc', 'uop_done'},
                'Unexpected commit event')
        if event == 'arch_start':
            require(front is None and r['order'] not in tx, 'Duplicate/overlapping architectural offer')
            require(r['order'] == len(tx), 'Missing architectural sequence')
            front = dict(seq=r['order'], insn=r['insn'], tid=r['trans_id'], start=r['cycle'])
            tx[front['seq']] = front
        elif event == 'cvx_req':
            require(front is not None and (r['insn'], r['trans_id']) == (front['insn'], front['tid']),
                    'Handshake does not match first offer')
            front['request'] = r['cycle']
            requests.setdefault(front['tid'], []).append(front)
            front = None
        elif event == 'cvx_resp':
            responses.append(r)
        elif event == 'retire':
            require(not r['trap'], 'Unexpected architectural trap')
    require(front is None, 'Outstanding architectural offer')
    for r in responses:
        queue = requests.get(r['trans_id'], [])
        require(queue and queue[0]['request'] <= r['cycle'], 'Orphan/early/duplicate response')
        t = queue.pop(0)
        require(not r['trap'], 'Accelerator exception')
        t.update(response=r['cycle'], result=r['rd_wdata'])
    require(all(not q for q in requests.values()), 'Unanswered accelerator request')
    return tx


def lifetimes(vector):
    result = {}
    configs = [r for r in vector if r['event'] == 'config']
    require(len(configs) == 1, 'Missing/duplicate vector configuration')
    for r in vector:
        require((r['nr_lanes'], r['vlen_bits']) == (4, 1024), 'Geometry drift')
        event = r['event']
        require(event in {'config', 'alloc', 'write', 'done'}, 'Reset/unknown vector event')
        if event == 'config':
            continue
        key = r['arch_seq'], r['vid']
        if event == 'alloc':
            require(key not in result, 'Duplicate allocation identity')
            result[key] = dict(alloc=r, writes=[], done=None)
        else:
            require(key in result, 'Write/completion has no matching allocation identity')
            u = result[key]
            require(all(r[k] == u['alloc'][k] for k in ('insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart')),
                    'Write/completion metadata identity drift')
            if event == 'done':
                require(u['done'] is None, 'Duplicate completion')
                u['done'] = r['cycle']
            else:
                u['writes'].append(r)
    by_vid = {}
    for key, u in result.items():
        require(u['done'] is not None and u['alloc']['cycle'] <= u['done'], 'Incomplete lifetime')
        require(all(u['alloc']['cycle'] <= r['cycle'] <= u['done'] for r in u['writes']),
                'Write outside its allocated lifetime')
        by_vid.setdefault(key[1], []).append(u)
    for uses in by_vid.values():
        uses.sort(key=lambda u: u['alloc']['cycle'])
        require(all(a['done'] <= b['alloc']['cycle'] for a, b in zip(uses, uses[1:])),
                'VID reused before completion')
    return result


def actual_bytes(u, case, expected):
    writes = u['writes']
    require(writes and {w['lane'] for w in writes} == {0, 1, 2, 3}, 'Missing actual lane writes')
    actual = {}
    size = 1 << case['eew']
    bits = (8 // size).bit_length() - 1
    for w in writes:
        require(w['source'] == 4 and 0 < w['be'] <= 255, 'Not a VLDU SRAM write or invalid BE')
        word = w['addr'] - case['vd'] * 4
        require(0 <= word < len(expected) // 32, 'Write outside destination group')
        for b in range(8):
            if w['be'] & (1 << b):
                lane_element = b // size
                natural = sum(((lane_element >> k) & 1) << (bits - 1 - k) for k in range(bits))
                offset = word * 32 + (natural * 4 + w['lane']) * size + b % size
                require(offset not in actual, 'Duplicate destination byte write')
                actual[offset] = (w['wdata'] >> (8 * b)) & 255
    require(set(actual) == set(range(len(expected))), 'Incomplete destination byte/BE coverage')
    require(bytes(actual[i] for i in range(len(expected))) == expected, 'Independent VRF numerical mismatch')
    return max(w['cycle'] for w in writes)


def firmware(log, golden):
    require(log.count('Core Test *** SUCCESS ***') == 1 and log.count('DRAIN_PAYLOAD_END') == 1,
            'Missing/duplicate firmware completion')
    require(not re.search(r'DRAIN_TRAP|Fatal|Error-|UVM_(?:ERROR|FATAL)\s*:\s*[1-9]', log),
            'Firmware/RTL/UVM failure')
    pattern = (r'^DRAIN_CHECK name=(\w+) elements=([0-9a-f]{8}) checked=([0-9a-f]{8}) '
               r'mismatches=([0-9a-f]{8}) first=([0-9a-f]{8}) actual=([0-9a-f]{2}) expected=([0-9a-f]{2})$')
    checks = re.findall(pattern, log, re.M)
    require(len(checks) == 5 and len({r[0] for r in checks}) == 5, 'Missing/duplicate memory comparison')
    for name, *fields in checks:
        require(name in golden['expected'], 'Unknown output')
        n = len(bytes.fromhex(golden['expected'][name]))
        count, checked, mismatches, first, actual, expected = [int(x, 16) for x in fields]
        require(count == n // (4 if name == 'qk' else 2) and checked == n + 128,
                'Memory/guard/source comparison cardinality')
        require((mismatches, first, actual, expected) == (0, 0xffffffff, 0, 0),
                'Stored result/guard/source mismatch: ' + name)
    obs = re.findall(r'^DRAIN_OBS index=([0-9a-f]{2}) vl=([0-9a-f]{16}) '
                     r'fcsr=([0-9a-f]{16}) vstart=([0-9a-f]{16})$', log, re.M)
    require([[int(x, 16) for x in r] for r in obs] ==
            [[i, c['vl'], 1, 0] for i, c in enumerate(golden['cases'].values())],
            'VL/sticky fflags/rounding mode/vstart mismatch')


def audit(commit, vector, log, golden, symbols):
    firmware(log, golden)
    tx, life = transactions(commit), lifetimes(vector)
    report = {}
    for name, case in golden['cases'].items():
        chosen = [t for t in tx.values() if t['insn'] == case['insn']]
        require(len(chosen) == 1, name + ': missing/duplicate command')
        t = chosen[0]
        csr, save = tx.get(t['seq'] + 1), tx.get(t['seq'] + 2)
        require(csr is not None and save is not None, 'Missing immediately following CSR/save')
        for suffix, tr in (('issue', t), ('csr', csr), ('save', save)):
            spec = symbols[name + '_' + suffix]
            require(tr['insn'] == spec['insn'], 'Instruction/ELF identity mismatch')
            retires = [r for r in commit if r['event'] == 'retire' and r['pc'] == spec['pc']]
            require(len(retires) == 1 and retires[0]['insn'] == spec['insn'], 'Missing/duplicate exact-PC retirement')
            tr['retire'] = retires[0]
        require(t['retire']['order'] < csr['retire']['order'] < save['retire']['order'], 'Save retirement order')
        require(csr['result'] == csr['retire']['rd_wdata'] == case['vl'], 'CSR vl result mismatch')
        group = [(key, u) for key, u in life.items() if key[0] == t['seq']]
        require(len(group) == 1, 'Expected one target allocation, no hidden repair uops')
        key, u = group[0]
        require(all(u['alloc'][k] == case[k] for k in ('insn', 'vd', 'eew', 'vl')) and
                u['alloc']['use_vd'] == 1 and u['alloc']['vstart'] == 0, 'Target allocation metadata')
        for event, cycle in (('uop_alloc', u['alloc']['cycle']), ('uop_done', u['done'])):
            events = [r for r in commit if r['event'] == event and r['order'] == key[0] and r['port'] == key[1]]
            require(len(events) == 1 and events[0]['cycle'] == cycle and
                    events[0]['insn'] == t['insn'] and events[0]['trans_id'] == t['tid'],
                    'Commit/vector trace lifetime identity disagreement')
        last = actual_bytes(u, case, bytes.fromhex(golden['expected'][name]))
        require(last <= u['done'] <= csr['response'], 'CSR response before final write/backend completion')
        require(t['response'] <= csr['start'] and csr['response'] <= save['start'], 'Save/CSR issued out of order')
        require(csr['response'] <= save['request'], 'Save handshake before CSR response')
        if case['early']:
            if not (t['response'] < last and csr['start'] < last):
                raise InsufficientWindow(name + ': no nonempty early response AND CSR-arrival/final-write window')
        else:
            require(last <= u['done'] <= t['response'], 'Resident QK/PV returned before terminal completion')
        report[name] = dict(arch_seq=key[0], vid=key[1], first_offer=t['start'], response=t['response'],
                            csr_first_offer=csr['start'], last_sram_write=last, backend_done=u['done'],
                            csr_response=csr['response'], save_first_offer=save['start'],
                            actual_write_events=len(u['writes']), checked_result_bytes=len(bytes.fromhex(golden['expected'][name])))
    return dict(state='BACKEND_ONLY_CHECKED', gate_tested=False, linux_tested=False, board_tested=False,
                actual_sram_writes_checked=True, stored_results_guards_source_checked=True, cases=report)


def check(work, inputs):
    return audit(rows(Path(work) / 'commit.csv', 'commit'), rows(Path(work) / 'vector.csv', 'vector'),
                 (Path(work) / 'run.vcs.log').read_text(),
                 json.loads((Path(inputs) / 'golden.json').read_text()),
                 json.loads((Path(inputs) / 'symbols.json').read_text()))
