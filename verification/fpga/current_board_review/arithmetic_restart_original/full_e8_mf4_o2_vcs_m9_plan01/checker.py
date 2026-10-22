"""Full original cap32 e8 mf4 RVFI oracle. No Spike-only log or HTIF assumptions."""
import csv
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'full_e8_mf4_optimized_compile01'
G = HERE.parents[1]
sys.path.insert(0, str(G / 'gather_repair05'))
import regression as common
sys.path.insert(0, str(G.parents[1] / 'coverage'))
from scoped_rv64c_memory import decode as compressed_memory

read, require = common.read, common.require
def sha(path):
    return common.sha(Path(path))
READY_SHA = 'f3eba77f2abd2fd1a9ad43eca00f26216ad1ad6c9cdbeceabd9a77d9f2751fe0'
SHAPE = 'rvv_matrix_e8_mf4'
SHAPES = (SHAPE,)
CAP = 32
ELFS = ('33fac90cb3c541657ede2d3b01e2cbd52d7ddd97cd0b78599ac237f237c16f44',)
MASK64 = (1 << 64) - 1
PROFILE_SHA = '3cc34144ae982e299d2cd51994d3e6545ba386583fbea09d99b8bbfc173aa656'
VETO = re.compile(common.BAD.pattern + r'|\bRVV_MATRIX_DETAIL\b|\b(?:FAIL|FAILED|TRAP|MISMATCH|UNSUPPORTED|ABORTED)\b', re.I)


def marker(p):
    return (f"RVV_MATRIX_PASS sew={p['sew']} vlmax={CAP} cases={p['calls']} "
            f"elements={CAP*p['calls']} errors=0 seeds=3 guard_tail_mask_vstart=checked")


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
    exit_store, = [pc for pc, insn in code.items() if symbols['replay_exit'] <= pc < symbols['number'] and insn == 0x00a2b023]
    bss_store, = [pc for pc, insn in code.items() if symbols['_start'] <= pc < symbols['trap_entry'] and insn == 0x0002b023]
    require(code[exit_store + 4] == 0xa001 and 'tohost' not in symbols and 'replay_log' not in symbols,
            'Actual SoC CTRL exit/park, not Spike HTIF/log')
    return dict(config=proof['case'], backend=spec, csr_prelude=csr, exit_store=exit_store,
                park=exit_store + 4, bss_store=bss_store, ctrl=0xd0000000, uart=0xc0000000)


def validate_reset(spec, gold):
    require(sha(HERE/'reset_profile.json') == PROFILE_SHA, 'Frozen M9 reset profile')
    p = read(HERE/'reset_profile.json')
    require(p['FpgaEn'] == 0 and p['initial_gpr_values'] == [0]*32 and
            p['allowed_shape'] == SHAPE and p['original_soc_elf_sha256'] == ELFS[0], 'Exact reset/ELF scope')
    old = HERE.parent/'full_small2_reset_gpr_recovery01/reset_profile.json'
    require(sha(old) == p['source_profile_sha256'] == '308784d27eaf81e2a608cd7cd37a9ac61a22a58ce9eda994715cec58dcd682a4', 'Reviewed reset authority')
    require(p['rtl_pins'] == {k.replace('candidate06','candidate09'):v for k,v in read(old)['rtl_pins'].items()}, 'Identical reset/encoder RTL')
    for path,digest in p['rtl_pins'].items():require(sha(path) == digest, 'Reset RTL drift '+path)
    image = read(p['image'])
    require(sha(p['image']) == p['image_sha256'] == '48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a' and
            image['snapshot_sha256'] == p['snapshot_sha256'] and image['manifest_sha256'] == p['compiled_manifest_sha256'] and
            image['configuration_sha256'] == p['configuration_sha256'], 'M9 reset image/config identity')
    require(spec == specification(SHAPE) and gold == read(REF/SHAPE/'model.json'), 'Full cap32 original spec/model')
    ready=read(REF/'READY.json');pins=read(ready['evidence_pins'])
    require(sha(ready['evidence_pins']) == ready['evidence_pins_sha256'] and
            pins[str(REF/SHAPE/'model.json')] == sha(REF/SHAPE/'model.json'), 'Original model pin')
    return dict(enumerate(p['initial_gpr_values']))


class MemoryOwners:
    """Require actual owner lifetimes for every nonempty helper memory request."""
    def __init__(self,spec):
        self.lookup={x['pc']:(name,i) for name,window in spec['backend']['helpers'].items() for i,x in enumerate(window)}
        self.arch={};self.live={};self.memory_arch=[];self.retired=[]
        self.allocs=self.dones=0
    @staticmethod
    def memory(insn):return insn&127 in (7,39) and (insn>>12)&7 in (0,5,6,7)
    def consume(self,row):
        event=row['event'];insn=int(row['insn'],16)
        if event=='arch_start':
            seq=int(row['order']);require(seq not in self.arch,'Repeated architecture owner')
            self.arch[seq]=dict(insn=insn,trans=int(row['trans_id']),allocs=0,dones=0)
            if self.memory(insn):self.memory_arch.append(seq)
        elif event=='uop_alloc':
            seq,vid=int(row['order']),int(row['port']);require(seq in self.arch and vid not in self.live,'Unowned/reused backend allocation')
            a=self.arch[seq];require(a['insn']==insn and a['trans']==int(row['trans_id']),'Backend owner metadata')
            self.live[vid]=(seq,insn,int(row['trans_id']));a['allocs']+=1;self.allocs+=1
        elif event=='uop_done':
            seq,vid=int(row['order']),int(row['port'])
            require(self.live.get(vid)==(seq,insn,int(row['trans_id'])),'Missing/mismatched backend completion')
            del self.live[vid];self.arch[seq]['dones']+=1;self.dones+=1
        elif event=='retire' and self.memory(insn):
            pc=int(row['pc'],16);require(pc in self.lookup,'Memory retirement outside original helpers')
            name,index=self.lookup[pc]
            self.retired.append(dict(insn=insn,pc=pc,required=index in (1,2,3,4,11)))
    def finish(self):
        require(not self.live and self.allocs==self.dones and self.allocs>0,'Missing real completion lifecycle')
        require(len(self.retired)==len(self.memory_arch)==20664,'Full original helper/target memory requests')
        required=0
        for r,seq in zip(self.retired,self.memory_arch):
            a=self.arch[seq];require(a['insn']==r['insn'] and a['allocs']==a['dones'],'Memory request order/completion')
            if r['required']:
                required+=1;require(a['allocs']>0,'Missing nonempty helper memory owner '+hex(r['pc']))
        require(required==20475,'All five cap32 memory helpers per call required')
        return dict(memory_requests=len(self.retired),required_nonempty_helpers=required,
                    all_uop_allocs=self.allocs,all_uop_dones=self.dones,live_at_end=0)


class Strict:
    def __init__(self, spec, gold):
        self.spec, self.gold = spec, gold
        self.p, self.s = spec['config'], spec['backend']['symbols']
        self.code = {int(k): v for k, v in spec['backend']['code'].items()}
        self.helpers = spec['backend']['helpers']
        self.lookup = {r['pc']: (name, i) for name, rows in self.helpers.items() for i, r in enumerate(rows)}
        self.width = self.p['sew'] // 8
        self.regs, self.memory = validate_reset(spec, gold), {}
        self.s = dict(self.s, failure=next(v for k,v in self.s.items() if k == 'failure' or k.startswith('failure.')))
        self.owners = MemoryOwners(spec)
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
            require(self.helper is None and self.active['reads'] == set(range(CAP + 2)) and
                    self.active['returned_vstart'] == 0, 'Incomplete full32/guards/vstart original call')

    def consume(self, row):
        self.owners.consume(row)
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
                    args = [self.s['a'], self.s['b'], self.s['out'] + self.width, g['vl'], CAP, self.s['mask'], g['vstart']]
                    require([self.regs.get(r) for r in range(10, 17)] == args, 'Original full arguments')
                    for n, values, size in (('a', g['a'], self.width), ('b', g['b'], self.width),
                                            ('mask', g['mask'], 1), ('out', [91] * (CAP + 2), self.width)):
                        require([self.value(self.s[n] + j * size, size) for j in range(len(values))] == values,
                                'Actual full setup/RNG/FP transition: ' + n)
                    self.active = dict(ordinal=ordinal, op=g['op'], seed=g['seed'], vl=g['vl'], mode=g['mode'],
                                       vstart=g['vstart'], entry_retire=self.retired, reads=set(), returned_vstart=None)
                    self.calls.append(self.active)
                self.helper, self.index = name, 0
            require(self.helper == name and self.index == i, 'Interior/duplicate/noncontiguous helper')
            if name == 'capacity' and i == 1:
                require((rd, result) == (10, CAP), 'Capacity VLMAX32')
            elif name != 'capacity':
                g = self.gold[self.active['ordinal']]
                if i in (0, 5, 10):
                    require((rd, result) == (5, g['vl'] if i == 5 else CAP), 'Original helper VL')
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
                if self.s['out'] <= addr < self.s['out'] + (CAP + 2) * self.width:
                    require(self.active is not None and self.helper is None and size == self.width and
                            (addr - self.s['out']) % self.width == 0, 'Scalar full-oracle address/window/width')
                    element = (addr - self.s['out']) // self.width
                    require(element not in self.active['reads'], 'Duplicate original result/guard load')
                    expected = 91 if element in (0, CAP + 1) else self.gold[self.active['ordinal']]['expected'][element - 1]
                    require(result == loaded_value(expected, size, desc['signed']), 'Actual signed scalar result/guard mismatch')
                    self.active['reads'].add(element)
        elif not is_vector(insn):
            require(rmask == wmask == 0, 'Unclassified nonvector memory effect')
        # FP destinations are not integer registers. All integer results are RVFI values.
        if rd and insn & 127 not in (7, 0x53, 0x43, 0x47, 0x4b, 0x4f):
            self.regs[rd] = result
        self.regs[0] = 0

    def finish(self):
        owner_report = self.owners.finish()
        self.finish_call()
        require(self.exited and self.capacity == 1 and len(self.calls) == self.p['calls'] == len(self.gold) and
                self.csr_count == len(self.spec['csr_prelude']), 'Missing CTRL/full calls/capacity/CSR')
        require(self.value(self.s['checks'], 8) == self.p['calls'] and
                self.value(self.s['elements'], 8) == CAP * self.p['calls'] and self.value(self.s['errors'], 8) == 0,
                'Original final checks/elements/errors ledger')
        text = self.console.decode('ascii')
        console_gate(text, self.p, simulator=False)
        return dict(status='FULL_ORIGINAL_RVFI_ACCEPTED', shape=self.p['id'], calls=len(self.calls),
                    results=CAP * len(self.calls), guards=2 * len(self.calls), vstart_checks=len(self.calls),
                    helper_instructions=13 * len(self.calls), capacity_calls=self.capacity, memory_owners=owner_report,
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
            try:state.consume(row)
            except Exception as error:
                raise ValueError(f'CSV first cause row={state.rows} call={state.active["ordinal"] if state.active else None} '
                    f'cycle={row.get("cycle")} event={row.get("event")} pc={row.get("pc")}: {error}') from error
    return state.finish()


def artifacts(result, case, ledger, spec, abort):
    # Source identity remains in case; only runtime command matching uses the test id.
    common.check_artifacts(result, dict(case, original_name=case['id']), ledger)
    console_gate((result.artifact_dir / 'console.log').read_text(), spec['config'])
    require(not VETO.search((result.artifact_dir / 'work/run.vcs.log').read_text()), 'Raw VCS failure/detail veto')
    return audit(result.artifact_dir / 'commit_trace.csv', spec, abort)
