"""Lossless single-pass observer; only consumes rows provided by terminal audit."""
from collections import Counter
import hashlib
import json

FIELDS = ['cycle', 'event', 'order', 'port', 'trans_id', 'pc', 'insn', 'rd',
          'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata', 'trap']


def vector(i):
    op, width = i & 127, (i >> 12) & 7
    return (op in (0x57, 0x5b) or op in (7, 0x27, 0x2f) and width in (0, 5, 6, 7)
            or op == 0x73 and i >> 20 in (8, 9, 10, 15, 0xc20, 0xc21, 0xc22))


def input_index(s, i):
    if s == 0: return i % 2, False
    if s == 1: return 14, False
    if s == 2: return (2 if i % 2 else 15), False
    if s == 3: return (13 if i % 2 else 12), False
    if s == 4: return [2, 7, 3, 7, 11, 11][i % 6], i % 6 in (3, 5)
    if s == 5: return [8, 9, 10, 8, 9, 10][i % 6], i % 6 >= 3
    if s == 6: return (15 if i % 2 else 2), False
    return (7 if i % 2 else 2), False


class Observer:
    def __init__(self, spec):
        self.spec, self.config = spec, spec['config']
        self.width, self.cap = self.config['word_bytes'], self.config['cap']
        self.bits = spec['input_bits']
        self.count, self.pcs = Counter(), Counter()
        self.pending, self.uops = {}, {}
        self.requests, self.arch, self.retvec = [], [], []
        self.first = self.last = -1
        self.maxcvx = self.maxuop = 0
        self.before, self.after = hashlib.sha256(), hashlib.sha256()
        self.regs = [0]*32
        self.fixtures, self.output, self.restores = [], [], []
        self.capacity, self.prelude, self.helper = [], [], []
        self.exit = None
        self.hp = [x['pc'] for x in spec['routine']]
        self.cp = [x['pc'] for x in spec['capacity_routine']]
        self.pp = [x['pc'] for x in spec['csr_prelude']]
        self.expected_output = b'\x5b'*8 + self.config['nan'].to_bytes(self.width, 'little') + b'\x5b'*(136-self.width)

    def rows(self, reader):
        assert reader.fieldnames == FIELDS
        for row in reader:
            original = tuple(row.items())
            assert None not in row and all(isinstance(v, str) for v in row.values())
            self.before.update(json.dumps(original, separators=(',', ':')).encode()+b'\n')
            self.observe(row)
            yield row
            assert tuple(row.items()) == original, 'Sealed checker modified an original row'
            self.after.update(json.dumps(tuple(row.items()), separators=(',', ':')).encode()+b'\n')
            self.count['unmodified_delivered_rows'] += 1

    def observe(self, r):
        cycle, event, i, order = int(r['cycle']), r['event'], int(r['insn'], 16), int(r['order'])
        assert cycle >= self.last and int(r['trap']) == 0
        if self.first < 0: self.first = cycle
        self.last = cycle
        self.count['rows'] += 1
        self.count[event] += 1
        if event == 'cvx_req':
            tid = int(r['trans_id'])
            assert vector(i) and tid not in self.pending
            self.pending[tid] = i
            self.requests.append(i)
            self.maxcvx = max(self.maxcvx, len(self.pending))
        elif event == 'cvx_resp':
            assert int(r['trans_id']) in self.pending
            del self.pending[int(r['trans_id'])]
        elif event == 'arch_start':
            assert order == len(self.arch)
            self.arch.append(i)
        elif event == 'uop_alloc':
            vid = int(r['port'])
            assert 0 <= order < len(self.arch) and self.arch[order] == i and vid not in self.uops
            self.uops[vid] = (order, i)
            self.maxuop = max(self.maxuop, len(self.uops))
        elif event == 'uop_done':
            assert self.uops.pop(int(r['port'])) == (order, i)
        else:
            assert event == 'retire' and order == self.count['retire']-1
            if vector(i): self.retvec.append(i)
            self.retirement(r, cycle, i, order)

    def retirement(self, r, cycle, i, order):
        s, sy, sites = self.spec, self.spec['symbols'], self.spec['sites']
        pc, rd, value = int(r['pc'], 16), int(r['rd']), int(r['rd_wdata'], 16)
        addr, rm, wm, wd = (int(r[k], 16) for k in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        assert int(s['instructions'][f'{pc:x}']['insn'], 16) == i
        self.pcs[pc] += 1
        assert not any(lo <= pc < hi for lo, hi in s['unused_ranges']) and pc != sy['trap_entry']
        if self.exit:
            assert pc == s['park']['pc'] and i == 0xa001 and rd == rm == wm == 0
            return
        if pc in self.hp:
            j = len(self.helper)
            assert j < 21 and pc == self.hp[j]
            if j: assert order == self.helper[-1]['order']+1
            self.helper.append(dict(pc=hex(pc), order=order, cycle=cycle, rd=rd, value=value))
            if j == 0:
                assert len(self.capacity) == 3 and len(self.prelude) == 7 and len(self.fixtures) == 3092
                assert self.regs[10:18] == [sy['input'], sy['seed'], sy['output']+8,
                                           self.config['vl'], self.cap, sy['mask'], 0, 0]
            returns = {0: (5, 128//self.width), 3: (5, self.cap), 6: (5, self.config['vl']),
                       7: (29, 0), 8: (30, 0), 12: (10, 0), 13: (6, 16),
                       14: (6, 16 << 32), 15: (10, 16 << 32), 18: (5, 128//self.width)}
            if j in returns: assert (rd, value) == returns[j]
            if j in (9, 10, 16, 17):
                src = (i >> 15) & 31
                assert self.regs[src] == 0 and rd == 0
                self.restores.append(dict(pc=hex(pc), csr=i >> 20, source_register=src,
                                          source_value=self.regs[src], order=order))
        if pc in self.cp:
            j = len(self.capacity)
            assert j < 3 and pc == self.cp[j] and len(self.prelude) == 7 and not self.helper
            if j: assert order == self.capacity[-1]['order']+1
            if j == 0: assert (rd, value) == (5, (1 << 64)-1)
            if j == 1: assert (rd, value) == (10, self.cap) and self.regs[5] == (1 << 64)-1
            self.capacity.append(dict(pc=hex(pc), order=order, rd=rd, value=value))
        if i & 127 == 0x73 and (i >> 12) & 7 and pc not in self.hp:
            assert len(self.prelude) < 7 and pc == self.pp[len(self.prelude)] and not self.capacity
            if i >> 20 == 0xc22: assert rd == (i >> 7) & 31 and value == 128
            self.prelude.append(pc)
        for name, area, width in [('input_store', 'input', self.width), ('seed_store', 'seed', self.width),
                                  ('mask_store', 'mask', 1), ('output_init', 'output', 1)]:
            if pc != sites[name]: continue
            n = self.count[name]
            if name == 'input_store':
                scenario, j = divmod(n, self.cap)
                assert scenario < 8
                idx, sign = input_index(scenario, j)
                want = self.bits[idx] ^ ((1 << (self.config['sew']-1)) if sign else 0)
            elif name == 'seed_store':
                scenario, j = divmod(n, 64)
                assert scenario < 8
                want = self.bits[[1, 14, 2, 12, 2, 8, 1, 12][scenario]]
            elif name == 'mask_store':
                fill, j = divmod(n, 64)
                assert fill < 3360
                want = [255, 0, 85, 36][(fill//15) % 4]
            else:
                j, want = n, 91
                assert j < 144 and not self.helper
            assert addr == sy[area]+j*width and wm == ((1 << width)-1) << (addr % 8) and wd == want
            self.count[name] += 1
        if pc in (sites['fixture_bits'], sites['fixture_flags']):
            n = len(self.fixtures)
            row, field = 3360+n//2, n % 2
            assert n < 6720 and addr == sy['fixtures']+row*16+field*8
            assert pc == sites['fixture_flags' if field else 'fixture_bits']
            assert rm == (15 if field else 255) and rd == (15 if field else 14)
            assert value == s['fixtures'][row][field]
            self.fixtures.append([addr, value])
        if pc == sites['output_read']:
            n = len(self.output)
            assert n < 144 and len(self.helper) == 21 and addr == sy['output']+n
            assert rd == (i >> 7) & 31 and value == self.expected_output[n] and rm == 1 << (addr % 8)
            self.output.append([addr, value])
        if addr == s['exit_address'] and wm:
            assert pc == s['exit_store']['pc'] and wm == 255 and wd == 0
            assert len(self.output) == 144 and len(self.fixtures) == 6720
            self.exit = dict(pc=hex(pc), order=order, cycle=cycle, address=hex(addr), value=wd)
        if rd: self.regs[rd] = value

    def finish(self):
        c = self.count
        assert not self.pending and not self.uops and self.retvec == self.requests == self.arch
        assert c['rows'] == c['unmodified_delivered_rows'] and self.before.digest() == self.after.digest()
        assert len(self.helper) == 21 and len(self.capacity) == 3 and len(self.prelude) == 7
        assert len(self.restores) == 4 and self.exit and len(self.output) == 144
        assert [c[k] for k in ('input_store', 'seed_store', 'mask_store', 'output_init')] == [8*self.cap, 512, 215040, 144]
        return dict(rows=c['rows'], first_cycle=self.first, last_cycle=self.last, retire_count=c['retire'],
                    vector_retire_count=len(self.retvec), cvx_request_count=c['cvx_req'],
                    cvx_response_count=c['cvx_resp'], cvx_max_inflight=self.maxcvx, cvx_replay_count=0,
                    arch_request_replay_count=0, cvx_exception_count=0, architecture_request_count=len(self.arch),
                    backend_uop_alloc_count=c['uop_alloc'], backend_uop_done_count=c['uop_done'],
                    backend_uop_max_inflight=self.maxuop)

    def evidence(self):
        return dict(original_rows_delivered_unmodified=self.count['unmodified_delivered_rows'],
                    before_sha256=self.before.hexdigest(), after_sha256=self.after.hexdigest(),
                    counts=dict(self.count), actual_pc_counts={hex(k): v for k, v in self.pcs.items()},
                    helper=self.helper, capacity=self.capacity, prelude=[hex(p) for p in self.prelude],
                    csr_write_operands=self.restores, output_reads=self.output,
                    fixture_field_reads=len(self.fixtures), exit=self.exit,
                    post_restore_csr_state_directly_measured=False)
