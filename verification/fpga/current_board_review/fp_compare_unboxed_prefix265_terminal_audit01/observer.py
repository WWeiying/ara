"""Original CSV dictionaries are delivered unchanged to the sealed checker."""
from collections import Counter
import hashlib


def observer_class(transport):
    class Observer(transport.Observer):
        def __init__(self, spec, gold):
            self.spec, self.gold = spec, gold
            self.count, self.pcs = Counter(), Counter()
            self.pending, self.uops = {}, {}
            self.requests, self.arch, self.retvec = [], [], []
            self.first = self.last = -1
            self.maxcvx = self.maxuop = 0
            self.before, self.after = hashlib.sha256(), hashlib.sha256()
            self.regs = [0]*32
            self.helper, self.capacity, self.prelude, self.rawft0, self.restores = [], [], [], [], []
            self.exit = None
            self.lookup = {r['pc']: (op, j) for op, rr in enumerate(spec['routines']) for j, r in enumerate(rr)}
            self.unused = [(rr[0]['pc'], rr[-1]['pc']+len(rr[-1]['insn'])//2) for rr in spec['routines'][5:]]
            self.step = self.call = 0

        def retirement(self, row, cycle, insn, order):
            s = self.spec
            pc, rd, value = int(row['pc'], 16), int(row['rd']), int(row['rd_wdata'], 16)
            address, rm, wm, wd = (int(row[k], 16) for k in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
            assert int(s['code'][f'{pc:x}']['insn'], 16) == insn
            assert pc != s['symbols']['trap_entry'] and not any(lo <= pc < hi for lo, hi in self.unused)
            self.pcs[pc] += 1
            if self.exit:
                assert pc == s['park']['pc'] and not (rd or rm or wm)
                return
            pair = self.lookup.get(pc)
            if self.step:
                op = self.gold['rows'][self.call-1]['op']
                assert pair == (op, self.step) and order == self.helper[-1]['order']+1
            if pair:
                op, j = pair
                assert op < 5 and j == self.step
                if j == 0:
                    assert self.call < 265 and op == self.gold['rows'][self.call]['op']
                    self.call += 1
                g = self.gold['rows'][self.call-1]
                delta = 2 if op == 4 else 0
                if op == 4 and j == 7:
                    assert insn == 0xf2038053 and self.regs[7] == 0
                    self.rawft0.append(dict(call=self.call, pc=hex(pc), order=order, cycle=cycle,
                                           encoding=hex(insn), integer_source=7, source_value=0))
                if j == 9+delta:
                    assert (rd, value) == (10, 0)
                    self.count['returned_vstart_zero'] += 1
                if j == 10+delta:
                    assert (rd, value) == (6, g['flags'])
                    self.count['flags_checked'] += 1
                if j == 13+delta:
                    assert self.regs[30] == 0
                    self.restores.append(dict(call=self.call, pc=hex(pc), order=order, source_value=0))
                self.helper.append(dict(call=self.call, op=op, index=j, pc=hex(pc), order=order, cycle=cycle))
                self.step = (j+1) % len(s['routines'][op])
            for name, values, records in (('capacity', s['capacity'], self.capacity), ('prelude', s['prelude'], self.prelude)):
                if pc in [r['pc'] for r in values]:
                    assert len(records) < len(values) and pc == values[len(records)]['pc']
                    records.append(dict(pc=hex(pc), order=order, rd=rd, value=value))
            for name, site in s['sites'].items():
                if pc == site: self.count[name] += 1
            if pc == s['exit_store']['pc'] or address == s['exit_address'] and wm:
                assert pc == s['exit_store']['pc'] and address == s['exit_address'] and wm == 255 and wd == 0
                assert self.call == 265 and self.step == 0
                self.exit = dict(pc=hex(pc), order=order, cycle=cycle, address=hex(address), value=0)
            if rd: self.regs[rd] = value

        def finish(self):
            c = self.count
            assert not self.pending and not self.uops and self.retvec == self.requests == self.arch
            assert c['rows'] == c['unmodified_delivered_rows'] and self.before.digest() == self.after.digest()
            assert self.exit and self.call == 265 and self.step == 0 and len(self.helper) == 4587
            assert len(self.rawft0) == 41 and len(self.restores) == 265
            assert len(self.capacity) == 3 and len(self.prelude) == 6
            assert c['returned_vstart_zero'] == c['flags_checked'] == 265
            assert [c[k] for k in ('mask', 'a', 'b', 'output', 'bits', 'guard0', 'guard1')] == [33920, 4240, 4240, 34450, 4240, 265, 265]
            return dict(rows=c['rows'], first_cycle=self.first, last_cycle=self.last, retire_count=c['retire'],
                        vector_retire_count=len(self.retvec), cvx_request_count=c['cvx_req'],
                        cvx_response_count=c['cvx_resp'], cvx_max_inflight=self.maxcvx, cvx_replay_count=0,
                        arch_request_replay_count=0, cvx_exception_count=0, architecture_request_count=len(self.arch),
                        backend_uop_alloc_count=c['uop_alloc'], backend_uop_done_count=c['uop_done'], backend_uop_max_inflight=self.maxuop)

        def evidence(self):
            return dict(original_rows_delivered_unmodified=self.count['unmodified_delivered_rows'],
                        before_sha256=self.before.hexdigest(), after_sha256=self.after.hexdigest(),
                        counts=dict(self.count), actual_pc_counts={hex(k): v for k, v in self.pcs.items()},
                        helper=self.helper, capacity=self.capacity, prelude=self.prelude, rawft0_instruction_sources=self.rawft0,
                        restores=self.restores, exit=self.exit, unused_full_ranges=self.unused,
                        unused_helper_retirements=0, raw_FPR_payload_directly_observed=False,
                        post_restore_csr_state_directly_measured=False)
    return Observer
