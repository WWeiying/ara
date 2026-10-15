"""Original full144 RVFI observer. No expected vector writes are manufactured."""
import csv
import importlib.util
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'segment_alignment_e16_m2_full144_prepare01'
G = HERE.parents[1]
sys.path.insert(0, str(REF))
sys.path.insert(0, str(REF / 'recovery01'))
import model as m
import checker02 as reference
from prepare import code, window
require = m.require
MASK = (1 << 64) - 1
FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
CSR_RECORD = {8: 0, 0xc21: 1, 0xc20: 2, 0x342: 3, 0x341: 4, 0x343: 5, 0x300: 6, 0x180: 7}
READY_SHA = 'e62b7cff2bb0c583d8e5f1123439ea31df385e9576a2b222ec2ea985ef9b04d0'
NAME = 'segment_alignment_e16_m2_full144'

def read(path):
    return json.loads(Path(path).read_text())

def specification():
    require(m.sha(REF / 'READY.json') == READY_SHA, 'Reference READY drift')
    ready = read(REF / 'READY.json')
    require(m.sha(ready['soc_elf']) == ready['soc_elf_sha256'], 'SoC ELF drift')
    out = REF / 'software01'
    symbols = read(out / 'soc.symbols.json')
    instructions = code((out / 'soc.dis').read_text())
    helpers = read(out / 'source_proof.json')['backends']['soc']['helpers']
    for name, proof in helpers.items():
        require([instructions[p] for p in proof['pcs']] == proof['encodings'], 'Original helper bytes ' + name)
    exits = window(instructions, symbols['replay_exit'], 5)
    stores = [p for p in exits if instructions[p] & 0x707f == 0x3023]
    require(len(stores) == 1 and instructions[stores[0]+4] == 0xa001, 'Exact SoC exit/park')
    require('tohost' not in symbols, 'No Spike-only output in SoC')
    return dict(elf=ready['soc_elf'], elf_sha256=ready['soc_elf_sha256'], symbols=symbols,
                code={str(p): i for p, i in instructions.items()}, helpers=helpers,
                exit_store=stores[0], park=stores[0]+4)

def capability(cfg, target, record):
    require(cfg['offset'] == 1 and cfg['vl'] > 0 and not cfg['off'], 'Ineligible capability')
    require(record[3] == (6 if cfg['store'] else 4) and record[4] == target and
            record[8] == 1 and record[9] == MASK, 'Target/cause/phase/return capability')
    require(record[1:3] == [9,cfg['vl']], 'Capability actual VL/vtype')

def protocol(text, source_exit):
    require(source_exit in (0, 77), 'Invalid source exit')
    oracle = 'SEGMENT144_CAPABILITY_COMPLETE' if source_exit else 'SEGMENT144_NUMERICAL_PASS'
    require(text.splitlines().count(oracle) == 1, 'Missing/duplicate exact source marker')
    require(text.count('SEGMENT144_') == 1, 'Conflicting source marker')
    expected = ('Core Test *** FAILED *** (tohost = 77)' if source_exit else
                'Core Test *** SUCCESS *** (tohost = 0)')
    require(text.count(expected) == 1 and '$finish' in text, 'Exact simulator end protocol')
    remainder = text.replace(expected, '')
    require(not BAD.search(remainder), 'Unexpected fatal/failure, not capability')

# During monitoring only this exact completed warning is eligible for later audit.
# Negative lookahead does not bless arbitrary FAIL, numeric exits or fatal messages.
BAD = re.compile(r'SEGMENT144_FAIL|BOARD_REPLAY_(?:TRAP|MISMATCH|SERVICE_FAIL)|'
                 r'\bFAILED\b|\bFAIL\b|Error-\[|Fatal[-:]|\$fatal|'
                 r'\bUVM_FATAL\b(?![ \t]*:[ \t]*0\b)|UnexpectedFatal|\bMISMATCH\b', re.I)

class FailureMatcher:
    def search(self,text):
        warning = 'Core Test *** FAILED *** (tohost = 77)'
        text = text.replace(warning, '')
        start = text.rfind('Core Test ')
        if start >= 0 and warning.startswith(text[start:]):
            text = text[:start]
        return BAD.search(text)

class Checker:
    def __init__(self, spec):
        self.spec = spec; self.s = spec['symbols']; self.code = {int(p): i for p, i in spec['code'].items()}
        self.helpers = {n: h['pcs'] for n, h in spec['helpers'].items()}
        self.owner = {p: n for n, pcs in self.helpers.items() for p in pcs}
        self.targets = {self.s[f'target_{i}']: i for i in range(8)}
        self.target_codes = {self.code[p] for p in self.targets}
        self.mem = reference.elf_memory(spec['elf']); self.regs = {0: 0}; self.csr = {}; self.saved = {}
        self.configs = m.cases(); self.gold = [m.expected(c) for c in self.configs]
        self.current = -1; self.checkpoints = 0; self.active = None; self.position = 0
        self.calls = []; self.capacity = 0; self.rows = 0; self.retired = 0; self.cycle = -1
        self.numerical = 0; self.capabilities = 0; self.words = 0; self.comparing = False
        self.actual_reads = []; self.expected_reads = []; self.reports = []; self.ctrl = []
        self.capture = None; self.captures = []; self.post = {}; self.last_pc = None
        self.cvx = {}; self.requests = []; self.exceptions = []; self.arch = {}; self.pending = {}; self.done = []
        self.memory_requests = []
        self.vector_unknown = set(); self.setup_writes = {}; self.mask_writes = set()
        self.spill = reference.StoreGuard(); self.source_exit = None

    def val(self, name):
        return reference.read(self.mem, self.s[name])

    def invalidate(self, address, size):
        for a in range(address, address+size):
            self.mem.pop(a, None); self.vector_unknown.add(a)

    def event(self, r, insn):
        event = r['event']; tid = int(r['trans_id']); order = int(r['order']); port = int(r['port'])
        if event == 'cvx_req':
            require(tid not in self.cvx, 'Duplicate live CVX owner')
            self.cvx[tid] = (insn, self.current)
            if insn&127 in (7,39) and (insn>>12)&7 in (0,5,6,7):
                self.memory_requests.append(insn)
            if insn in self.target_codes:
                require(0 <= self.current < 144 and insn == self.code[self.s[f"target_{self.configs[self.current]['op']}"]], 'Target request owner/op')
                self.requests.append(self.current)
        elif event == 'cvx_resp':
            require(tid in self.cvx, 'CVX response without owner')
            op, case = self.cvx.pop(tid)
            if int(r['trap']):
                require(op in self.target_codes and case == self.current and case not in self.exceptions, 'Unexpected/duplicate CVX exception')
                self.exceptions.append(case)
        elif event == 'arch_start':
            require(order not in self.arch, 'Duplicate architecture order')
            self.arch[order] = (insn, self.current)
        elif event == 'uop_alloc':
            require(order in self.arch and port not in self.pending, 'Uop allocation owner/VID')
            require(self.arch[order][0] == insn, 'Uop instruction owner mismatch')
            self.pending[port] = (order, insn)
        elif event == 'uop_done':
            require(self.pending.get(port) == (order, insn), 'Uop completion wrong owner')
            del self.pending[port]; self.done.append(order)
        else:
            require(event == 'retire', 'Unknown trace event')

    def checkpoint(self):
        case = self.val('mx_case'); require(0 <= case < 144, 'Case bounds')
        cfg = self.configs[case]
        if self.checkpoints % 2 == 0:
            require(case == self.current+1 and self.active is None, 'Full144 natural order')
            self.current = case; self.comparing = False; self.actual_reads = []; self.expected_reads = []; self.post = {}
            for name, want in [('input', m.INPUT), ('memory', m.FILL if cfg['store'] else m.MEMORY),
                               ('output', m.FILL), ('expected', self.gold[case])]:
                reference.equal_bytes(self.mem, self.s['mx_'+name], want, 'Actual full reset '+name)
                require(self.setup_writes.get(name, set()) == set(range(1024)), 'Missing actual reset stores '+name)
            reference.equal_bytes(self.mem, self.s['mx_mask'], bytes([0 if cfg['off'] else 255])*128, 'Mask128')
            require(self.mask_writes == set(range(16)), 'Missing actual mask reset stores')
            require(self.val('mx_scene') == 0 and self.val('mx_return') == MASK and self.val('mx_outcome') == 0, 'Reset control')
            self.setup_writes = {}; self.mask_writes = set()
        else:
            require(case == self.current and self.active is None and self.requests == list(range(case+1)), 'Case target ownership')
            record = [reference.read(self.mem, self.s['mx_records']+case*80+8*j) for j in range(10)]
            require(self.capture is not None and set(self.capture) == set(range(8)), 'Missing actual handler CSR reads')
            require([self.capture[j] for j in range(8)] == record[:8], 'Recorded context differs from actual CSR readback')
            require(record[6]&0x1800 == 0x800 and record[7] == self.val('mx_satp'), 'S-mode Sv39 context')
            outcome = self.val('mx_outcome')
            if outcome == 1:
                require(case not in self.exceptions and record[:6] == [0,9,cfg['vl'] if cfg['store'] else 128,9,self.s['mx_ecall'],0] and
                        record[8:] == [2,0], 'Actual successful completion context')
                require(self.post == {0xc20: cfg['vl'] if cfg['store'] else 128, 0xc21: 9, 8: 0}, 'Actual post-helper CSR reads')
                require([reference.read(self.mem,self.s['mx_post']+case*32+8*j) for j in range(4)] ==
                        [self.post[0xc20],9,0,0], 'Actual post CSR stores')
                reference.equal_bytes(self.mem, self.s['mx_memory' if cfg['store'] else 'mx_output'], self.gold[case], 'Full8192 oracle')
                require(self.actual_reads == list(range(1024)) and self.expected_reads == list(range(1024)), 'Missing full scalar oracle reads')
                self.numerical += 1
            else:
                require(outcome == 2 and case in self.exceptions, 'Fabricated/invalid capability outcome')
                capability(cfg, self.s[f"target_{cfg['op']}"], record)
                require(not self.actual_reads and not self.expected_reads and not self.post, 'Invented trapped-child readback')
                require(all(reference.read(self.mem,self.s['mx_post']+case*32+8*j) == MASK for j in range(4)), 'Invented post return')
                self.capabilities += 1
            require(self.val('mx_errors') == self.val('mx_fatal') == 0 and not self.pending, 'Error or undrained backend')
            self.reports.append(dict(case=case,outcome=outcome,context=record))
        self.checkpoints += 1

    def scalar(self, r, insn):
        a, rm, wm, data = (int(r[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        desc = reference.scalar(insn)
        if not (rm or wm):
            require(desc is None or int(r['trap']) != 0, 'Missing actual scalar RVFI access')
            return
        require(desc is not None and not int(r['trap']) and not (rm and wm), 'Non-scalar/fault RVFI access')
        size = desc['size']; bits = (1<<(8*size))-1; pc = int(r['pc'],16)
        require(a == (self.regs.get(desc['base'],-2)+desc['offset'])&MASK, 'Actual RVFI effective address')
        require(a%8+size <= 8 and (wm or rm) == ((1<<size)-1)<<(a%8), 'Actual RVFI byte enables')
        if wm:
            require(desc['kind'] == 'write', 'RVFI store instruction')
            value = data & bits
            self.spill.check(value,self.regs,desc,pc,3 if self.current < 0 else 1,self.current,a,self.s,self.code)
            for name in ('input','memory','output','expected'):
                base = self.s['mx_'+name]
                if base <= a < base+8192 and self.s['mx_reset'] <= pc < self.s['mx_compare']:
                    require(size == 8 and (a-base)%8 == 0, 'Reset word alignment')
                    self.setup_writes.setdefault(name,set()).add((a-base)//8)
            base = self.s['mx_mask']
            if base <= a < base+128:
                require(size == 8 and (a-base)%8 == 0, 'Predicate reset width'); self.mask_writes.add((a-base)//8)
            if a == 0xd0000000:
                require(pc == self.spec['exit_store'] and size == 8 and not self.ctrl and value in (0,77), 'CTRL raw source exit')
                self.ctrl.append(value)
            if a == 0xc0000000:
                require(size == 1, 'UART byte width')
        else:
            require(desc['kind'] == 'read' and int(r['rd']) == desc['register'] != 0, 'Actual load destination')
            raw = int(r['rd_wdata'],16); value = raw & bits
            signed = desc.get('signed',size==4)
            extended = (value-(1<<(8*size)))&MASK if signed and value>>(8*size-1) else value
            require(raw == extended, 'Signed load result')
            for j, byte in enumerate(value.to_bytes(size,'little')):
                require(self.mem.get(a+j) == byte or a+j in self.vector_unknown, 'Scalar data differs from actual known bytes')
            if self.comparing:
                cfg = self.configs[self.current]; base = self.s['mx_memory' if cfg['store'] else 'mx_output']
                for b, indices in ((base,self.actual_reads),(self.s['mx_expected'],self.expected_reads)):
                    if b <= a < b+8192:
                        require(size == 8 and (a-b)%8 == 0, 'Full oracle read width')
                        index = (a-b)//8; indices.append(index)
                        require(value == int.from_bytes(self.gold[self.current][index*8:index*8+8],'little'), 'Actual RVFI numerical mismatch')
                        if b == base: self.words += 1
        for j, byte in enumerate(value.to_bytes(size,'little')):
            self.mem[a+j] = byte; self.vector_unknown.discard(a+j)

    def row(self,r):
        require(set(r) == set(FIELDS) and None not in r.values(), 'Malformed row')
        self.rows += 1; cycle = int(r['cycle']); require(cycle >= self.cycle, 'Cycle reversal'); self.cycle = cycle
        insn = int(r['insn'],16); self.event(r,insn)
        if r['event'] != 'retire': return
        require(int(r['order']) == self.retired, 'Retirement order gap'); self.retired += 1
        pc = int(r['pc'],16); rd = int(r['rd']); value = int(r['rd_wdata'],16); trap = int(r['trap'])
        require(self.code.get(pc) == insn, 'Actual ELF PC/code')
        require(pc not in (self.s['trap_entry'],self.s['replay_trap'],self.s['replay_mismatch']), 'Unexpected fatal runtime')
        if self.ctrl:
            require(pc == self.spec['park'] and rd == 0 and not int(r['mem_rmask'],16) and not int(r['mem_wmask'],16), 'Only park after CTRL')
            return
        require(not trap or pc in self.targets or pc == self.s['mx_ecall'], 'Non-target trapping retirement')
        if pc == self.s['mx_checkpoint']: self.checkpoint()
        if pc == self.s['mx_handler']:
            require(self.current >= 0 and self.current == len(self.captures), 'Handler ownership')
            if self.active is not None:
                target = self.s[f"target_{self.configs[self.current]['op']}"]
                require(self.current in self.exceptions, 'Interrupted helper without CVX exception')
                reference.fault_boundary(self.active,self.helpers,self.position,target,self.last_pc)
                self.active = None; self.position = 0
            require(not self.pending, 'Handler before backend done')
            self.capture = {}; self.captures.append(self.capture)
        if self.active is not None and pc not in self.owner:
            require(self.current in self.exceptions and self.s['mx_handler'] <= pc < self.s['mx_enter_s'], 'Original helper interrupted')
        if pc in self.owner:
            name = self.owner[pc]
            if pc == self.helpers[name][0]:
                require(self.active is None, 'Helper reentry')
                self.active = name; self.position = 0
                if name == 'capacity':
                    self.capacity += 1; require(self.current == -1 and self.capacity == 1,'Capacity once')
                    self.saved = dict(self.csr)
                else:
                    cfg = self.configs[self.current]
                    require(name == f"op_{cfg['op']}" and self.calls == list(range(self.current)), 'Original helper order')
                    args = [self.s['mx_input']+64,self.s['mx_output']+64,self.s['mx_mask'],cfg['vl'],128,
                            self.s['mx_memory']+cfg['base'],cfg['stride']&MASK,self.s['mx_scene']]
                    require([self.regs.get(i) for i in range(10,18)] == args, 'Original eight helper arguments')
                    self.calls.append(self.current)
            require(self.active == name and self.helpers[name][self.position] == pc, 'Exact contiguous original helper')
            if pc in self.targets:
                cfg = self.configs[self.current]
                require(self.csr.get(0xc20) == cfg['vl'] and self.csr.get(0xc21) == 9 and self.csr.get(8) == 0 and self.val('mx_scene') == 1,'Actual target CSR/phase')
            self.position += 1
            if self.position == len(self.helpers[name]): self.active = None; self.position = 0
        if pc == self.s['mx_compare']: self.comparing = True
        if self.comparing and pc >= self.s['mx_allowed']: self.comparing = False
        # No RVFI vector payload exists. Forget only actual vector-written ranges;
        # the subsequent scalar loads must supply and independently match every byte.
        if insn&127 == 0x27 and (insn>>12)&7 in (0,5,6,7):
            require(pc in self.owner and self.current >= 0, 'Unexpected vector store')
            cfg = self.configs[self.current]
            if pc in self.targets:
                require(cfg['store'], 'Target direction'); self.invalidate(self.s['mx_memory'],8192)
            else:
                require(not cfg['store'], 'Non-target store in store helper'); self.invalidate(self.s['mx_output'],8192)
        if pc == self.s['mx_handler'] and self.current in self.exceptions and self.configs[self.current]['store']:
            self.invalidate(self.s['mx_memory'],8192)
        self.scalar(r,insn)
        if insn&127 == 0x73 and (insn>>12)&7:
            csr = insn>>20; f = (insn>>12)&7; rs = (insn>>15)&31
            pure = f in (2,3) and rs == 0
            if pure and rd:
                if csr in CSR_RECORD and self.s['mx_trap'] <= pc < self.s['main']:
                    require(self.capture is not None and CSR_RECORD[csr] not in self.capture, 'Actual handler CSR ownership')
                    self.capture[CSR_RECORD[csr]] = value
                if self.s['mx_s_entry'] <= pc < self.s['mx_ecall'] and csr in (0xc20,0xc21,8):
                    require(csr not in self.post, 'Duplicate post CSR'); self.post[csr] = value
                self.csr[csr] = value
            elif not pure:
                operand = rs if f >= 5 else self.regs.get(rs)
                require(operand is not None, 'Missing CSR operand')
                old = self.csr.get(csr, value if rd else 0)
                self.csr[csr] = operand if f in (1,5) else old|operand if f in (2,6) else old&~operand
        if insn&0x707f == 0x7057:
            if insn>>30 == 3: vtype = (insn>>20)&1023
            elif insn>>31 == 0: vtype = (insn>>20)&2047
            else: vtype = self.regs[(insn>>20)&31]
            self.csr[0xc21] = vtype
            self.csr[0xc20] = value if rd else self.regs[(insn>>15)&31]
            self.csr[8] = 0
        if rd and not trap: self.regs[rd] = value
        self.regs[0] = 0; self.last_pc = pc

    def finish(self):
        require(self.checkpoints == 288 and self.current == 143 and self.calls == list(range(144)) and self.capacity == 1, 'Complete144 order/helpers/checkpoints')
        require(self.requests == list(range(144)) and len(self.captures) == 144 and len(self.reports) == 144, '144 actual target/context ownership')
        require(self.numerical+self.capabilities == 144 and 0 <= self.capabilities <= 24 and self.val('mx_noactive') == 96, 'Outcome totals')
        require(self.val('mx_supported') == self.numerical and self.val('mx_unsupported') == self.capabilities, 'Outcome counters')
        require(self.words == self.val('mx_words_checked') == self.numerical*1024, 'Complete executed oracle')
        source = 77 if self.capabilities else 0
        require(self.val('mx_source_exit') == source and self.ctrl == [source] and self.val('mx_done') == 0x7365673134340001 and
                self.val('mx_errors') == self.val('mx_fatal') == 0, 'Actual source/CTRL completion')
        require(not self.cvx and not self.pending and len(self.exceptions) == self.capabilities, 'Undrained/wrong CVX/backend')
        for csr in (0x180,0x305,0x302,0x303,0x304,0xc20,0xc21,8,15,3):
            if csr in self.saved: require(self.csr.get(csr) == self.saved[csr], f'CSR restore {csr:x}')
        return dict(status='FULL144_CAPABILITY_COMPLETE' if source else 'FULL144_NUMERICAL_PASS',source_exit=source,
                    cases=144,numerical=self.numerical,capability=self.capabilities,no_active=96,
                    oracle_bytes=self.words*8,checkpoints=288,rows=self.rows,retired=self.retired,last_cycle=self.cycle,
                    contexts=self.reports,cvx_exception_cases=self.exceptions,linux_clone_COW_equivalence=False,
                    vector_data_evidence='Actual RVFI scalar loads after vector stores, no direct vector payload claim')

    def backend_coverage(self):
        actual = [(order,insn,case) for order,(insn,case) in self.arch.items()
                  if insn&127 in (7,39) and (insn>>12)&7 in (0,5,6,7)]
        require(actual and [insn for _,insn,_ in actual] == self.memory_requests,
                'Missing architecture owners for actual memory requests')
        required=[]
        for order,insn,case in actual:
            require(0 <= case < 144,'Memory owner outside original call')
            cfg=self.configs[case]
            # A VL0 target may be elided. An early fault may not allocate a
            # backend uop. Staging/readback and successful active targets may not.
            if insn not in self.target_codes or (cfg['vl'] and case not in self.exceptions):
                require(order in self.done,'Actual memory owner has no completed backend uop')
                required.append(order)
        return dict(memory_architectures=len(actual),required_completed_owners=required)

def analyze(path,spec):
    checker = Checker(spec)
    with Path(path).open() as f:
        rows = csv.DictReader(f); require(rows.fieldnames == FIELDS,'CSV columns')
        for row in rows: checker.row(row)
    result=checker.finish(); result['backend_coverage']=checker.backend_coverage()
    return result
