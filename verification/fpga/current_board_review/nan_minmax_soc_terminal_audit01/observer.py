"""Adapted mature ordered-reduction one-pass observer; no guest execution."""
import collections
import hashlib
import json
import re

def independent_oracle(seed, mask):
    # Exact original scenario1: quiet NaN seed and all quiet NaN source words.
    assert seed == 0x7fc12345 and mask in (0,0x24)
    active = [index for index in range(3) if mask & (1 << index)]
    assert active == ([] if mask == 0 else [2])
    assert (seed & 0x7f800000) == 0x7f800000 and seed & 0x400000
    return 0x7fc00000 if active else seed

def input_index(s, i):
    if s == 0: return i % 2, False
    if s == 1: return 14, False
    if s == 2: return (2 if i % 2 else 15), False
    if s == 3: return (13 if i % 2 else 12), False
    if s == 4: return [2, 7, 3, 7, 11, 11][i % 6], i % 6 in (3, 5)
    if s == 5: return [8, 9, 10, 8, 9, 10][i % 6], i % 6 >= 3
    if s == 6: return (15 if i % 2 else 2), False
    return (7 if i % 2 else 2), False


def vector(i):
    op, width = i & 127, (i >> 12) & 7
    return (op in (0x57, 0x5b) or op in (7, 0x27, 0x2f) and width in (0, 5, 6, 7)
            or op == 0x73 and i >> 20 in (8, 9, 10, 15, 0xc20, 0xc21, 0xc22))


class Observer:
    def __init__(self, spec, source, protocol):
        self.spec = spec
        self.protocol = protocol
        self.config = spec['config']
        self.source = source
        self.count = collections.Counter()
        self.pc = collections.Counter()
        self.pending, self.uops = {}, {}
        self.requests, self.arch, self.retvec = [], [], []
        self.first = self.last = -1
        self.maxcvx = self.maxuop = 0
        self.before = hashlib.sha256()
        self.after = hashlib.sha256()
        self.regs = [None]*32
        self.regs[0] = 0
        self.fixture_reads, self.output_reads, self.restores = [], [], []
        self.capacity, self.prelude, self.helper = [], [], []
        self.exit = None
        self.hp = [x['pc'] for x in spec['routine']]
        self.cp = [x['pc'] for x in spec['capacity_routine']]
        self.pp = [x['pc'] for x in spec['csr_prelude']]
        self.bits = [int(x, 16) for x in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)',
                                                  (source/'prepared/input_bits.h').read_text())]
        assert len(self.bits) == 16 and self.bits[14] == 0x7fc12345
        self.result = independent_oracle(self.bits[14], self.config['mask_byte'])

    def rows(self, reader):
        assert reader.fieldnames == ['cycle', 'event', 'order', 'port', 'trans_id', 'pc', 'insn',
                                    'rd', 'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata', 'trap']
        for row in reader:
            original = tuple(row.items())
            assert None not in row and all(isinstance(v, str) for v in row.values())
            payload = json.dumps(original, separators=(',', ':')).encode()+b'\n'
            self.before.update(payload)
            self.observe(row)
            yield row
            assert tuple(row.items()) == original, 'Sealed consumer changed original row'
            self.after.update(json.dumps(tuple(row.items()), separators=(',', ':')).encode()+b'\n')
            self.count['unmodified_delivered_rows'] += 1

    def observe(self, r):
        c, e, i, order = int(r['cycle']), r['event'], int(r['insn'], 16), int(r['order'])
        assert c >= self.last and int(r['trap']) == 0
        if self.first < 0: self.first = c
        self.last = c
        self.count['rows'] += 1
        self.count[e] += 1
        if e == 'cvx_req':
            tid = int(r['trans_id'])
            assert vector(i) and tid not in self.pending
            self.pending[tid] = i
            self.requests.append(i)
            self.maxcvx = max(self.maxcvx, len(self.pending))
        elif e == 'cvx_resp':
            assert int(r['trans_id']) in self.pending
            del self.pending[int(r['trans_id'])]
        elif e == 'arch_start':
            assert order == len(self.arch)
            self.arch.append(i)
        elif e == 'uop_alloc':
            vid = int(r['port'])
            assert 0 <= order < len(self.arch) and self.arch[order] == i and vid not in self.uops
            self.uops[vid] = (order, i)
            self.maxuop = max(self.maxuop, len(self.uops))
        elif e == 'uop_done':
            assert self.uops.pop(int(r['port'])) == (order, i)
        else:
            assert e == 'retire' and order == self.count['retire']-1
            if vector(i): self.retvec.append(i)
            self.retirement(r, c, i, order)

    def retirement(self, r, cycle, i, order):
        s, sy, sites = self.spec, self.spec['symbols'], self.spec['sites']
        pc, rd, value = int(r['pc'], 16), int(r['rd']), int(r['rd_wdata'], 16)
        addr, rm, wm, wd = (int(r[k], 16) for k in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        assert int(s['instructions'][f'{pc:x}']['insn'], 16) == i
        self.pc[pc] += 1
        assert not any(lo <= pc < hi for lo, hi in s['unused_ranges']) and pc != sy['trap_entry']
        hp, cp, pp = self.hp, self.cp, self.pp
        if pc in hp:
            j = len(self.helper)
            assert j < 21 and pc == hp[j]
            if j: assert order == self.helper[-1]['order']+1
            expected = {0:(5,32),3:(5,32),6:(5,3),7:(29,0),8:(30,0),
                        12:(10,0),13:(6,0),14:(6,0),15:(10,0),18:(5,32)}
            if j in expected:
                assert (rd,value) == expected[j]
            if j == 0:
                assert self.regs[10:18] == [sy['input'],sy['seed'],sy['output']+8,3,32,sy['mask'],0,0]
                assert len(self.fixture_reads) == 2*(self.config['fixture_row']+1)
            self.helper.append(dict(pc=hex(pc), order=order, cycle=cycle, rd=rd, value=value))
            if j in (9, 10, 16, 17):
                src = (i >> 15) & 31
                assert self.regs[src] == 0 and rd == 0
                self.restores.append(dict(pc=hex(pc), csr=i >> 20, source_register=src,
                                          source_value=self.regs[src], order=order))
        if pc in cp:
            j = len(self.capacity)
            assert j < 3 and pc == cp[j]
            if j: assert order == self.capacity[-1]['order']+1
            self.capacity.append(dict(pc=hex(pc), order=order, rd=rd, value=value))
        if i & 127 == 0x73 and (i >> 12) & 7 and pc not in hp:
            assert len(self.prelude) < 7 and pc == pp[len(self.prelude)] and not self.capacity
            self.prelude.append(pc)
        # Every initialization write is checked against the unchanged original source loop.
        for name, area, width in [('input_store', 'input', 4), ('seed_store', 'seed', 4),
                                  ('mask_store', 'mask', 1), ('output_init', 'output', 1)]:
            if pc != sites[name]: continue
            n = self.count[name]
            if name == 'input_store':
                scenario, j = divmod(n, 32)
                assert scenario < 8
                idx, sign = input_index(scenario, j)
                want = self.bits[idx] ^ (0x80000000 if sign else 0)
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
            assert addr == sy[area]+j*width and wm == ((1 << width)-1) << (addr % 8)
            assert wd & ((1 << (8*width))-1) == want
            self.count[name] += 1
        if pc in (sites['fixture_bits'], sites['fixture_flags']):
            n = len(self.fixture_reads)
            row, field = 3360+n//2, n % 2
            assert n < 6720 and addr == sy['fixtures']+row*16+field*8
            assert pc == sites['fixture_flags' if field else 'fixture_bits']
            assert rm == (15 if field else 255) and rd == (15 if field else 14)
            assert value == s['fixtures'][row][field]
            self.fixture_reads.append([addr, value])
        if pc == sites['output_read']:
            n = len(self.output_reads)
            want = self.result.to_bytes(4,'little')[n-8] if 8 <= n < 12 else 91
            assert n < 144 and len(self.helper) == 21 and addr == sy['output']+n
            assert rd == 10 and value == want and rm == 1 << (addr % 8)
            self.output_reads.append([addr, value])
        if addr == s['exit_address'] and wm:
            assert self.exit is None and pc == s['exit_store']['pc'] and wm == 255 and wd == 0
            assert len(self.output_reads) == 144 and len(self.fixture_reads) == 6720
            self.exit = dict(pc=hex(pc), order=order, cycle=cycle, address=hex(addr), value=wd)
        if rd: self.regs[rd] = value

    def finish(self):
        c = self.count
        assert not self.pending and not self.uops
        cvx_replays = self.protocol._validate_retired_request_sequence(self.retvec,self.requests)
        arch_replays = self.protocol._validate_retired_request_sequence(self.arch,self.requests)
        assert c['rows'] == c['unmodified_delivered_rows'] and self.before.digest() == self.after.digest()
        assert len(self.helper) == 21 and len(self.capacity) == 3 and len(self.prelude) == 7
        assert len(self.restores) == 4 and self.exit and len(self.output_reads) == 144
        assert [c[k] for k in ('input_store', 'seed_store', 'mask_store', 'output_init')] == [256, 512, 215040, 144]
        return dict(rows=c['rows'], first_cycle=self.first, last_cycle=self.last, retire_count=c['retire'],
                    vector_retire_count=len(self.retvec), cvx_request_count=c['cvx_req'],
                    cvx_response_count=c['cvx_resp'], cvx_max_inflight=self.maxcvx, cvx_replay_count=cvx_replays,
                    arch_request_replay_count=arch_replays, cvx_exception_count=0, architecture_request_count=len(self.arch),
                    backend_uop_alloc_count=c['uop_alloc'], backend_uop_done_count=c['uop_done'],
                    backend_uop_max_inflight=self.maxuop)


