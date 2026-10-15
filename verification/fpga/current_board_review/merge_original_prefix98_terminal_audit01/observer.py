"""Merge-specific oracle observer over unchanged mature row/transport machinery."""
from collections import Counter
import hashlib
import itertools

from support import TRANSPORT, TRANSPORT_SHA, load, sha

assert sha(TRANSPORT) == TRANSPORT_SHA
Transport = load(TRANSPORT, 'sealed_remaining9_transport').Observer
CAP, CALLS = 512, 98


def model():
    # Independent transcription of original seed0/op4/scalar-slot0 nested loops.
    rng, data, indices = 0xe736815b449aec21, [], []
    for i in range(CAP):
        rng = (rng ^ (rng << 13)) & ((1 << 64)-1)
        rng ^= rng >> 7
        rng = (rng ^ (rng << 17)) & ((1 << 64)-1)
        data.append(rng & 0xffff)
        indices.append([0, 1, 511, 512, 513, rng % 544][i % 6])
    rows = []
    for length, mode, trial in itertools.product(range(7), range(4), range(4)):
        vl = [0, 1, 2, 3, 256, 511, 512][length]
        start = [1, vl//2, vl, 511][trial]
        predicate, output = [0]*128, [91]*CAP
        for i in range(CAP):
            selected = mode == 0 or mode == 1 and i % 2 == 1 or mode == 2 and i % 7 == 2
            if selected: predicate[i//8] |= 1 << (i % 8)
            if start <= i < vl: output[i] = indices[i] if selected else data[i]
        rows.append(dict(ordinal=len(rows)+1, tuple=[0, 4, 0, length, mode, trial],
                         vl=vl, vstart=start, scalar=0, predicate=predicate, output=output))
        if len(rows) == CALLS: break
    digest = lambda a: hashlib.sha256(b''.join(x.to_bytes(2, 'little') for x in a)).hexdigest()
    assert rows[-1]['tuple'] == [0, 4, 0, 6, 0, 1]
    return dict(sew=16, lmul='m8', capacity=CAP, input=data, indices=indices, indices16=indices,
        input_bytes_sha256=digest(data), index_bytes_sha256=digest(indices), rows=rows,
        excluded_ops0_through3_empty_iterations=3584, original_calls=2688,
        original_stopped_tuple=None, fullcap_checks=50176, guards=196)


def setup_events(spec, gold):
    a, sites = spec['addresses'], spec['sites']
    for i in range(128): yield sites['pred_clear'], a['predicate']+i, 0, 1
    packed = [0]*128
    for i in range(CAP):
        if gold['predicate'][i//8] & (1 << (i % 8)):
            packed[i//8] |= 1 << (i % 8)
            yield sites['pred_pack'], a['predicate']+i//8, packed[i//8], 1
    for i in range(CAP+2): yield sites['output_init'], a['output']+2*i, 91, 2


class Observer(Transport):
    # Reuse only mature rows()/observe() transport code, not reduction semantics.
    def __init__(self, spec, gold):
        self.spec, self.gold = spec, gold
        self.count, self.pcs = Counter(), Counter()
        self.pending, self.uops = {}, {}
        self.requests, self.arch, self.retvec = [], [], []
        self.first = self.last = -1
        self.maxcvx = self.maxuop = 0
        self.before, self.after = hashlib.sha256(), hashlib.sha256()
        self.regs = [0]*32
        self.hp = [r['pc'] for r in spec['routine']]
        self.cp = [r['pc'] for r in spec['capacity']]
        self.pp = [r['pc'] for r in spec['prelude']]
        self.setup_pcs = {spec['sites'][n]: n for n in ('input', 'indices', 'indices16', 'pred_clear', 'pred_pack', 'output_init')}
        self.read_pcs = {spec['sites'][n] for n in ('output_read', 'guard0', 'guard1')}
        self.initial = [(spec['sites'][n], spec['addresses'][n]+2*i, gold[n][i], 2)
                        for i in range(CAP) for n in ('input', 'indices', 'indices16')]
        self.initial_pos = self.setup_pos = self.step = 0
        self.events = list(setup_events(spec, gold['rows'][0]))
        self.calls, self.capacity, self.prelude = [], [], []
        self.exit = None

    def retirement(self, row, cycle, insn, order):
        s, a, sites = self.spec, self.spec['addresses'], self.spec['sites']
        pc, rd, value = int(row['pc'], 16), int(row['rd']), int(row['rd_wdata'], 16)
        address, rm, wm, wd = (int(row[n], 16) for n in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        assert int(s['instructions'][f'{pc:x}']['insn'], 16) == insn
        self.pcs[pc] += 1
        if self.exit:
            assert pc == s['park']['pc'] and insn == 0xa001 and rd == rm == wm == 0
            self.count['park'] += 1
            return
        assert pc != s['symbols']['trap_entry'] and not any(lo <= pc < hi for lo, hi in s['unused_ranges'])
        if self.step: assert pc == self.hp[self.step]
        if 0 < len(self.capacity) < 3: assert pc == self.cp[len(self.capacity)]
        if pc in self.cp:
            j = len(self.capacity)
            assert j < 3 and pc == self.cp[j] and len(self.prelude) == 6 and not self.calls
            if j: assert order == self.capacity[-1]['order']+1
            if j == 0: assert (rd, value) == (5, (1 << 64)-1)
            if j == 1: assert (rd, value) == (10, CAP) and self.regs[5] == (1 << 64)-1
            self.capacity.append(dict(pc=hex(pc), order=order, value=value))
        if insn & 127 == 0x73 and (insn >> 12) & 7 and pc not in self.hp:
            j = len(self.prelude)
            assert j < 7 and pc == self.pp[j] and not self.calls
            assert len(self.capacity) == (3 if j == 6 else 0)
            operand = (insn >> 15) & 31
            if not (insn >> 12) & 4: operand = self.regs[operand]
            if j < 5: assert rd == 0 and operand == [0, s['symbols']['trap_entry'], 0x6600, 0, 0][j]
            else: assert rd == (insn >> 7) & 31 and value == 128
            self.prelude.append(dict(pc=hex(pc), order=order, operand=operand, value=value))
        if pc == sites['filter']:
            self.count['filter'] += 1
            assert self.count['filter'] <= 3584+CALLS
        if pc in self.setup_pcs:
            assert self.step == 0 and len(self.capacity) == 3 and len(self.prelude) == 7
            if self.initial_pos < len(self.initial):
                event = self.initial[self.initial_pos]; self.initial_pos += 1
            else:
                if self.calls: assert len(self.calls[-1]['reads']) == CAP+2
                assert self.setup_pos < len(self.events)
                event = self.events[self.setup_pos]; self.setup_pos += 1
            epc, ea, ev, width = event
            assert (pc, address) == (epc, ea) and wm == ((1 << width)-1) << (address % 8)
            assert wd & ((1 << (width*8))-1) == ev
            self.count[self.setup_pcs[pc]] += 1
        if pc in self.hp:
            j = self.hp.index(pc)
            assert j == self.step and len(self.capacity) == 3 and len(self.prelude) == 7
            if j == 0:
                if self.calls: assert len(self.calls[-1]['reads']) == CAP+2
                index = len(self.calls)
                assert index < CALLS and self.initial_pos == len(self.initial) and self.setup_pos == len(self.events)
                assert self.count['filter'] == 3584+index+1
                gold = self.gold['rows'][index]
                args = [a['input'], a['indices'], a['output']+2, gold['vl'], CAP, a['predicate'], 0, gold['vstart']]
                assert self.regs[10:18] == args
                self.calls.append(dict(ordinal=index+1, original_tuple=gold['tuple'], args=args,
                                       helper=[], reads=[], returned_vstart=None))
            current = self.calls[-1]; gold = self.gold['rows'][len(self.calls)-1]
            if j: assert order == current['helper'][-1]['order']+1
            if j in (0, 5, 10):
                want = gold['vl'] if j == 5 else CAP
                assert (rd, value) == (5, want) and self.regs[13 if j == 5 else 14] == want
            if j == 6: assert (rd, value) == (28, 0)
            if j == 7: assert rd == 0 and self.regs[17] == gold['vstart']
            if j == 8:
                assert insn == 0x5c880c57 and self.regs[28] == 0 and self.regs[17] == gold['vstart']
                current['target'] = dict(pc=hex(pc), cycle=cycle, order=order)
            if j == 9:
                assert (rd, value) == (10, 0); current['returned_vstart'] = 0
            if j == 11: assert self.regs[12] == a['output']+2
            current['helper'].append(dict(pc=hex(pc), order=order, cycle=cycle, rd=rd, value=value))
            self.step = (j+1) % 13
        if pc in self.read_pcs:
            assert self.calls and self.step == 0
            current = self.calls[-1]; gold = self.gold['rows'][len(self.calls)-1]
            n = len(current['reads'])
            assert n < CAP+2 and len(current['helper']) == 13
            index = n+1 if n < CAP else 0 if n == CAP else CAP+1
            expected_pc = sites['output_read'] if n < CAP else sites['guard0' if n == CAP else 'guard1']
            expected = gold['output'][index-1] if n < CAP else 91
            assert pc == expected_pc and address == a['output']+2*index and rm == 3 << (address % 8)
            assert not wm and rd == (insn >> 7) & 31 and value == expected
            current['reads'].append([index, value])
            self.count['fullcap_checks' if n < CAP else 'guards'] += 1
            if n < CAP and gold['vstart'] <= index-1 < gold['vl']:
                bit = (gold['predicate'][(index-1)//8] >> ((index-1) % 8)) & 1
                self.count['selector_one_body_checks' if bit else 'selector_zero_body_checks'] += 1
            if n == CAP+1:
                self.events = list(setup_events(s, self.gold['rows'][len(self.calls)])) if len(self.calls) < CALLS else []
                self.setup_pos = 0
        if pc == s['exit_store']['pc'] or address == s['exit_address'] and wm:
            assert pc == s['exit_store']['pc'] and address == s['exit_address'] and wm == 255 and wd == 0
            assert len(self.calls) == CALLS and len(self.calls[-1]['reads']) == CAP+2 and not self.step
            self.exit = dict(pc=hex(pc), order=order, cycle=cycle, value=0)
        if rd: self.regs[rd] = value

    def finish(self):
        c = self.count
        assert not self.pending and not self.uops and self.retvec == self.requests == self.arch
        assert c['rows'] == c['unmodified_delivered_rows'] and self.before.digest() == self.after.digest()
        assert self.exit and len(self.calls) == CALLS and len(self.capacity) == 3 and len(self.prelude) == 7
        assert all(len(x['helper']) == 13 and len(x['reads']) == 514 and x['returned_vstart'] == 0 for x in self.calls)
        assert (c['fullcap_checks'], c['guards'], c['selector_zero_body_checks'], c['selector_one_body_checks']) == (50176, 196, 2722, 2669)
        return dict(rows=c['rows'], first_cycle=self.first, last_cycle=self.last, retire_count=c['retire'],
            vector_retire_count=len(self.retvec), cvx_request_count=c['cvx_req'], cvx_response_count=c['cvx_resp'],
            cvx_max_inflight=self.maxcvx, cvx_replay_count=0, arch_request_replay_count=0, cvx_exception_count=0,
            architecture_request_count=len(self.arch), backend_uop_alloc_count=c['uop_alloc'],
            backend_uop_done_count=c['uop_done'], backend_uop_max_inflight=self.maxuop)

    def evidence(self):
        return dict(original_rows_delivered_unmodified=self.count['unmodified_delivered_rows'],
            before_sha256=self.before.hexdigest(), after_sha256=self.after.hexdigest(), counts=dict(self.count),
            actual_pc_counts={hex(k): v for k, v in self.pcs.items()}, calls=self.calls,
            capacity=self.capacity, prelude=self.prelude, exit=self.exit,
            vector_payload_directly_observed=False, returned_vstart_read_scope='98 original csrr reads, not reference CSR log')
