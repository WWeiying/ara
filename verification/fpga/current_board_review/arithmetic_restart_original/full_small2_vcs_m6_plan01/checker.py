"""Full original small2 RVFI oracle. No Spike-only log or HTIF assumptions."""
import csv
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'full_small2_prepare01'
G = HERE.parents[1]
sys.path.insert(0, str(G / 'gather_repair05'))
import regression as common
sys.path.insert(0, str(G.parents[1] / 'coverage'))
from scoped_rv64c_memory import decode as compressed_memory

read, require = common.read, common.require
def sha(path):
    return common.sha(Path(path))
READY_SHA = 'db878aa262c882af8cf32dfa803426382b3869c1a0f47662c4a434bd8b6439b6'
SHAPES = ('rvv_matrix_e8_mf8', 'rvv_matrix_e32_mf2')
ELFS = ('181e24f087437f76519128e3a5cfab0e931b1d2df643fce41035d6bfd618f55b',
        '54931771b1ba6ade43ae776af14f52163323670ec8881dc2fc1f70fe1c6c994f')
MASK64 = (1 << 64) - 1
VETO = re.compile(common.BAD.pattern + r'|\bRVV_MATRIX_DETAIL\b|\b(?:FAIL|FAILED|TRAP|MISMATCH|UNSUPPORTED|ABORTED)\b', re.I)


def marker(p):
    return (f"RVV_MATRIX_PASS sew={p['sew']} vlmax=16 cases={p['calls']} "
            f"elements={16*p['calls']} errors=0 seeds=3 guard_tail_mask_vstart=checked")


def is_vector(insn):
    return insn & 127 == 0x57 or (insn & 127 in (7, 39) and (insn >> 12) & 7 in (0, 5, 6, 7))


def is_csr(insn):
    return insn & 127 == 0x73 and (insn >> 12) & 7 != 0


def memory_op(insn):
    if insn & 3 != 3:
        d = compressed_memory(insn)
        return dict(d, signed=d['kind'] == 'read' and d['size'] == 4) if d else None
    opcode, f = insn & 127, (insn >> 12) & 7
    if opcode not in (3, 35):
        return None
    require(f in ((0, 1, 2, 3, 4, 5, 6) if opcode == 3 else (0, 1, 2, 3)), 'Illegal scalar memory width')
    imm = insn >> 20 if opcode == 3 else ((insn >> 25) << 5) | ((insn >> 7) & 31)
    if imm & 2048:
        imm -= 4096
    return dict(kind='read' if opcode == 3 else 'write', size=1 << (f & 3),
                base=(insn >> 15) & 31, register=(insn >> (7 if opcode == 3 else 20)) & 31,
                offset=imm, signed=opcode == 3 and f < 4)


def loaded_value(bits, size, signed):
    bits &= (1 << (8 * size)) - 1
    if signed and bits & (1 << (8 * size - 1)):
        bits -= 1 << (8 * size)
    return bits & MASK64


def specification(shape):
    require(shape in SHAPES and sha(REF / 'READY.json') == READY_SHA, 'Reference identity drift')
    proof = read(REF / shape / 'sourceproof.json')
    spec = proof['backends']['soc']
    require(spec['sha256'] == ELFS[SHAPES.index(shape)] and sha(spec['elf']) == spec['sha256'], 'Same SoC ELF required')
    require(proof['full_order_preserved'] and not proof['partitioned'] and
            spec['all_helper_instructions_equal_original'], 'Original continuous helper proof')
    code = {int(k): v for k, v in spec['code'].items()}
    symbols = spec['symbols']
    helpers = spec['helpers']
    helper_pcs = {r['pc'] for rows in helpers.values() for r in rows}
    csr = [pc for pc, insn in code.items() if is_csr(insn) and pc not in helper_pcs and
           (pc < symbols['trap_entry'] or symbols['main'] <= pc < symbols['replay_text'])]
    require([code[pc] for pc in csr[:5]] == [0x30401073, 0x30529073, 0x3002a073, 0x00305073, 0x00805073]
            and len(csr) == 6 and code[csr[5]] & ~0xf80 == 0xc2202073, 'Exact startup/main CSR image')
    exit_store, = [pc for pc, insn in code.items() if symbols['replay_exit'] <= pc < symbols['selected'] and insn == 0x00a2b023]
    bss_store, = [pc for pc, insn in code.items() if symbols['_start'] <= pc < symbols['trap_entry'] and insn == 0x0002b023]
    require(code[exit_store + 4] == 0xa001 and 'tohost' not in symbols and 'replay_log' not in symbols,
            'Actual SoC CTRL exit/park, not Spike HTIF/log')
    return dict(config=proof['case'], backend=spec, csr_prelude=csr, exit_store=exit_store,
                park=exit_store + 4, bss_store=bss_store, ctrl=0xd0000000, uart=0xc0000000)


class Strict:
    def __init__(self, spec, gold):
        self.spec, self.gold = spec, gold
        self.p, self.s = spec['config'], spec['backend']['symbols']
        self.code = {int(k): v for k, v in spec['backend']['code'].items()}
        self.helpers = spec['backend']['helpers']
        self.lookup = {r['pc']: (name, i) for name, rows in self.helpers.items() for i, r in enumerate(rows)}
        self.width = self.p['sew'] // 8
        self.regs, self.memory = {0: 0}, {}
        self.rows = self.retired = self.capacity = self.csr_count = self.parking = 0
        self.cycle = -1
        self.calls, self.active, self.helper, self.index = [], None, None, 0
        self.exited = self.main_entered = False
        self.bss_next = self.s['__bss_start']
        self.console = bytearray()
        self.exit_retire = None

    def value(self, address, size):
        require(all(address + i in self.memory for i in range(size)), 'Missing actual initialized byte')
        return sum(self.memory[address + i] << (8 * i) for i in range(size))

    def finish_call(self):
        if self.active is not None:
            require(self.helper is None and self.active['reads'] == set(range(18)) and
                    self.active['returned_vstart'] == 0, 'Incomplete full16/guards/vstart original call')

    def consume(self, row):
        self.rows += 1
        cycle = int(row['cycle'])
        require(cycle >= self.cycle and row['event'] != 'cvx_exception', 'Cycle reversal/exception')
        self.cycle = cycle
        if row['event'] != 'retire':
            return
        require(int(row['order']) == self.retired and int(row['trap']) == 0, 'Retire order/trap')
        self.retired += 1
        pc, insn = int(row['pc'], 16), int(row['insn'], 16)
        rd, result = int(row['rd']), int(row['rd_wdata'], 16)
        addr, rmask, wmask, wdata = (int(row[k], 16) for k in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        require(self.code.get(pc) == insn, 'Actual SoC PC/code mismatch')
        require(self.retired != 1 or pc == self.s['_start'], 'Missing original startup')
        if self.exited:
            require(pc == self.spec['park'] and insn == 0xa001 and rd == rmask == wmask == 0, 'Nonparking after CTRL exit')
            self.parking += 1
            return
        require(pc not in (self.s['trap_entry'], self.s['failure']), 'Original trap/oracle failure')
        if pc == self.s['main']:
            require(not self.main_entered and self.bss_next == self.s['__bss_end'], 'Incomplete BSS/main restart')
            self.main_entered = True
        if pc in self.lookup:
            name, i = self.lookup[pc]
            if i == 0:
                require(self.helper is None and self.csr_count == len(self.spec['csr_prelude']) and
                        self.main_entered, 'Helper entry before source setup/overlap')
                if name == 'capacity':
                    require(not self.calls and self.capacity == 0, 'Repeated capacity')
                    self.capacity += 1
                else:
                    require(self.capacity == 1, 'Call before capacity')
                    self.finish_call()
                    ordinal = len(self.calls)
                    require(ordinal < len(self.gold), 'Extra original call')
                    g = self.gold[ordinal]
                    require(name == f'op_{g["op"]}', 'Full operation/seed ordering')
                    args = [self.s['a'], self.s['b'], self.s['out'] + self.width, g['vl'], 16, self.s['mask'], g['vstart']]
                    require([self.regs.get(r) for r in range(10, 17)] == args, 'Original full arguments')
                    for n, values, size in (('a', g['a'], self.width), ('b', g['b'], self.width),
                                            ('mask', g['mask'], 1), ('out', [91] * 18, self.width)):
                        require([self.value(self.s[n] + j * size, size) for j in range(len(values))] == values,
                                'Actual full setup/RNG/FP transition: ' + n)
                    self.active = dict(ordinal=ordinal, op=g['op'], seed=g['seed'], vl=g['vl'], mode=g['mode'],
                                       vstart=g['vstart'], entry_retire=self.retired, reads=set(), returned_vstart=None)
                    self.calls.append(self.active)
                self.helper, self.index = name, 0
            require(self.helper == name and self.index == i, 'Interior/duplicate/noncontiguous helper')
            if name == 'capacity' and i == 1:
                require((rd, result) == (10, 16), 'Capacity VLMAX16')
            elif name != 'capacity':
                g = self.gold[self.active['ordinal']]
                if i in (0, 5, 10):
                    require((rd, result) == (5, g['vl'] if i == 5 else 16), 'Original helper VL')
                if i == 7:
                    require(self.regs.get(16) == g['vstart'], 'Original vstart operand')
                if i == 8:
                    require(self.regs.get(28) == 7 and self.regs.get(16) == g['vstart'], 'Original scalar7/start')
                    self.active.update(target_retire=self.retired, target_cycle=cycle, target_pc=pc, target_insn=insn)
                if i == 9:
                    require((rd, result) == (10, 0), 'Returned full vstart')
                    self.active['returned_vstart'] = 0
            self.index += 1
            if self.index == len(self.helpers[name]):
                self.helper, self.index = None, 0
        else:
            require(self.helper is None, 'Execution left continuous original13 window')
        if is_vector(insn):
            require(pc in self.lookup, 'RVV outside capacity/original helper windows')
        if is_csr(insn) and pc not in self.lookup:
            require(not self.calls and not self.capacity and self.csr_count < len(self.spec['csr_prelude']) and
                    pc == self.spec['csr_prelude'][self.csr_count], 'CSR outside original source phase')
            if insn >> 20 == 0xc22:
                require(rd == (insn >> 7) & 31 and result == 128, 'Original vlenb128')
            self.csr_count += 1
        desc = memory_op(insn)
        if desc:
            size = desc['size']
            require(desc['base'] in self.regs and addr == (self.regs[desc['base']] + desc['offset']) & MASK64,
                    'Actual scalar memory address/base')
            enable = ((1 << size) - 1) << (addr % 8)
            require(addr % size == 0 and enable <= 255, 'Unexpected scalar alignment')
            if desc['kind'] == 'write':
                require(wmask == enable and rmask == 0 and desc['register'] in self.regs and
                        (wdata & ((1 << (8 * size)) - 1)) == (self.regs[desc['register']] & ((1 << (8 * size)) - 1)),
                        'Scalar store enables/value/register')
                if pc == self.spec['bss_store']:
                    require(insn == 0x0002b023 and size == 8 and wdata == 0 and not self.main_entered and
                            addr == self.bss_next and addr + 8 <= self.s['__bss_end'] and
                            self.regs.get(6) == self.s['__bss_end'], 'Strict ordered startup BSS')
                    self.bss_next += 8
                for j in range(size):
                    self.memory[addr + j] = (wdata >> (8 * j)) & 255
                if addr == self.spec['uart']:
                    require(self.main_entered and size == 1 and len(self.console) < 8192, 'SoC UART byte-only console')
                    self.console.append(wdata & 255)
                if addr == self.spec['ctrl']:
                    require(pc == self.spec['exit_store'] and size == 8 and wdata == 0 and self.regs.get(10) == 0,
                            'SoC CTRL raw0, not HTIF encoded1')
                    self.finish_call()
                    self.exited, self.exit_retire = True, self.retired
            else:
                require(rmask == enable and wmask == 0 and rd == desc['register'], 'Scalar load enables/destination')
                if self.s['out'] <= addr < self.s['out'] + 18 * self.width:
                    require(self.active is not None and self.helper is None and size == self.width and
                            (addr - self.s['out']) % self.width == 0, 'Scalar full-oracle address/window/width')
                    element = (addr - self.s['out']) // self.width
                    require(element not in self.active['reads'], 'Duplicate original result/guard load')
                    expected = 91 if element in (0, 17) else self.gold[self.active['ordinal']]['expected'][element - 1]
                    require(result == loaded_value(expected, size, desc['signed']), 'Actual signed scalar result/guard mismatch')
                    self.active['reads'].add(element)
        elif not is_vector(insn):
            require(rmask == wmask == 0, 'Unclassified nonvector memory effect')
        # FP destinations are not integer registers. All integer results are RVFI values.
        if rd and insn & 127 not in (7, 0x53, 0x43, 0x47, 0x4b, 0x4f):
            self.regs[rd] = result
        self.regs[0] = 0

    def finish(self):
        self.finish_call()
        require(self.exited and self.capacity == 1 and len(self.calls) == self.p['calls'] == len(self.gold) and
                self.csr_count == len(self.spec['csr_prelude']), 'Missing CTRL/full calls/capacity/CSR')
        require(self.value(self.s['checks'], 8) == self.p['calls'] and
                self.value(self.s['elements'], 8) == 16 * self.p['calls'] and self.value(self.s['errors'], 8) == 0,
                'Original final checks/elements/errors ledger')
        text = self.console.decode('ascii')
        console_gate(text, self.p, simulator=False)
        return dict(status='FULL_ORIGINAL_RVFI_ACCEPTED', shape=self.p['id'], calls=len(self.calls),
                    results=16 * len(self.calls), guards=2 * len(self.calls), vstart_checks=len(self.calls),
                    helper_instructions=13 * len(self.calls), capacity_calls=self.capacity,
                    firmware_through_ctrl=self.exit_retire, retired=self.retired, rows=self.rows, last_cycle=self.cycle,
                    post_ctrl_parking=self.parking, call_ledger=[dict(c, reads=sorted(c['reads'])) for c in self.calls],
                    console=text, full_order=True, partitioned=False,
                    fflags_oracle='Original has no explicit fflags oracle; no invented acceptance')


def console_gate(text, p, simulator=True):
    require(not VETO.search(text), 'Raw failure/detail veto')
    for prefix, exact in [('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN ' + p['id']), ('RVV_MATRIX_PASS', marker(p)),
                          ('ARITHMETIC_FULL_PASS', 'ARITHMETIC_FULL_PASS ' + p['id']), ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS')]:
        require([line for line in text.splitlines() if line.startswith(prefix)] == [exact], 'Missing/ambiguous full oracle marker')
    if simulator:
        require(text.count(common.SUCCESS) == 1 and '$finish' in text, 'Simulator exit/finish missing')


def audit(path, spec, abort=None):
    state = Strict(spec, read(REF / spec['config']['id'] / 'model.json'))
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if state.rows % 4096 == 0:
                require(abort is None or not abort.is_set(), 'Cancelled during strict full trace')
            state.consume(row)
    return state.finish()


def artifacts(result, case, ledger, spec, abort):
    # Source identity remains in case; only runtime command matching uses the test id.
    common.check_artifacts(result, dict(case, original_name=case['id']), ledger)
    console_gate((result.artifact_dir / 'console.log').read_text(), spec['config'])
    require(not VETO.search((result.artifact_dir / 'work/run.vcs.log').read_text()), 'Raw VCS failure/detail veto')
    return audit(result.artifact_dir / 'commit_trace.csv', spec, abort)
