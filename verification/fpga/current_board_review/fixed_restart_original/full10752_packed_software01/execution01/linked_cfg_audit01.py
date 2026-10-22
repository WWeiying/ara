"""Linked positive scalar CFG accounting, NOT an architectural reference run.

Scalar branch constants come from the pinned ELF and original loop inputs.
Only capacity and the four byte-identical vector helpers have summaries: their
instructions are all charged, but their successful results are HYPOTHESES from
the independently Host-validated oracle. No ISA simulator is invoked.
"""
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GEN = ROOT / 'generated01'
BUILD = HERE / 'compile01'
OLD = ROOT.parent / 'full777_optimized_prepare01/prepared01'
ORIGINAL = ROOT.parent / 'recovery01/rvv_fixed_restart_e8_m4'
OUT = HERE / 'linked_cfg01'
MASK = (1 << 64) - 1
BASE = 0x80000000
SIZE = 1 << 20


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def signed(x, bits):
    x &= (1 << bits) - 1
    return x - (1 << bits) if x >> (bits - 1) else x


def elf(path):
    data = Path(path).read_bytes()
    require(data[:6] == b'\x7fELF\x02\x01', 'ELF64 little endian')
    h = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    require(h[1] == 243, 'RISC-V ELF')
    result = []
    for i in range(h[9]):
        typ, flags, off, va, pa, fs, ms, align = struct.unpack_from('<IIQQQQQQ', data, h[4] + h[8] * i)
        if typ == 1:
            require(fs <= ms and off + fs <= len(data), 'Bounded PT_LOAD')
            result.append(dict(va=va, flags=flags, data=data[off:off + fs], mem=ms))
    return result


def parse_dis(path):
    code, functions = {}, collections.defaultdict(list)
    name = None
    for line in Path(path).read_text().splitlines():
        m = re.fullmatch(r'([0-9a-f]+) <([^>]+)>:', line)
        if m:
            name = m[2]
        m = re.match(r'^\s+([0-9a-f]+):\s+([0-9a-f]{4}|[0-9a-f]{8})\s+(\S+)\s*(.*)$', line)
        if not m:
            continue
        pc = int(m[1], 16)
        require(pc not in code and name is not None, 'Unique named disassembly PC')
        blob = int(m[2], 16).to_bytes(len(m[2]) // 2, 'little')
        require(len(blob) == (4 if blob[0] & 3 == 3 else 2), 'Instruction length')
        args = m[4].split('#')[0].strip()
        code[pc] = dict(pc=pc, blob=blob, op=m[3], args=args,
                        p=[x.strip() for x in args.split(',')] if args else [], function=name)
        functions[name].append(code[pc])
    return code, functions


def symbols(path):
    syms, sizes = {}, {}
    for line in Path(path).read_text().splitlines():
        p = line.split()
        if len(p) in (3, 4):
            syms[p[-1]] = int(p[0], 16)
            if len(p) == 4:
                sizes[p[-1]] = int(p[1], 16)
    return syms, sizes


SUPPORTED = set('add addi addiw andi auipc beq beqz bgeu bltu bltz bne bnez csrr csrs csrw csrwi divu fence j jal jalr lbu ld lhu li lui lw lwu mul mv or ori remu ret sb sd sext.w sh slli snez srli srliw sw xor'.split())
POSITIVE = {'_start', 'replay_exit', 'fixed_full_main', 'main', 'text', 'number', 'replay_text', 'replay_write'}


class CFG:
    def __init__(self, backend, model, original_helpers):
        self.backend = backend
        self.model = model
        self.code, self.func = parse_dis(BUILD / backend / 'dis.log')
        self.s, self.sizes = symbols(BUILD / backend / 'symbols.log')
        self.segments = elf(BUILD / backend / 'program.elf')
        self.mem = bytearray(SIZE)
        self.known = bytearray(SIZE)
        self.readonly = bytearray(SIZE)
        for seg in self.segments:
            off = seg['va'] - BASE
            require(0 <= off and off + seg['mem'] <= SIZE, 'All segments in 1 MiB')
            self.mem[off:off + len(seg['data'])] = seg['data']
            self.known[off:off + len(seg['data'])] = b'\1' * len(seg['data'])
            if not seg['flags'] & 2:
                self.readonly[off:off + seg['mem']] = b'\1' * seg['mem']
        for pc, x in self.code.items():
            require(bytes(self.mem[pc - BASE:pc - BASE + len(x['blob'])]) == x['blob'], 'Disassembly/ELF bytes ' + hex(pc))
            if x['function'] in POSITIVE:
                require(x['op'] in SUPPORTED, 'Preflight unsupported scalar opcode ' + x['op'])
        helpers = ['capacity'] + ['op_' + str(i) for i in range(4)]
        for name in helpers:
            actual = self.func[name]
            require(len(actual) == (3 if name == 'capacity' else 24), 'Exact helper length')
            require(b''.join(x['blob'] for x in actual) == original_helpers[name], 'Original helper exact bytes ' + name)
            if name != 'capacity':
                csr = [(x['op'], x['args']) for x in actual if x['op'].startswith('csr')]
                require(csr == [('csrw', 'vstart,a6'), ('csrr', 't4,vxrm'), ('csrr', 't5,vxsat'),
                                ('csrw', 'vxrm,t2'), ('csrw', 'vxsat,t2'), ('csrr', 'a0,vstart'),
                                ('csrr', 't1,vxsat'), ('csrw', 'vxrm,t4'), ('csrw', 'vxsat,t5')], 'Original CSR ordering including saves/restores')
        vector = [x for x in self.code.values() if x['op'].startswith('v')]
        require(all(x['function'] in helpers for x in vector) and len(vector) == 37, 'No extra vector instructions')
        self.helper_names = {self.s[n]: n for n in helpers}
        self.names = {v: k for k, v in self.s.items() if k in self.func}
        self.reg = {'zero': 0}
        self.opaque = {}
        self.visits = collections.Counter()
        self.terms = collections.Counter()
        self.events = collections.Counter()
        self.event_pcs = collections.defaultdict(collections.Counter)
        self.branches = collections.defaultdict(collections.Counter)
        self.calls = collections.Counter()
        self.args = []
        self.text = bytearray()
        self.source_events = [(seed['seed'], *w) for seed in model['seeds'] for w in seed['writes']]
        self.source_index = 0
        self.mask_events = []
        for row in model['calls'][::32]:
            self.mask_events.extend((8, i * 8, 0) for i in range(16))
            self.mask_events.extend((1, off, val) for off, val in model['masks'][row['mode']]['writes'])
        self.mask_index = 0
        self.call_index = 0
        self.init_index = 0
        self.read_index = 0
        self.min_sp = self.s['__stack_top']
        self.pc = self.s['_start']
        self.steps = 0
        self.exit = None
        self.main_return = None
        self.csr = {'vstart': 0, 'vxrm': 'entry:vxrm', 'vxsat': 'entry:vxsat'}
        self.table_audit()

    def table_audit(self):
        for r in self.model['calls']:
            i = r['ordinal'] - 1
            ri = self.load(self.s['fixed_expected_index'] + i * 2, 2, observe=False)
            require(ri == r['row'], 'Actual linked row index')
            require(self.load(self.s['fixed_expected_sat'] + i, 1, observe=False) == r['expected_sat'], 'Actual linked saturation')
            ids = [self.load(self.s['fixed_expected_rows'] + ri * 18 + j * 2, 2, observe=False) for j in range(9)]
            require(ids == r['block_ids'], 'Actual linked block IDs')
            gold = b''.join(bytes(self.mem[self.s['fixed_expected_blocks'] - BASE + j * 64:self.s['fixed_expected_blocks'] - BASE + (j + 1) * 64]) for j in ids)[:514]
            require(gold.hex() == r['expected_hex'], 'Linked expected bytes equal Host-validated generated oracle')

    def value(self, r):
        require(r in self.reg and type(self.reg[r]) is int, 'Unknown CFG value ' + r + ' at ' + hex(self.pc))
        return self.reg[r]

    def set(self, r, v):
        if r != 'zero':
            self.reg[r] = v & MASK if type(v) is int else v
        if r == 'sp':
            self.min_sp = min(self.min_sp, self.value('sp'))
            require(self.s['__stack_top'] - 65536 <= self.value('sp') <= self.s['__stack_top'], '64 KiB stack bound')

    def address(self, expr):
        m = re.fullmatch(r'(-?\d+)?\((\w+)\)', expr)
        require(m is not None, 'Actual linked address grammar ' + expr)
        return (self.value(m[2]) + int(m[1] or 0)) & MASK

    def event(self, name):
        self.events[name] += 1
        self.event_pcs[name][hex(self.pc)] += 1

    def load(self, a, n, observe=True):
        if (a, n) in self.opaque:
            if observe:
                self.event('opaque_caller_restore')
                self.event('stack_loads')
            return self.opaque[(a, n)]
        off = a - BASE
        require(0 <= off and off + n <= SIZE and all(self.known[off:off + n]), 'Known bounded scalar load ' + hex(a) + ' pc=' + hex(self.pc))
        v = int.from_bytes(self.mem[off:off + n], 'little')
        if observe:
            if self.s['out'] <= a < self.s['out'] + 1026:
                require(self.code[self.pc]['function'] == 'fixed_full_main', 'Output load belongs to positive comparator')
                require(self.call_index > 0 and self.init_index == 0 and self.read_index < 65, 'Exactly 65 post-helper reads')
                j = self.read_index
                require(a == self.s['out'] + (8 * j if j < 64 else 512) and n == (8 if j < 64 else 2), 'Exact 514-byte output read sequence')
                expected = bytes.fromhex(self.model['calls'][self.call_index - 1]['expected_hex'])
                require(v == int.from_bytes(expected[a - self.s['out']:a - self.s['out'] + n], 'little'), 'Positive comparator data hypothesis')
                self.read_index += 1
                self.event('actual_output_reads')
            elif self.s['__stack_top'] - 65536 <= a <= self.s['__stack_top']:
                self.event('stack_loads')
            else:
                for key in ('fixed_expected_index', 'fixed_expected_rows', 'fixed_expected_blocks', 'fixed_expected_sat'):
                    if self.s[key] <= a < self.s[key] + self.sizes[key]:
                        self.event(key + '_reads')
                        break
        return v

    def store(self, a, n, v, observe=True):
        f = self.code[self.pc]['function']
        if a == 0xc0000000:
            require(self.backend == 'soc' and n == 1 and f in ('replay_write', 'replay_text'), 'Only bounded UART writes')
            self.text.append(v & 255)
            self.event('UART_SB')
            return
        if a == 0xd0000000 or self.backend == 'spike' and a == self.s['tohost']:
            require(f == 'replay_exit' and n == 8 and self.main_return == 0, 'Actual finite successful endpoint')
            require(v == (1 if self.backend == 'spike' else 0), 'Actual completion payload: HTIF1 versus raw CTRL0')
            self.exit = dict(pc=hex(self.pc), address=hex(a), bytes=n, value=v)
        off = a - BASE
        if self.exit and a == 0xd0000000:
            return
        require(0 <= off and off + n <= SIZE and not any(self.readonly[off:off + n]), 'Writable scalar store range ' + hex(a))
        if type(v) is not int:
            require(n == 8 and self.s['__stack_top'] - 65536 <= a < self.s['__stack_top'] and str(v).startswith('caller:'), 'Opaque values only in caller-save slots')
            self.opaque[(a, n)] = v
            self.event('opaque_caller_save')
            self.event('stack_stores')
            return
        for oa, size in list(self.opaque):
            if a < oa + size and oa < a + n:
                del self.opaque[(oa, size)]
        self.mem[off:off + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')
        self.known[off:off + n] = b'\1' * n
        if not observe:
            return
        if f == '_start':
            require(self.s['__bss_start'] <= a < self.s['__bss_end'] and n == 8 and v == 0, 'Actual startup BSS initialization')
            self.event('BSS_SD')
        elif f == 'fixed_full_main':
            bank = next((b for b in ('a', 'b') if self.s[b] <= a < self.s[b] + 1024), None)
            if bank:
                require(self.source_index < len(self.source_events) and n == 1, 'Source write count/width')
                seed, wantbank, offset, expected = self.source_events[self.source_index]
                require((bank, a - self.s[bank], v & 255) == (wantbank, offset, expected), 'All ordered original RNG/override source writes')
                require(self.call_index == seed * 3584, 'Source writes at correct seed boundary')
                self.source_index += 1
                self.event('source_SB')
            elif self.s['mask'] <= a < self.s['mask'] + 128:
                require(self.mask_index < len(self.mask_events), 'No extra mask writes')
                require((n, a - self.s['mask'], v & ((1 << (8 * n)) - 1)) == self.mask_events[self.mask_index], 'Exact clear/ordered cumulative mask stores')
                require(self.call_index % 32 == 0, 'Mask epoch before 32 original calls')
                self.mask_index += 1
                self.event('mask_clear_SD' if n == 8 else 'mask_selected_SB')
            elif self.s['out'] <= a < self.s['out'] + 1026:
                require(self.call_index < 10752, 'No output initialization after last call')
                if self.init_index == 0:
                    require(self.read_index == (65 if self.call_index else 0), 'Previous full output read completed')
                    self.read_index = 0
                j = self.init_index
                require(j < 65 and a == self.s['out'] + (j * 8 if j < 64 else 512) and n == (8 if j < 64 else 2), 'Exact 64SD plus tailSH initialization')
                require(v & ((1 << (8 * n)) - 1) == int.from_bytes(b'\x5b' * n, 'little'), 'Original sentinel bytes')
                self.init_index += 1
                self.event('fresh_output_stores')
        if self.s['__stack_top'] - 65536 <= a < self.s['__stack_top']:
            self.event('stack_stores')

    def helper(self, name):
        if name == 'capacity':
            require(self.calls[name] == 1, 'Capacity exactly once')
            self.set('t0', MASK)
            self.set('a0', 512)
        else:
            require(self.call_index < 10752 and self.init_index == 65, 'One complete initializer per helper')
            r = self.model['calls'][self.call_index]
            args = [self.s['a'], self.s['b'], self.s['out'] + 1, r['vl'], 512, self.s['mask'], r['start'], r['control']]
            require(name == 'op_' + str(r['op']) and [self.value('a' + str(i)) for i in range(8)] == args, 'Exact complete original argument/order contract')
            require(self.source_index == 1472 * (r['seed'] + 1), 'Full current seed fresh writes before helpers')
            for bank in ('a', 'b'):
                off = self.s[bank] - BASE
                require(bytes(self.mem[off:off + 512]).hex() == self.model['seeds'][r['seed']][bank + '_hex'], 'Original seed content')
                require(not any(self.mem[off + 512:off + 1024]), 'Original backing tail preserved')
            off = self.s['mask'] - BASE
            require(bytes(self.mem[off:off + 128]).hex() == self.model['masks'][r['mode']]['hex'], 'Full physical mask128')
            expected_epoch_count = sum(16 + len(self.model['masks'][x['mode']]['writes']) for x in self.model['calls'][:self.call_index + 1:32])
            require(self.mask_index == expected_epoch_count, 'Exactly one complete mask epoch per source group')
            self.args.append(dict(ordinal=r['ordinal'], pc=hex(self.pc), helper=name, arguments=args,
                                  seed=r['seed'], mode=r['mode'], expected_sat=r['expected_sat']))
            gold = bytes.fromhex(r['expected_hex'])
            require(len(gold) == 514 and gold[0] == gold[-1] == 0x5b, 'Full footprint/guards')
            # Hypothetical successful vector writeback changes only 512 result bytes.
            off = self.s['out'] + 1 - BASE
            self.mem[off:off + 512] = gold[1:513]
            self.known[off:off + 512] = b'\1' * 512
            self.set('a0', r['expected_sat'] << 32)
            self.set('t0', 512)
            self.set('t1', r['expected_sat'] << 32)
            self.set('t2', r['control'] >> 2)
            self.set('t3', 7)
            self.set('t4', self.csr['vxrm'])
            self.set('t5', self.csr['vxsat'])
            self.csr['vstart'] = 0
            self.call_index += 1
            self.init_index = 0
            self.event('helper_calls')
        for x in self.func[name]:
            self.visits[x['pc']] += 1
            self.terms[name] += 1
            self.steps += 1

    def walk(self):
        while self.exit is None:
            require(self.steps < 12000000 and self.pc in self.code, 'Finite complete CFG bound')
            x = self.code[self.pc]
            op, p, f = x['op'], x['p'], x['function']
            require(f in POSITIVE, 'No error/fallback/unused function on positive path: ' + f)
            self.steps += 1
            self.visits[self.pc] += 1
            self.terms[f] += 1
            nxt = self.pc + len(x['blob'])
            if op in ('ld', 'lw', 'lwu', 'lhu', 'lbu'):
                n = {'ld': 8, 'lw': 4, 'lwu': 4, 'lhu': 2, 'lbu': 1}[op]
                v = self.load(self.address(p[1]), n)
                self.set(p[0], signed(v, 32) if op == 'lw' else v)
            elif op in ('sd', 'sw', 'sh', 'sb'):
                if p[0] not in self.reg:
                    require(re.fullmatch(r's\d+', p[0]) is not None, 'Only unknown callee-save registers may be saved')
                    self.reg[p[0]] = 'caller:' + p[0]
                self.store(self.address(p[1]), {'sd': 8, 'sw': 4, 'sh': 2, 'sb': 1}[op], self.reg[p[0]])
            elif op in ('jal', 'jalr'):
                dest = int(p[-1].split()[0], 16) if op == 'jal' else self.value(p[-1])
                require(dest in self.names, 'Resolved actual linked call')
                self.set('ra', nxt)
                name = self.names[dest]
                self.calls[name] += 1
                if dest in self.helper_names:
                    self.helper(name)
                else:
                    nxt = dest
            elif op == 'ret':
                if f == 'main':
                    self.main_return = self.value('a0')
                    require(self.main_return == 0, 'Source positive return zero')
                nxt = self.value('ra')
            elif op == 'j':
                nxt = int(p[0].split()[0], 16)
            elif op in ('beq', 'bne', 'bltu', 'bgeu', 'beqz', 'bnez', 'bltz'):
                a = self.value(p[0])
                b = 0 if op in ('beqz', 'bnez', 'bltz') else self.value(p[1])
                taken = (a == b) if op in ('beq', 'beqz') else (a != b) if op in ('bne', 'bnez') else a < b if op == 'bltu' else a >= b if op == 'bgeu' else signed(a, 64) < 0
                self.branches[hex(self.pc)]['taken' if taken else 'fallthrough'] += 1
                if taken:
                    nxt = int(p[-1].split()[0], 16)
            elif op == 'li':
                self.set(p[0], int(p[1], 0))
            elif op in ('lui', 'auipc'):
                self.set(p[0], signed(int(p[1], 0) << 12, 32) + (self.pc if op == 'auipc' else 0))
            elif op == 'mv':
                require(p[1] in self.reg, 'Known or explicitly opaque move')
                self.set(p[0], self.reg[p[1]])
            elif op in ('sext.w', 'snez'):
                self.set(p[0], signed(self.value(p[1]), 32) if op == 'sext.w' else int(self.value(p[1]) != 0))
            elif op in ('addi', 'addiw', 'slli', 'srli', 'srliw', 'andi', 'ori'):
                v, i = self.value(p[1]), int(p[2], 0)
                z = v + i if op in ('addi', 'addiw') else v << i if op == 'slli' else v >> i if op == 'srli' else (v & 0xffffffff) >> i if op == 'srliw' else v & i if op == 'andi' else v | i
                self.set(p[0], signed(z, 32) if op in ('addiw', 'srliw') else z)
            elif op in ('add', 'xor', 'or', 'mul', 'remu', 'divu'):
                a, b = self.value(p[1]), self.value(p[2])
                require(op not in ('remu', 'divu') or b != 0, 'Finite scalar decimal division')
                z = a + b if op == 'add' else a ^ b if op == 'xor' else a | b if op == 'or' else a * b if op == 'mul' else a % b if op == 'remu' else a // b
                self.set(p[0], z)
            elif op == 'csrr':
                require(p[1] == 'vlenb' and f == 'fixed_full_main', 'Only explicit profile scalar CSR read')
                self.set(p[0], 128)
                self.event('vlenb_read')
            elif op in ('csrw', 'csrwi', 'csrs'):
                require(f == '_start' and p[0] in ('mie', 'mtvec', 'mstatus', 'fcsr', 'vstart'), 'Only existing startup CSR writes')
                if op != 'csrs':
                    self.csr[p[0]] = int(p[1], 0) if op == 'csrwi' else self.value(p[1])
            elif op == 'fence':
                require(f == 'replay_exit', 'No new fence')
            else:
                raise ValueError('Unsupported actual opcode ' + op + ' at ' + hex(self.pc))
            self.pc = nxt
            if self.call_index and self.call_index % 3584 == 0 and x['op'] == 'jalr':
                print(self.backend, 'completed helper calls', self.call_index, 'charged instructions', self.steps, flush=True)
        return self.finish()

    def finish(self):
        require((self.call_index, self.read_index, self.init_index) == (10752, 65, 0), 'Complete full source history/read completion')
        require((self.source_index, self.mask_index) == (len(self.source_events), len(self.mask_events)), 'All source/mask writes')
        for k in ('source_SB', 'mask_clear_SD', 'mask_selected_SB', 'actual_output_reads', 'fresh_output_stores'):
            require(self.events[k] == self.model['counts'][k], 'Exact final event count ' + k)
        require([self.load(self.s[n], 8, observe=False) for n in ('checks', 'elements', 'errors')] == [10752, 5505024, 0], 'Complete scalar counters')
        require(self.calls['capacity'] == 1 and all(self.calls['op_' + str(i)] == 2688 for i in range(4)), 'All four original helper calls')
        if self.backend == 'spike':
            n = self.load(self.s['replay_log_count'], 8, observe=False)
            require(n < 8191, 'No truncated bounded logging')
            off = self.s['replay_log'] - BASE
            self.text = self.mem[off:off + n]
        text = bytes(self.text).decode('ascii')
        boundaries = re.findall(r'RVV_TRIAL seed=(\d+) vl=(\d+) mask=(\d+) vstart=(\d+) completed=(\d+)\n', text)
        want = [tuple(r[k] for k in ('seed', 'vl', 'mode', 'start', 'completed')) for r in self.model['boundaries']]
        require([tuple(map(int, row)) for row in boundaries] == want, 'All28 original boundary prints')
        require('RVV_MATRIX_PASS sew=8 vlmax=512 cases=10752 elements=5505024 errors=0 seeds=3 guard_tail_mask_vstart=checked\n' in text and 'BOARD_REPLAY_PASS' in text, 'Full finite success text')
        require('FAIL' not in text and 'MISMATCH' not in text and 'TRAP' not in text, 'Positive text veto')
        require(self.s['__bss_end'] < self.s['__stack_top'] - 65536, 'Actual map keeps 64KiB stack')
        require(sum(self.visits.values()) == sum(self.terms.values()) == self.steps, 'Every charged instruction belongs to actual PC/function')
        result = dict(backend=self.backend, status='COMPLETE_CONDITIONAL_POSITIVE_CFG_NOT_REFERENCE',
                      linked_positive_instruction_count=self.steps, terms=dict(self.terms), calls=dict(self.calls),
                      events=dict(self.events), helper_dynamic_instructions=24 * 10752, capacity_instructions=3,
                      original_static_helper_instructions=99, original_call_count=10752,
                      all_arguments_verified=True, all_original_boundary_prints=28,
                      text_bytes=len(self.text), actual_min_sp=hex(self.min_sp), stack_highwater_bytes=self.s['__stack_top'] - self.min_sp,
                      bss_end=hex(self.s['__bss_end']), reserved_stack_bytes=65536, image_ram_bytes=self.s['__bss_end'] - BASE,
                      finite_exit=self.exit, original_CSR_instructions_per_call=9,
                      original_rounding_saturation_save_restore_instructions_per_call=4,
                      assumptions=['capacity=512 and VLENB=128', 'all original vector helpers return source-correct result, vstart0 and expected saturation',
                                   'no asynchronous trap; no device polling exists in linked runtime'],
                      conditional_count_not_Spike_or_DUT=True, no_error_fallback_on_success=True)
        save(OUT / (self.backend + '_cfg.json'), result)
        save(OUT / (self.backend + '_PC_visits.json'), {hex(k): v for k, v in sorted(self.visits.items())})
        save(OUT / (self.backend + '_branches.json'), self.branches)
        save(OUT / (self.backend + '_event_PCs.json'), self.event_pcs)
        save(OUT / (self.backend + '_all10752_arguments.json'), self.args)
        (OUT / (self.backend + '_conditional_stdout.txt')).write_text(text)
        return result


def main():
    OUT.mkdir(exist_ok=False)
    pins = read(BUILD / 'inputs_before.json')
    require(pins == read(BUILD / 'inputs_after.json'), 'Compile pre/post input identity')
    generated = read(GEN / 'GENERATED.json')
    for d in (generated['input_pins'], generated['artifacts']):
        pins.update(d)
    for p in [Path(__file__), HERE / 'run_cfg_once.py', BUILD / 'COMPILED.json', BUILD / 'inputs_before.json', BUILD / 'inputs_after.json',
              OLD / 'soc/fixed_e8_m4_prefix777.dis', OLD / 'soc/fixed_e8_m4_prefix777.elf', ROOT / 'source_review01/HOST_TERMINAL_REVIEW01.json']:
        pins[str(p)] = sha(p)
    for p in BUILD.rglob('*'):
        if p.is_file():
            pins[str(p)] = sha(p)
    for p, h in pins.items():
        require(sha(p) == h, 'Input pin changed ' + p)
    save(OUT / 'inputs_before.json', pins)
    compile_status = read(BUILD / 'COMPILED.json')
    for b in ('soc', 'spike'):
        v = compile_status['backends'][b]
        require(type(v['actual_compile_wait']['actual_wait_exit']) is int and v['actual_compile_wait']['actual_wait_exit'] == 0 and not v['actual_compile_wait']['timed_out'], 'Actual bounded compile0')
        require(sha(BUILD / b / 'program.elf') == v['elf_sha256'], 'Compiled ELF hash')
    oldcode, oldfunc = parse_dis(OLD / 'soc/fixed_e8_m4_prefix777.dis')
    oldsegments = elf(OLD / 'soc/fixed_e8_m4_prefix777.elf')
    names = ['capacity'] + ['op_' + str(i) for i in range(4)]
    original_helpers = {}
    for n in names:
        require(len(oldfunc[n]) == (3 if n == 'capacity' else 24), 'Old named helper window count')
        for x in oldfunc[n]:
            require(any(s['flags'] & 1 and s['va'] <= x['pc'] and x['pc'] + len(x['blob']) <= s['va'] + len(s['data']) and s['data'][x['pc'] - s['va']:x['pc'] - s['va'] + len(x['blob'])] == x['blob'] for s in oldsegments), 'Named original-source port code bound')
        original_helpers[n] = b''.join(x['blob'] for x in oldfunc[n])
    whole = b''.join(original_helpers.values())
    locations = []
    for seg in elf(ORIGINAL):
        if seg['flags'] & 1:
            start = 0
            while True:
                at = seg['data'].find(whole, start)
                if at < 0:
                    break
                locations.append(seg['va'] + at)
                start = at + 1
    require(len(locations) == 1 and locations[0] % 2 == 0, 'Unique contiguous99 helper instructions in original executable segment')
    save(OUT / 'original_helper_identity.json', dict(original_elf=str(ORIGINAL), original_elf_sha256=sha(ORIGINAL), original_start=hex(locations[0]),
         bytes=len(whole), sha256=hashlib.sha256(whole).hexdigest(), static_instructions=99,
         windows={n:dict(instructions=len(oldfunc[n]), bytes=len(v), sha256=hashlib.sha256(v).hexdigest()) for n,v in original_helpers.items()}))
    model = read(GEN / 'model.json')
    machines = [CFG(b, model, original_helpers) for b in ('soc', 'spike')]
    save(OUT / 'preflight.json', dict(status='ACTUAL_ASM_COVERED', supported_scalar_opcodes=sorted(SUPPORTED),
                                    helper_summary_names=names, capacity=512, VLENB=128,
                                    full_scope=model['counts'], no_implicit_unknown_opcode_or_branch=True))
    print('Both linked images preflight passed; starting bounded scalar CFG accounting', flush=True)
    results = {m.backend: m.walk() for m in machines}
    require(bytes(machines[0].text) == bytes(machines[1].text), 'Both backend positive text identical')
    for p, h in pins.items():
        require(sha(p) == h, 'Post-audit input pin drift ' + p)
    save(OUT / 'inputs_after.json', pins)
    over = results['spike']['linked_positive_instruction_count'] > 3000000
    save(OUT / 'complete.json', dict(status='HOLD_LINKED_POSITIVE_CFG_OVER_3M' if over else 'LINKED_POSITIVE_CFG_UNDER_3M_PENDING_INDEPENDENT_REVIEW',
         backends={b: r['linked_positive_instruction_count'] for b,r in results.items()},
         firmware_gate=3000000, complete_full10752=True, inputs_unchanged=True, input_pins=len(pins),
         reference_executed=False, DUT_executed=False,
         evidence={str(p):sha(p) for p in OUT.iterdir() if p.is_file()}))
    print(json.dumps(dict(status='HOLD' if over else 'COST_UNDER_3M', counts={b:r['linked_positive_instruction_count'] for b,r in results.items()})), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if OUT.is_dir() and not (OUT / 'FIRST_FAILURE.json').exists():
            save(OUT / 'FIRST_FAILURE.json', dict(status='AUDITOR_FAILED_NOT_COST_RESULT', error=repr(exc), traceback=traceback.format_exc()))
        raise
