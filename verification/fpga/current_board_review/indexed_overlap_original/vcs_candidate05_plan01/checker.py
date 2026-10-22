#!/usr/bin/env python3
"""Read-only RVFI/CVX observer for the three reference03 ELFs, not Spike text."""
import csv
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
from scoped_rv64c_memory import decode

FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
CSR = (0x342, 0x341, 0x343, 8, 0xc20, 0xc21, 3, 15)
TARGETS = (0x0645f207, 0x0645f807, 0x0445f807)
STORES = (0x02066227, 0x02066827)
RELOAD = 0x02057207
MASK64 = (1 << 64) - 1


def require(ok, message):
    if not ok:
        raise ValueError(message)


def instructions(disassembly):
    return {int(a, 16): int(op, 16) for a, op in
            re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s', disassembly, re.M)}


def value(i):
    return ((((i * 13 + 7) % 32) * 1024 * 7919) ^ 0xa5a50f0f) & 0xffffffff


def point(values, r):
    require(values == [32, 17, 0, 117, 5] + [
        value(i) if r < 50 or 7 <= i < 17 and i % 2 else 0xfffffff9
        for i in range(32)] + [0x5b12, 0x5b12], 'Results/guards/CSR round ' + str(r))


def memory_access(row, regs, write):
    # NF2 csv_check.scalar_store contract: shifted enables, unshifted store data.
    insn, address, mask = (int(row[k], 16) for k in
                           ('insn', 'mem_addr', 'mem_wmask' if write else 'mem_rmask'))
    if not mask:
        return None
    d = decode(insn)
    if d is not None:
        require(d['kind'] == ('write' if write else 'read'), 'Wrong compressed access kind')
        width, source, base, offset = d['size'], d['register'], d['base'], d['offset']
    else:
        require(insn & 127 == (0x23 if write else 3), 'Non-scalar RVFI memory access')
        funct = (insn >> 12) & 7
        require(funct <= 3 if write else funct in (0, 1, 2, 3, 4, 5, 6), 'Invalid memory width')
        width, base = 1 << (funct & 3), (insn >> 15) & 31
        source = (insn >> 20) & 31 if write else (insn >> 7) & 31
        offset = ((insn >> 25) << 5) | ((insn >> 7) & 31) if write else insn >> 20
        if offset & 2048:
            offset -= 4096
    require(address == (regs[base] + offset) & MASK64, 'RVFI effective address mismatch')
    require(width in (1, 2, 4, 8) and address % 8 + width <= 8, 'Misaligned scalar observation')
    require(mask == ((1 << width) - 1) << (address % 8), 'RVFI byte mask mismatch')
    bits = (1 << (width * 8)) - 1
    data = int(row['mem_wdata' if write else 'rd_wdata'], 16) & bits
    if write:
        require(data == regs[source] & bits, 'RVFI store/register disagreement')
    else:
        require(int(row['rd']) == source and source != 0, 'Unobservable scalar load')
    return address, data, width


class Checker:
    def __init__(self, symbols, opcodes, fault, overlap):
        self.s, self.ops, self.fault, self.overlap = symbols, opcodes, fault, overlap
        self.op = TARGETS[0 if overlap else 1]
        pcs = [p for p, op in opcodes.items() if op == self.op]
        require(len(pcs) == 1, 'Ambiguous SoC target opcode/PC')
        self.target = pcs[0]
        self.regs = {i: 0 for i in range(32)}
        self.mem, self.inflight = {}, {}
        self.order = self.cycle = -1
        self.calls = self.reloads = self.reload_retires = self.retries = 0
        self.requests = self.success_responses = self.fault_responses = 0
        self.success_retires = self.trapped_retires = 0
        self.points, self.traps, self.exits = [], [], []
        self.capture = self.await_handler = self.retry = None
        self.round_requests = self.round_success = self.round_retired = 0
        self.round_stores = self.round_store_responses = self.round_store_retires = 0
        self.after_resume = False
        self.pages_read, self.pt_read = [], []
        self.helper_calls = self.masked_calls = 0
        self.post_active = False
        self.post_output, self.post_indices, self.post_guards = [], [], []
        self.post_checks = 0
        self.prologue = []
        stores = [p for p, op in opcodes.items() if symbols['replay_exit'] <= p < symbols['check'] and op & 127 == 0x23]
        require(len(stores) == 1 and opcodes.get(stores[0] + 4) == 0xa001, 'Unrecognized CTRL store/park')
        self.exit_pc = stores[0]

    def read(self, address, width=8):
        require(all(address + i in self.mem for i in range(width)),
                f'Missing observed memory bytes at {address:#x}/{width}')
        return int.from_bytes(bytes(self.mem[address + i] for i in range(width)), 'little')

    def named(self, name, index=0):
        return self.read(self.s[name] + index * 8)

    def cvx(self, r):
        tag = int(r['trans_id'])
        if r['event'] == 'cvx_req':
            require(tag not in self.inflight, 'CVX transaction reused before response')
            op = int(r['insn'], 16)
            self.inflight[tag] = op
            if op == RELOAD:
                require(self.capture is None and self.retry is None and self.await_handler is None,
                        'Index reload across fault/retry')
                require(self.round_requests == 0 and self.reloads == len(self.points), 'Extra/missing index prologue')
                self.reloads += 1
            if op in TARGETS:
                expected = 0x0445f807 if len(self.points) == 50 and not self.fault else self.op
                require(op == expected and self.capture is None and self.await_handler is None,
                        'Wrong/early target request')
                require(self.reloads == len(self.points) + 1, 'Target before index prologue')
                if self.round_requests:
                    require(self.retry is not None, 'Target reissued without completed repair/MRET')
                    self.retries += 1
                    self.retry = None
                else:
                    require(self.retry is None, 'Retry crossed round')
                self.round_requests += 1
                self.requests += 1
            elif op in STORES:
                expected = STORES[0] if self.overlap and len(self.points) < 50 else STORES[1]
                require(op == expected and self.round_success == 1 and self.round_stores == 0 and
                        self.capture is self.retry is self.await_handler is None, 'Wrong/early/extra original result store')
                self.round_stores += 1
            elif self.retry is not None or self.capture is not None:
                # Vector CSR reads are themselves CVX traffic on CVA6.
                readonly_csr = (op & 127 == 0x73 and (op >> 12) & 7 in (2, 3) and
                                (op >> 15) & 31 == 0 and op >> 20 in CSR)
                require(readonly_csr, 'Vector/CSR mutation inside scalar handler/retry gap')
        else:
            require(tag in self.inflight, 'Unpaired CVX response')
            op = self.inflight.pop(tag)
            trapped = int(r['trap'])
            require(trapped in (0, 1), 'Malformed CVX exception bit')
            if op in TARGETS:
                if trapped:
                    require(self.fault and self.await_handler is None, 'Unexpected/overlapping vector fault')
                    self.fault_responses += 1
                    self.await_handler = dict(cycle=self.cycle, ordinal=self.fault_responses - 1)
                else:
                    self.success_responses += 1
                    self.round_success += 1
            else:
                require(not trapped, 'Non-target accelerator exception')
                if op in STORES:
                    self.round_store_responses += 1

    def fault_values(self, cap):
        require(set(cap['csr']) == set(CSR), 'Missing/duplicate handler CSR capture')
        vals = [cap['csr'][c] for c in CSR]
        require(vals[0] in (9, 13), 'Unexpected cause (not syscall/load-page-fault)')
        if vals[0] == 13:
            n = len(self.traps)
            r, start = divmod(n, 32)
            require(self.fault and r == len(self.points) and r < 50, 'Wrong fault round/count')
            require(vals == [13, self.target, 0x40000000 + ((start * 13 + 7) % 32) * 4096,
                             start, 32, 17, 117, 5], 'Fault mepc/mtval/vstart/CSR mismatch')
            require(self.await_handler is not None and self.await_handler['ordinal'] == n,
                    'Handler without matching target exception response')
        else:
            require(self.ops.get(vals[1]) == 0x73 and cap['regs'][17] in (279, 64, 222, 165, 215, 94),
                    'Syscall cause/PC/number not original fixture')
            require(not self.prologue and self.await_handler is None, 'Syscall during pending target/prologue')
        return vals

    def checkpoint(self):
        r = len(self.points)
        require(r < (50 if self.fault else 51) and self.named('io_round') == r, 'Checkpoint membership')
        require(self.capture is self.retry is self.await_handler is None, 'Unfinished fault at checkpoint')
        require(not self.prologue and self.calls - self.post_checks == 72, 'Full prologue/72 post checks missing')
        require(self.round_success == self.round_retired == 1 and
                self.round_requests == (33 if self.fault else 1), 'Incomplete target ledger this round')
        require(self.round_stores == self.round_store_responses == self.round_store_retires == 1,
                'Missing original result store acceptance/response/retirement')
        require(self.reloads == self.reload_retires == r + 1, 'Accepted/retired prologues differ')
        # Pinned -Os code reloads output for io_result, and active indices for expected().
        indices = [i for i in range(32) for _ in range(2 if r < 50 or 7 <= i < 17 and i % 2 else 1)]
        require(self.post_active and self.post_output == [i for i in range(32) for _ in range(2)] and
                self.post_indices == indices and self.post_guards == [0, 33, 0, 33],
                'Missing actual output/index/guard scalar loads in post')
        point([self.read(self.s['io_result'] + (r * 39 + i) * 8) for i in range(39)], r)
        require(self.named('io_errors') == 0, 'Nonzero errors at checkpoint')
        if self.fault:
            require(self.named('io_fault_count', r) == 32 and len(self.traps) == 32 * (r + 1),
                    'Not exactly 32 faults this round')
            for start in range(32):
                actual = [self.read(self.s['io_records'] + ((r * 32 + start) * 7 + j) * 8) for j in range(7)]
                require(actual == self.traps[r * 32 + start]['values'][1:], 'Stored record differs from actual CSR')
        self.points.append(dict(round=r, cycle=self.cycle, checks=self.calls))
        self.round_requests = self.round_success = self.round_retired = 0
        self.round_stores = self.round_store_responses = self.round_store_retires = 0
        self.post_active = False
        self.post_output, self.post_indices, self.post_guards = [], [], []

    def row(self, r):
        require(set(r) == set(FIELDS) and None not in r.values(), 'Malformed/truncated CSV')
        cycle = int(r['cycle'])
        require(cycle >= self.cycle, 'Cycle regressed')
        self.cycle = cycle
        if self.exits:
            require(r['event'] == 'retire' and int(r['pc'], 16) == self.exit_pc + 4 and
                    int(r['insn'], 16) == 0xa001 and int(r['mem_wmask'], 16) == 0 and
                    int(r['mem_rmask'], 16) == 0 and int(r['trap']) == 0,
                    'Side effect or second exit after CTRL completion')
        if r['event'] in ('cvx_req', 'cvx_resp'):
            self.cvx(r)
        if r['event'] != 'retire':
            return
        order = int(r['order'])
        require(order == self.order + 1, 'Retirement gap/duplicate')
        self.order = order
        pc, op, data = (int(r[k], 16) for k in ('pc', 'insn', 'rd_wdata'))
        rd, trap = int(r['rd']), int(r['trap'])
        require(self.ops.get(pc) == op, 'PC/opcode not from pinned SoC ELF')
        require(pc not in (self.s['trap_entry'], self.s['replay_mismatch'], self.s['fail']), 'Firmware failure path')
        require(not trap or op in TARGETS or op == 0x73, 'Unexpected trapped retirement')
        if pc in (self.s['gather32'], self.s['masked_restart32']):
            masked = pc == self.s['masked_restart32']
            require(self.regs[10] == self.s['indices'] and self.regs[11] ==
                    (0x40000000 if self.fault else self.s['pages']) and
                    self.regs[12] == self.s['output'] + 4, 'Original helper pointer arguments')
            if masked:
                require(not self.fault and self.helper_calls == 50 and self.masked_calls == 0 and
                        len(self.points) == 50, 'Extra/early masked helper')
                self.masked_calls += 1
            else:
                require(self.regs[13] == self.overlap and self.helper_calls == len(self.points) < 50,
                        'Original helper overlap/round argument')
                self.helper_calls += 1
            require(self.retry is self.capture is self.await_handler is None, 'Helper replayed across trap')
            require([self.named('indices', i) for i in range(32)] ==
                    [((i * 13 + 7) % 32) * 4096 for i in range(32)], 'Original initialized index vector')
            require(self.read(self.s['output'], 4) == self.read(self.s['output'] + 132, 4) == 0x5b12,
                    'Missing original initialized guards')
            if self.helper_calls == 1 and not masked:
                require(all(self.read(self.s['pages'] + 4 * i, 4) == ((i * 7919) ^ 0xa5a50f0f) & 0xffffffff
                            for i in range(32768)), 'Original initialized backing-memory bytes')
            if masked:
                target = next(p for p, v in self.ops.items() if v == 0x0445f807)
                self.prologue = sorted(p for p in self.ops if pc <= p < target)
            else:
                self.prologue = sorted(p for p in self.ops if pc <= p)[:7]
        if self.prologue:
            require(pc == self.prologue.pop(0) and not trap, 'Original prologue execution order/branch')
            if op & 127 == 0x57 and (op >> 12) & 7 == 7:
                require(data == (17 if (op >> 20) & 0x7ff == 17 and self.regs[5] == 17 else 32),
                        'Original vsetvli returned wrong VL')
        if pc == self.s['post']:
            require(not self.post_active and self.regs[10] == self.s['output'] + 4 and
                    self.regs[11] == 32 and self.regs[12] == int(len(self.points) == 50), 'Post oracle arguments')
            self.post_active = True
            self.post_checks = self.calls
        if pc == self.s['check']:
            require(self.regs[10] == self.regs[11], f'Firmware check mismatch {self.calls}')
            self.calls += 1
        if pc == self.s['io_handler']:
            require(self.capture is None and self.retry is None, 'Nested handler/unconsumed retry')
            self.capture = dict(csr={}, cycle=cycle, repair=False, pte=False, oldpte=False,
                                fence=False, mepc_writes=[], regs=dict(self.regs), records=[])
        if self.capture and self.s['io_trap'] <= pc < self.s['main'] and op & 127 == 0x73:
            f, src, csr = (op >> 12) & 7, (op >> 15) & 31, op >> 20
            if rd and f in (2, 3) and src == 0 and csr in CSR:
                require(csr not in self.capture['csr'], 'Repeated handler CSR')
                self.capture['csr'][csr] = data
        if self.capture and self.capture['csr'].get(0x342) == 13 and op & 127 == 0x73:
            f, src, csr = (op >> 12) & 7, (op >> 15) & 31, op >> 20
            require(not (f in (1, 2, 3, 5, 6, 7) and (f in (1, 5) or src) and
                         csr in (0x341, 8, 0xc20, 0xc21)), 'Fault handler reconstructs PC/vector CSR')
        if self.capture and op & 127 == 0x73 and op >> 20 == 0x341:
            f, src = (op >> 12) & 7, (op >> 15) & 31
            if f in (1, 5):
                self.capture['mepc_writes'].append(src if f == 5 else self.regs[src])
        if self.capture and self.capture['pte'] and op == 0x0330000f:
            self.capture['fence'] = True
        if pc == self.s['io_repair_sfence']:
            require(self.capture is not None, 'Repair outside handler')
            vals = self.fault_values(self.capture)
            require(vals[0] == 13 and self.capture['pte'] and self.capture['fence'] and
                    not self.capture['repair'], 'Repair ordering')
            require(op & 0xfe007fff == 0x12000073 and (op >> 20) & 31 == 0 and
                    self.regs[(op >> 15) & 31] == vals[2], 'Wrong addressed SFENCE')
            self.capture['repair'] = True
        if pc == self.s['io_retry_mret']:
            require(op == 0x30200073 and self.capture is not None, 'Missing real handler MRET')
            vals = self.fault_values(self.capture)
            if vals[0] == 13:
                require(self.capture['repair'] and self.capture['pte'], 'MRET before repair')
                require(self.capture['mepc_writes'] == [] and self.regs == self.capture['regs'],
                        'Fault PC/scalar register context not preserved')
                require(self.capture['records'] == list(range(7)), 'Missing/reordered fault record stores')
                require(self.named('io_fault_count', len(self.traps) // 32) == len(self.traps) % 32 + 1 and
                        self.named('io_minor') == len(self.traps) + 1, 'Per-fault counter increment')
                self.traps.append(dict(values=vals, handler_cycle=self.capture['cycle'], mret_cycle=cycle))
                self.retry = self.target
                self.await_handler = None
            else:
                target = self.s['io_m_resume'] if self.capture['regs'][17] == 94 else vals[1] + 4
                require(self.capture['mepc_writes'] == [target], 'Syscall MRET not original PC+4/exit')
            self.capture = None
        if op == RELOAD and not trap:
            self.reload_retires += 1
        if op in TARGETS:
            if trap:
                self.trapped_retires += 1
            else:
                expected = self.target if op != 0x0445f807 else next(p for p, v in self.ops.items() if v == op)
                require(pc == expected, 'Successful target moved PC')
                self.success_retires += 1
                self.round_retired += 1
        if op in STORES and not trap:
            require(self.regs[12] == self.s['output'] + 4, 'Original result store base changed')
            self.round_store_retires += 1
        if pc == self.s['io_checkpoint']:
            self.checkpoint()
        if pc == self.s['io_m_resume']:
            require(len(self.points) == (50 if self.fault else 51), 'Early return to M')
            self.after_resume = True
        write = memory_access(r, self.regs, True) if not trap else None
        if write:
            a, v, width = write
            require(not 0x40000000 <= a < 0x40020000, 'Store to read-only source VA')
            if self.capture and self.capture['csr'].get(0x342) == 13 and self.s['io_pt'] + 8192 <= a < self.s['io_pt'] + 12288:
                vals = self.fault_values(self.capture)
                page = (vals[2] - 0x40000000) // 4096
                require(a == self.s['io_pt'] + 8192 + page * 8 and width == 8 and self.read(a) == 0 and
                        self.capture['oldpte'],
                        'Wrong/nonzero prior repair leaf')
                require(v == ((self.s['pages'] + page * 4096) >> 12 << 10) | 0xc3 and
                        not self.capture['pte'], 'Wrong/repeated PTE repair')
                self.capture['pte'] = True
            if self.capture and self.capture['csr'].get(0x342) == 13 and self.s['io_records'] <= a < self.s['io_records'] + 50 * 32 * 56:
                vals = self.fault_values(self.capture)
                j = len(self.capture['records'])
                require(j < 7 and width == 8 and a == self.s['io_records'] + len(self.traps) * 56 + j * 8 and
                        v == vals[j + 1], 'Fault record slot/value differs from CSR')
                self.capture['records'].append(j)
            for i in range(width):
                self.mem[a + i] = (v >> (8 * i)) & 255
            if a == self.s['io_errors']:
                require(v == 0, 'Firmware error state written')
            if a == 0xd0000000:
                require(pc == self.exit_pc and width == 8 and v == 0, 'Nonzero/invalid CTRL exit')
                self.exits.append(v)
        load = memory_access(r, self.regs, False) if not trap else None
        if load and self.capture and self.capture['csr'].get(0x342) == 13:
            a, v, width = load
            if self.s['io_pt'] + 8192 <= a < self.s['io_pt'] + 12288:
                vals = self.fault_values(self.capture)
                leaf = self.s['io_pt'] + 8192 + ((vals[2] - 0x40000000) // 4096) * 8
                require(a == leaf and width == 8 and v == 0 and not self.capture['pte'], 'Actual old PTE load is not zero')
                self.capture['oldpte'] = True
        if load and self.post_active:
            a, v, width = load
            if self.s['indices'] <= a < self.s['indices'] + 256:
                i = (a - self.s['indices']) // 8
                require(width == 8 and a % 8 == 0 and v == ((i * 13 + 7) % 32) * 4096,
                        'Actual index read differs')
                self.post_indices.append(i)
            if self.s['output'] <= a < self.s['output'] + 136:
                i = (a - self.s['output']) // 4
                require(width == 4 and a % 4 == 0, 'Output load width')
                if i in (0, 33):
                    require(v == 0x5b12, 'Actual output guard corrupted')
                    self.post_guards.append(i)
                else:
                    element = i - 1
                    expected = value(element) if len(self.points) < 50 or 7 <= element < 17 and element % 2 else 0xfffffff9
                    require(v == expected, 'Actual output read differs')
                    self.post_output.append(element)
        if load and self.after_resume and self.s['main'] <= pc < self.s['io_handler']:
            a, v, width = load
            if self.s['pages'] <= a < self.s['pages'] + 131072:
                i = len(self.pages_read)
                require(width == 4 and a == self.s['pages'] + 4 * i and
                        v == ((i * 7919) ^ 0xa5a50f0f) & 0xffffffff, 'Full backing-memory scalar read differs')
                self.pages_read.append(a)
            if self.s['io_pt'] <= a < self.s['io_pt'] + 12288:
                offset = a - self.s['io_pt']
                i, table = divmod(len(self.pt_read), 3)
                require(width == 8 and offset == table * 4096 + i * 8, 'Final PTE read coverage/order')
                wanted = {8: ((self.s['io_pt'] + 4096) >> 12 << 10) | 1,
                          16: 0x200000cf, 4096: ((self.s['io_pt'] + 8192) >> 12 << 10) | 1}.get(offset, 0)
                require(v == wanted, 'Final actual PTE load differs')
                self.pt_read.append(a)
        if rd and not trap:
            self.regs[rd] = data
        self.regs[0] = 0

    def finish(self):
        fault = self.fault
        count = 50 if fault else 51
        require(len(self.points) == count and self.reloads == self.reload_retires == count, 'Incomplete 50 rounds/control')
        require(self.success_responses == self.success_retires == count and
                self.requests == (1650 if fault else 51), 'Incomplete accepted/success target ledger')
        require(self.fault_responses == len(self.traps) == self.retries == (1600 if fault else 0), 'Fault/MRET/retry totals')
        require(self.capture is self.await_handler is self.retry is None and not self.inflight, 'Unfinished CVX/handler')
        require(self.exits == [0] and self.after_resume, 'Missing/duplicate CTRL0 exit')
        require(self.helper_calls == 50 and self.masked_calls == (0 if fault else 1), 'Original helper invocation totals')
        expected = dict(io_errors=0, io_exit_code=0, io_round=50, io_mask_count=0 if fault else 1,
                        io_minor=1600 if fault else 0, io_maps=50 if fault else 0,
                        io_unmaps=50 if fault else 0, io_done=0x525656303146494e)
        if fault:
            expected['faults'] = 1600
        for name, v in expected.items():
            require(self.named(name) == v, 'Terminal counter/magic: ' + name)
        require(self.calls == self.named('io_checks') == (21595 if fault else 5215), 'Full firmware oracle check count')
        require(len(self.pages_read) == 32768 and len(self.pt_read) == 1536, 'Full memory/PTE actual load coverage')
        require(all(self.named('io_fault_count', i) == (32 if fault else 0) for i in range(50)), 'Final per-round fault counts')
        return dict(status='CSV_FULL_ORACLE_PASS', rounds=50, points=self.points, checks=self.calls,
                    target_pc=hex(self.target), accepted_targets=self.requests, successful_target_retires=self.success_retires,
                    optional_trapped_target_retires=self.trapped_retires, reloads=self.reloads,
                    fault_responses=self.fault_responses, repairs=len(self.traps), retries=self.retries, traps=self.traps,
                    backing_words_read=32768, pte_words_read=1536, retired=self.order + 1, last_cycle=self.cycle,
                    scope='Full reference03 fixture; not Linux minor-fault batching or pre-fault VRF timing')


def analyze(path, work, case, abort=None):
    c = Checker(json.loads((work / 'soc.symbols.json').read_text()),
                instructions((work / 'soc.dis').read_text()), case['fault'], case['overlap'])
    try:
        with Path(path).open(newline='') as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames == FIELDS, 'Wrong CSV header')
            for n, row in enumerate(reader):
                if n % 4096 == 0:
                    require(abort is None or not abort.is_set(), 'Cancelled during CSV checking')
                c.row(row)
        require(abort is None or not abort.is_set(), 'Cancelled before final CSV decision')
        return c.finish()
    except (ValueError, KeyError, TypeError, OSError) as error:
        return dict(status='CSV_NOT_PASS', error=str(error), cycle=c.cycle, retired=c.order + 1,
                    points=c.points, faults=len(c.traps), requests=c.requests, retries=c.retries)
