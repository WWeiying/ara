"""Actual scalar RVFI values check the complete defined source oracle."""
import csv
from pathlib import Path
import observer as o
require=o.require
FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')

def memory_op(insn):
    if insn & 3 != 3:
        return o.u.decoder.decode(insn)
    op, f = insn & 127, (insn >> 12) & 7
    if op not in (3, 35):
        return None
    write = op == 35
    imm = ((insn >> 25) << 5 | (insn >> 7) & 31) if write else insn >> 20
    if imm & 2048:
        imm -= 4096
    return dict(kind='write' if write else 'read', size=1 << (f if write else f & 3),
                base=(insn >> 15) & 31, register=(insn >> 20) & 31 if write else (insn >> 7) & 31,
                offset=imm, signed=not write and f < 4)

class Checker:
    def __init__(self, spec):
        require(spec['backend']=='soc' and spec['sew']==64 and spec['scenario'] in (1,2), 'Exact SoC scope')
        require('tohost' not in spec['symbols'], 'SoC uses CTRL, not HTIF')
        self.spec = spec
        self.s, self.sew = spec['symbols'], spec['sew']
        self.cfg = o.spec_values(self.sew)
        self.code = {int(k): v for k, v in spec['code'].items()}
        self.mem = o.elf_bytes(spec['elf'])
        self.regs = {i: 0 for i in range(32)}
        self.csrs, self.saved, self.restore_reads = {}, {}, {}
        self.rows = self.retired = self.checks = self.step = self.cap = 0
        self.last_cycle = -1
        self.started = self.completed = self.exited = False
        self.bss_next = self.s['__bss_start']
        self.actions, self.points, self.traps, self.handler = [], [], [], []
        self.cvx, self.target_requests, self.target_responses = {}, 0, 0
        self.read_phase, self.reads = None, []
        self.ctrl, self.parked = [], 0

    def u64(self, name):
        return o.readint(self.mem, self.s[name])

    def scalar(self, r, pc, insn, trap):
        a, rm, wm, raw = (int(r[k], 16) for k in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        if not (rm or wm):
            return
        d = memory_op(insn)
        require(d and not trap and not (rm and wm), 'Only nonfaulting scalar memory row')
        width = d['size']
        require(width in (1, 2, 4, 8) and a % 8 + width <= 8, 'Scalar width/alignment')
        require(a == (self.regs[d['base']] + d['offset']) & o.MASK64, 'Scalar effective address')
        require((wm or rm) == ((1 << width) - 1) << (a % 8), 'RVFI shifted byte enables')
        mask = (1 << (8 * width)) - 1
        if wm:
            require(d['kind'] == 'write' and raw & mask == self.regs[d['register']] & mask, 'Store register value')
            value = raw & mask
            require(not o.VA <= a < o.VA + 8192, 'Load fixture writes virtual data')
            if self.s['__bss_start'] <= a < self.s['__bss_end'] and not self.started:
                require(pc == self.s['_start'] + 0x46 and insn == 0x2b023 and width == 8
                        and a == self.bss_next and value == 0 and a + 8 <= self.s['__bss_end'],
                        'Exact ordered pre-main BSS initialization')
                self.bss_next += 8
            if a in (self.s['fx_errors'], self.s['fx_unexpected']):
                require(value == 0, 'Nonzero source error')
            if a == self.s['fx_completed'] and self.started:
                require(width == 8 and value == o.DONE and not self.completed
                        and set(self.saved) == set(o.RESTORE) and self.restore_reads == self.saved,
                        'Completion requires all original CSR save/restore reads')
                require(self.checks == self.cfg['checks'] and len(self.points) == 2, 'Premature completion')
                self.completed = True
            if a == 0xd0000000:
                require(pc == self.spec['exit_store'] and width == 8 and value == 0 and self.completed,
                        'SoC CTRL raw0 after completion, not Spike HTIF1')
                require(not self.ctrl,'Duplicate CTRL exit')
                self.ctrl.append(value)
                self.exited = True
        else:
            rd, raw = int(r['rd']), int(r['rd_wdata'], 16)
            require(d['kind'] == 'read' and rd == d['register'] and rd != 0, 'Scalar load destination')
            value = raw & mask
            signed = d.get('signed', width == 4)
            require(raw == (value | (o.MASK64 ^ mask if signed and value >> (8 * width - 1) else 0)),
                    'Signed/unsigned scalar result')
            for j, byte in enumerate(value.to_bytes(width, 'little')):
                require(a + j not in self.mem or self.mem[a + j] == byte, 'Read differs from actual prior bytes')
            if self.read_phase is not None:
                objects = [(self.s['fx_pages'], 20480), (self.s['fx_guard_lo'], 64),
                           (self.s['fx_guard_hi'], 64), (self.s['fx_out'], 130 * self.cfg['width']),
                           (self.s['fx_mask'], 16)]
                if any(base <= a < base + n for base, n in objects):
                    self.reads.append((a, width))
        for j, byte in enumerate(value.to_bytes(width, 'little')):
            self.mem[a + j] = byte

    def expected_reads(self, phase):
        s, width = self.s, self.cfg['width']
        out = [(s['fx_pages'] + 8 * i, 8) for i in range(2560)]
        out += [(s[name] + 8 * i, 8) for i in range(8) for name in ('fx_guard_lo', 'fx_guard_hi')]
        out += [(s['fx_out'] + width * i, width) for i in range(130) if o.output_value(self.sew, phase, i) is not None]
        return out + [(s['fx_mask'] + i, 1) for i in range(16)]

    def row(self, r):
        require(set(r) == set(FIELDS) and None not in r.values(), 'Malformed/truncated CSV')
        self.rows += 1
        cycle = int(r['cycle'])
        require(cycle >= self.last_cycle, 'Cycle reversal')
        self.last_cycle = cycle
        event, insn = r['event'], int(r['insn'], 16)
        target = self.code[self.spec['helper'][3]]
        if event == 'cvx_req':
            tid = int(r['trans_id'])
            require(tid not in self.cvx, 'Duplicate CVX ID')
            self.cvx[tid] = insn
            self.target_requests += int(insn == target)
        if event == 'cvx_resp':
            tid = int(r['trans_id'])
            require(tid in self.cvx and int(r['trap']) == 0, 'Unexpected architectural CVX exception')
            self.target_responses += int(self.cvx.pop(tid) == target)
        require(event in ('retire', 'cvx_req', 'cvx_resp', 'arch_start', 'uop_alloc', 'uop_done'), 'Unknown event')
        if event != 'retire':
            return
        require(int(r['order']) == self.retired, 'Retirement order gap')
        self.retired += 1
        pc, rd, value, trap = int(r['pc'], 16), int(r['rd']), int(r['rd_wdata'], 16), int(r['trap'])
        require(self.code.get(pc) == insn, 'Actual SoC PC/code mismatch')
        require(pc not in self.spec['unused'] and pc not in (self.s['trap_entry'], self.s['replay_mismatch']),
                'Unused helper/default trap/mismatch PC')
        require(not self.started or pc != self.s['_start'] + 0x46, 'Boot BSS clear after main')
        if self.exited:
            require(pc == self.spec['park'] and rd == 0 and not trap and
                    int(r['mem_rmask'], 16) == int(r['mem_wmask'], 16) == 0, 'Only original post-CTRL park')
            self.parked += 1
            return
        require(not trap or pc == self.s['fx_ecall'], 'Unexpected target/other retirement trap')
        if trap:
            self.traps.append(pc)
        if pc == self.s['main']:
            require(not self.started and self.bss_next == self.s['__bss_end'], 'Main once after full BSS')
            self.started = True
        if pc == self.s['check']:
            require(self.regs[10] == self.regs[11], 'Actual scalar oracle failed')
            self.checks += 1
        if pc == self.s['check_state']:
            require(self.read_phase is None and self.regs[10] == len(self.points) < 2, 'Full check_state phase')
            self.read_phase, self.reads = self.regs[10], []
        if pc in self.spec['capacity']:
            require(self.started and self.step == 0 and self.cap < 3 and pc == self.spec['capacity'][self.cap], 'Capacity once/in order')
            if self.cap == 1:
                require(rd == 10 and value == 1024 // self.sew, 'Actual capacity result')
            self.cap += 1
        if 0 < self.step < 11:
            require(pc == self.spec['helper'][self.step], 'Interrupted original helper window')
        if pc in self.spec['helper']:
            require(self.cap == 3 and self.step < 11 and pc == self.spec['helper'][self.step], 'Exactly one original11 window')
            i = self.step
            if i == 0:
                require(self.actions == ['checkpoint0', 'enter_s'] and
                        [self.regs[j] for j in range(10, 14)] ==
                        [self.cfg['base'], self.s['fx_out'] + self.cfg['width'], self.s['fx_mask'], 8], 'Original helper arguments/phase')
                self.actions.append('helper')
            if i in (0, 8):
                require(rd == 5 and value == 8, 'Original VL8 setup/restore')
            if i == 3:
                require(self.csrs.get(0xc20) == 8 and self.csrs.get(0xc21) == self.cfg['vtype']
                        and self.csrs.get(8) == 0 and self.regs[10] == self.cfg['base'], 'Target CSR/base')
            if i == 4:
                require(rd == 10 and value == self.cfg['returned_vl'], 'Business VL, not helper-restored VL')
            if i == 5:
                require(rd == 6 and value == 0, 'Immediate returned vstart')
            if i == 9:
                require(self.csrs.get(0xc20) == 8 and self.regs[11] == self.s['fx_out'] + self.cfg['width'], 'Full original output store')
                for j in range(8 * self.cfg['width']):
                    self.mem.pop(self.regs[11] + j, None)
            self.step += 1
        if insn & 127 in (7, 39, 87):
            # No scalar FP occurs in these ELFs. All vector PCs are exact source windows or main restore.
            restore = pc == self.spec['restore_pc'] and len(self.points) == 2
            require(pc in self.spec['helper'] + self.spec['capacity'] or restore, 'Unexpected RVV instruction')
        if pc == self.s['fx_enter_mret']:
            require(self.csrs.get(0x300, 0) & 0x1800 == 0x800 and self.csrs.get(0x180) ==
                    (8 << 60) | ((self.s['fx_pages'] + 8192) >> 12) and self.csrs.get(0x341) == self.s['fx_s_entry'], 'Actual Sv39/S-mode entry')
            self.actions.append('enter_s')
        if pc == self.s['fx_younger_store']:
            require(self.step == 11, 'Younger before helper completion')
            self.actions.append('younger')
        if pc == self.s['fx_handler']:
            require(self.step == 11 and not self.handler, 'Unexpected/extra handler')
            self.handler.append({})
            self.actions.append('handler')
        if pc == self.s['fx_trap_mret']:
            require(len(self.handler) == 1 and self.csrs.get(0x341) == self.s['fx_m_resume']
                    and self.csrs.get(0x300, 0) & 0x1800 == 0x1800, 'Actual M-mode continuation')
            self.actions.append('return_m')
        if insn & 127 == 0x73 and (insn >> 12) & 7:
            k, f, src = insn >> 20, (insn >> 12) & 7, (insn >> 15) & 31
            writing = f in (1, 5) or src != 0
            if not writing and rd:
                if self.started and self.cap == 0 and k in o.RESTORE:
                    require(k not in self.saved, 'Duplicate original CSR save')
                    self.saved[k] = value
                if len(self.points) == 2 and not self.completed and k in o.RESTORE:
                    require(k not in self.restore_reads and value == self.saved.get(k), 'Actual CSR restoration')
                    self.restore_reads[k] = value
                if self.s['fx_trap'] <= pc < self.s['main'] and k in o.FIELDS:
                    require(self.handler and o.FIELDS[k] not in self.handler[0], 'Handler CSR ownership')
                    self.handler[0][o.FIELDS[k]] = value
                self.csrs[k] = value
            if writing:
                x = src if f >= 5 else self.regs[src]
                old = value if rd else self.csrs.get(k, 0)
                self.csrs[k] = x if f in (1, 5) else old | x if f in (2, 6) else old & ~x
        if insn & 0x707f == 0x7057:
            vtype = (insn >> 20) & (1023 if insn >> 30 == 3 else 2047) if insn >> 31 == 0 or insn >> 30 == 3 else self.regs[(insn >> 20) & 31]
            self.csrs.update({0xc21: vtype, 0xc20: value if rd else self.regs[(insn >> 15) & 31], 8: 0})
        if pc == self.s['fx_checkpoint']:
            phase = self.u64('fx_phase')
            require(phase == len(self.points) == self.read_phase, 'Checkpoint phase/order')
            require(self.reads == self.expected_reads(phase), 'Full ordered pages/output/guards/mask scalar reads')
            amount = o.compare(self.mem, self.s, self.sew, phase)
            require(self.checks == self.u64('fx_checks') == self.cfg['checkpoint_checks'][phase], 'Full original check count')
            if phase:
                require(self.handler == [{i: o.readint(self.mem, self.s['fx_records'] + 8 * i) for i in range(10)}], 'Actual handler CSR vs stored context')
            self.points.append(dict(phase=phase, bytes=amount, checks=self.checks, cycle=cycle))
            self.actions.append('checkpoint' + str(phase))
            self.read_phase = None
        self.scalar(r, pc, insn, trap)
        if rd and not trap:
            self.regs[rd] = value
        self.regs[0] = 0

    def finish(self):
        require(self.actions == ['checkpoint0', 'enter_s', 'helper', 'younger', 'handler', 'return_m', 'checkpoint1'], 'Complete source order')
        require(self.traps in ([], [self.s['fx_ecall']]) and len(self.handler) == 1, 'Only completion ecall context')
        require(self.cap == 3 and self.step == 11 and self.completed and self.ctrl == [0]
                and not self.cvx and self.target_requests == self.target_responses == 1, 'Complete helper/capacity/CVX/CTRL')
        require(self.checks == self.u64('fx_checks') == self.cfg['checks'] and self.u64('fx_completed') == o.DONE, 'Full final oracle')
        return dict(status='PASS_UNIT_FOF_E64_SUFFIX', scenario=self.spec['scenario'], sew=self.sew, rows=self.rows, retired=self.retired,
                    last_cycle=self.last_cycle, checks=self.checks, checkpoints=self.points, actions=self.actions,
                    original_helper_instructions=11, capacity_instructions=3, target_attempts=1,
                    returned_vl=self.cfg['returned_vl'], post_helper_vl=8, actual_handler_csrs=self.handler,
                    allowed_undefined_indices=[], output_allocation=130,
                    data_bytes=8192, page_table_bytes=12288, mask_bytes=16, original_guards=[0, 9],
                    postexit_park=self.parked, ctrl=self.ctrl, target_architectural_exceptions=0,
                    zero_MMU_or_physical_requests_proved=False, Linux_signal_equivalence=False)

def analyze(path, spec):
    q = Checker(spec)
    try:
        with Path(path).open() as stream:
            rows = csv.DictReader(stream)
            require(rows.fieldnames == FIELDS, 'Actual CSV header')
            for row in rows:
                q.row(row)
        return q.finish()
    except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
        return dict(status='NOT_PASS_FOF', error=str(error), rows=q.rows, retired=q.retired,
                    last_cycle=q.last_cycle, checks=q.checks, actions=q.actions, checkpoints=q.points)
