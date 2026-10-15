"""Exact whole-register pair RVFI oracle; source-derived, no DUT launch."""
import csv
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
from scoped_rv64c_memory import decode as compressed

FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
MASK = (1 << 64) - 1
COMMIT = re.compile(r'^core\s+0:\s+[0-3]\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def memory(insn, regs):
    if insn & 3 != 3:
        d = compressed(insn)
        if d is None:
            return None
        return d['kind'], (regs[d['base']] + d['offset']) & MASK, d['size'], d['register']
    op = insn & 127
    if op not in (3, 0x23):
        return None
    read = op == 3
    imm = insn >> 20 if read else (insn >> 25 << 5) | ((insn >> 7) & 31)
    if imm & 2048:
        imm -= 4096
    return ('read' if read else 'write', (regs[(insn >> 15) & 31] + imm) & MASK,
            1 << ((insn >> 12) & 3), (insn >> (7 if read else 20)) & 31)


def instruction_map(disassembly):
    return {int(pc, 16): int(insn, 16) for pc, insn in
            re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+', disassembly, re.M)}


class Checker:
    def __init__(self, case, symbols, targets, disassembly, spike=False):
        self.case, self.s, self.targets = case, symbols, targets
        self.code = instruction_map(disassembly)
        self.spike = spike
        self.regs = [0] * 32
        self.entries = {symbols[f'op_{op}']: op for op in range(20)}
        self.target_pcs = {v['pc']: int(k) for k, v in targets.items()}
        self.calls = []
        self.input_setup, self.output_setup = {}, {}
        self.reads, self.preloads, self.stores, self.csrs = [0, 0], [0, 0], [0, 0], [[], []]
        self.target_order, self.numbers, self.exits, self.control = [], [], [], []
        self.returned = [False, False]
        self.vtype = None
        self.inherited = []
        self.cycle = self.order = -1
        self.rows = 0
        self.last_pc = None

    def wanted(self, c, i):
        active = 32 + c['start'] * c['bytes'] <= i < 32 + c['registers'] * 128
        return ((i - 32) * 37 + c['seed'] * 71 + 3) & 255 if active else 0x5b

    def row(self, row):
        require(set(row) == set(FIELDS) and None not in row.values(), 'Malformed/truncated CSV')
        self.rows += 1
        cycle = int(row['cycle'])
        require(cycle >= self.cycle, 'Cycle regression')
        self.cycle = cycle
        if row['event'] != 'retire':
            return
        order = int(row['order'])
        require(order == self.order + 1, 'Retirement gap/duplicate')
        self.order = order
        pc, insn, rd, value = int(row['pc'], 16), int(row['insn'], 16), int(row['rd']), int(row['rd_wdata'], 16)
        self.last_pc = pc
        require(int(row['trap']) == 0 and pc not in (self.s['trap_entry'], self.s.get('replay_mismatch', -1)), 'Trap/mismatch')
        require(self.code.get(pc) == insn, 'Instruction differs from accepted ELF')
        if pc in self.entries:
            n = len(self.calls)
            require(n < 2, 'Extra operation call')
            if n:
                require(self.reads[n-1] == 1088 and self.returned[n-1], 'Next call before full prior oracle')
                require(self.vtype == self.case['expected_second_entry_vtype'], 'Lost predecessor vtype')
            c = self.case['calls'][n]
            require(self.entries[pc] == c['op'], 'Wrong predecessor/successor')
            require(self.regs[10:14] == [self.s['input'], self.s['output']+32, c['start'], c['mode']], 'Call arguments differ')
            require(self.input_setup == {i: (i*37+c['seed']*71+3)&255 for i in range(1024)}, 'Input initialization differs')
            require(self.output_setup == {i: 0x5b for i in range(1088)}, 'Old destination initialization differs')
            self.input_setup.clear()
            self.output_setup.clear()
            self.calls.append(c)
            self.inherited.append(self.vtype)
        n = len(self.calls) - 1
        c = self.calls[n] if n >= 0 else None
        if insn & 127 == 0x57 and (insn >> 12) & 7 == 7:
            if insn >> 25 == 0x40:
                vt = self.regs[(insn >> 20) & 31]
            else:
                vt = (insn >> 20) & (0x3ff if insn >> 30 == 3 else 0x7ff)
            require(vt in (0, 9, 18, 24, 1 << 63), 'Unexpected vtype configuration')
            self.vtype = vt
        if pc in self.target_pcs:
            require(c is not None and len(self.target_order) == n and self.preloads[n] == 2, 'Target out of order')
            target = self.targets[str(c['op'])]
            require(pc == target['pc'] and insn == target['opcode'], 'Wrong target opcode/order')
            require(self.csrs[n] == [c['start']], 'Missing exact initial vstart read')
            require(self.regs[12] == c['start'], 'Wrong target vstart argument')
            self.target_order.append(c['op'])
        if insn & 127 == 7:
            require(c is not None, 'Vector load outside operation')
            if pc not in self.target_pcs:
                index = self.preloads[n]
                require(index < 2 and pc == self.s[f"op_{c['op']}"] + 4 + index*4,
                        'Unexpected whole preload')
                require(self.regs[(insn >> 15) & 31] == (self.s['input'] if index == 0 else self.s['output']+32),
                        'Whole preload address differs')
                self.preloads[n] += 1
        if insn & 127 == 0x27:
            require(c is not None and len(self.target_order) == n+1 and self.csrs[n] == [c['start'], 0],
                    'Output whole store precedes target/completion')
            require(self.stores[n] == 0 and (insn >> 29)+1 == c['registers'] and
                    self.regs[(insn >> 15) & 31] == self.s['output']+32, 'Whole output store differs')
            self.stores[n] += 1
        if insn & 127 == 0x73 and (insn >> 12) & 7 == 2 and (insn >> 15) & 31 == 0:
            csr = insn >> 20
            if csr == 8 and rd:
                require(c is not None and pc in (self.targets[str(c['op'])]['pc']-4,
                                               self.targets[str(c['op'])]['pc']+4), 'Unexpected vstart read')
                expected = c['start'] if not self.csrs[n] else 0
                require(len(self.csrs[n]) < 2 and value == expected, 'vstart readback differs')
                self.csrs[n].append(value)
            if csr == 0xc22 and rd:
                require(value == 128, 'VLENB differs')
        if c is not None and self.s[f"op_{c['op']}"] <= pc < self.s[f"op_{c['op']}"]+100 and insn == 0x8082:
            require(self.stores[n] == 1 and self.csrs[n] == [c['start'], 0] and
                    self.regs[10] == c['start'] << 32, 'Original returned status differs')
            require(not self.returned[n], 'Duplicate operation return')
            self.returned[n] = True
        if pc == self.s['num']:
            self.numbers.append(self.regs[10])
        if pc == self.s['replay_exit']:
            require(self.regs[10] == 0, 'Nonzero raw exit')
            self.exits.append(self.regs[10])
        access = memory(insn, self.regs)
        if access:
            kind, addr, width, register = access
            require(addr == int(row['mem_addr'], 16), 'Scalar effective address differs')
            require(int(row['mem_rmask' if kind == 'read' else 'mem_wmask'], 16) == ((1 << width)-1) << (addr%8),
                    'Scalar mask differs')
            require(addr%8+width <= 8, 'Scalar crossing unsupported')
            v = int(row['rd_wdata'] if kind == 'read' else row['mem_wdata'], 16) & ((1 << (8*width))-1)
            require((rd == register if kind == 'read' else v == self.regs[register] & ((1 << (8*width))-1)),
                    'Scalar register/value mismatch')
            if kind == 'write':
                if width == 1:
                    for name, size, state in (('input', 1024, self.input_setup), ('output', 1088, self.output_setup)):
                        if self.s[name] <= addr < self.s[name]+size:
                            require(c is None or (self.reads[n] == 1088 and self.returned[n]), 'Setup overwrites live result')
                            offset = addr-self.s[name]
                            require(offset not in state, 'Repeated setup byte')
                            state[offset] = v
                if addr == (self.s['tohost'] if self.spike else 0xd0000000):
                    require(width == 8 and v == (1 if self.spike else 0), 'Nonzero CTRL/HTIF exit')
                    self.control.append(v)
            elif self.s['output'] <= addr < self.s['output']+1088:
                require(c is not None and self.returned[n] and self.stores[n] == 1 and width == 1,
                        'Output read before target return')
                i = addr-self.s['output']
                require(i == self.reads[n], 'Full output oracle order/count differs')
                require(v == self.wanted(c, i), f'pair{self.case["pair"]} call{n} byte{i}: got {v:#x}, expected {self.wanted(c,i):#x}')
                self.reads[n] += 1
        if rd:
            self.regs[rd] = value
        self.regs[0] = 0

    def finish(self):
        require(self.calls == self.case['calls'] and self.target_order == [c['op'] for c in self.calls], 'Incomplete pair')
        require(self.reads == [1088, 1088] and self.preloads == [2, 2] and self.stores == [1, 1] and all(self.returned),
                'Incomplete setup/target/full oracle')
        require(self.numbers == [2, len(self.case['skips']), 0], 'Original case/skip/error counters differ')
        require(self.exits == [0] and self.control == ([1] if self.spike else [0]), 'Missing raw/CTRL exit')
        return dict(status='PAIR_FULL_CSV_ORACLE_PASS', pair=self.case['pair'], calls=self.calls,
                    target_order=self.target_order, output_byte_checks=self.reads, preloads=self.preloads,
                    stores=self.stores, vstart_reads=self.csrs, inherited_vtypes=self.inherited,
                    numbers=self.numbers, raw_exit=self.exits, control=self.control, rows=self.rows,
                    retired=self.order+1, last_cycle=self.cycle, last_pc=hex(self.last_pc))


def analyze(path, checker, guard=lambda: None):
    with Path(path).open() as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == FIELDS, 'CSV header differs')
        for n, row in enumerate(reader):
            if n % 1024 == 0:
                guard()
            checker.row(row)
    guard()
    result = checker.finish()
    guard()
    return result


def spike_rows(path, checker):
    """Convert existing Spike commits to RVFI-shaped rows; no ISA execution."""
    order = 0
    for line in Path(path).open():
        m = COMMIT.match(line)
        if not m:
            continue
        pc, insn, tail = int(m[1], 16), int(m[2], 16), m[3]
        updates = [(int(r), int(v, 16)) for r, v in re.findall(r'\bx\s*([0-9]+)\s+0x([0-9a-f]+)', tail)]
        if pc < 0x80000000:
            for r, v in updates:
                checker.regs[r] = v
            continue
        require(len(updates) <= 1, 'Multiple scalar destinations')
        rd, value = updates[0] if updates else (0, 0)
        row = dict.fromkeys(FIELDS, '0')
        row.update(cycle=str(order), order=str(order), event='retire', pc=f'{pc:016x}', insn=f'{insn:08x}',
                   rd=str(rd), rd_wdata=f'{value:016x}')
        access = memory(insn, checker.regs)
        if access:
            kind, addr, width, register = access
            addresses = re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?', tail)
            require(len(addresses) == 1 and int(addresses[0][0], 16) == addr, 'Spike scalar memory evidence differs')
            row['mem_addr'] = f'{addr:016x}'
            row['mem_rmask' if kind == 'read' else 'mem_wmask'] = f'{((1 << width)-1) << (addr%8):02x}'
            if kind == 'write':
                require(addresses[0][1] != '', 'Missing Spike store value')
                row['mem_wdata'] = addresses[0][1]
        yield row
        order += 1
        if checker.control:
            return
