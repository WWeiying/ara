import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import qualify_narrow_source_group_terminal as q


class QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = q.life.read_bound(q.PRE / 'preflight-manifest.json', q.PRE_SEAL)
        cls.symbols = cls.pre['symbols']
        cls.reference = q.p.shared.parse_spike_commits(q.PRE / 'spike.trace')
        cls.prepared = {'case':q.p.NAME}

    def observed_fixture(self):
        rows = []; active = False
        for c in self.reference:
            if c.pc == 0x80000000: active = True
            if not active: continue
            rd, value = next(iter(c.gpr_writes.items()), (0, 0))
            r = dict(event='retire', cycle=str(len(rows)), order=str(len(rows)), port='0', trans_id='-1',
                pc='%016x' % c.pc, insn='%08x' % c.instruction, trap='0', rd=str(rd), rd_wdata=hex(value),
                mem_addr='0', mem_rmask='0', mem_wmask='0', mem_wdata='0')
            access = q.common.scalar_memory(c.instruction)
            if access and c.memory_accesses:
                kind, size = access; address, data = c.memory_accesses[0]
                r['mem_addr'] = hex(address); r['mem_' + ('rmask' if kind == 'read' else 'wmask')] = hex(((1 << size) - 1) << (address & 7))
                if kind == 'write': r['mem_wdata'] = hex(data)
            rows.append(r)
            if (self.symbols['tohost'], 1) in c.memory_accesses: break
        return rows

    def test_real_reference_all_memory_and_elf(self):
        result = q.observed(self.observed_fixture(), self.symbols, q.PRE)
        self.assertEqual((result['checks'], result['explicit_readback_bytes'], result['handler_store_words']), (2130, 2256, 8))

    def corrupt_read(self, name, offset):
        rows = self.observed_fixture(); found = False
        for r in rows:
            if int(r['mem_rmask'], 16) and int(r['mem_addr'], 16) == self.symbols[name] + offset:
                r['rd_wdata'] = hex(int(r['rd_wdata'], 16) ^ 1); found = True
        self.assertTrue(found); return rows

    def test_csr_change_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CSR preservation'):
            q.observed(self.corrupt_read('ng_after', 8), self.symbols, q.PRE)

    def test_rd_change_rejected(self):
        with self.assertRaisesRegex(ValueError, 'RD sentinel'):
            q.observed(self.corrupt_read('ng_rd', 0), self.symbols, q.PRE)

    def test_wrong_cause_tval_mepc_rejected(self):
        for offset in (8, 16, 24):
            with self.assertRaisesRegex(ValueError, 'trap ledger'):
                q.observed(self.corrupt_read('ng_trap', offset), self.symbols, q.PRE)

    def test_buffer_and_guard_rejected(self):
        for name, offset in (('ng_source', 8), ('ng_dump', 8), ('ng_recovered', 0), ('ng_recovered', 16)):
            with self.assertRaisesRegex(ValueError, 'Buffer/guard'):
                q.observed(self.corrupt_read(name, offset), self.symbols, q.PRE)

    def test_missing_readback_rejected(self):
        rows = [r for r in self.observed_fixture() if not
            (int(r['mem_rmask'], 16) and int(r['mem_addr'], 16) == self.symbols['ng_source'])]
        for i, r in enumerate(rows): r['order'] = str(i)
        with self.assertRaisesRegex(ValueError, 'readback'): q.observed(rows, self.symbols, q.PRE)

    def test_foreign_retirement_opcode_rejected(self):
        rows = self.observed_fixture(); rows[0]['insn'] = '00000013'
        with self.assertRaisesRegex(ValueError, 'sealed ELF'): q.observed(rows, self.symbols, q.PRE)

    def test_extra_terminal_rejected(self):
        rows = self.observed_fixture(); rows.append(dict(rows[-1], order=str(len(rows))))
        with self.assertRaisesRegex(ValueError, 'tohost'): q.observed(rows, self.symbols, q.PRE)

    def test_handler_protected_register_rejected(self):
        rows = self.observed_fixture()
        r = next(r for r in rows if int(r['pc'], 16) == self.symbols['ng_handler_begin'])
        r['rd'] = '28'
        with self.assertRaisesRegex(ValueError, 'protected scalar'): q.observed(rows, self.symbols, q.PRE)

    def lifecycle_fixture(self):
        rows, vectors = [], []
        def row(event, seq, cycle, word, trap=0):
            rows.append(dict(event=event, order=str(seq), cycle=str(cycle), insn=hex(word),
                trans_id=str(seq), pc='0', trap=str(trap), port='0'))
        for i in range(2):
            cycle = i * 10; word = q.p.opcode(i) if i < 1 else 0x0341bc57
            row('arch_start', i, cycle, word); row('cvx_req', i, cycle + 1, word)
            if i == 1:
                row('uop_alloc', i, cycle + 2, word); row('uop_done', i, cycle + 3, word)
                for event, t in (('alloc', cycle + 2), ('done', cycle + 3)):
                    vectors.append(dict(event=event, cycle=str(t), arch_seq=str(i), vid='0', insn=hex(word),
                        nr_lanes='4', vlen_bits='1024', use_vd='1', vd='24', eew='0', vl='8', vstart='0'))
            row('cvx_resp', -1, cycle + 4, 0, int(i < 1)); rows[-1]['trans_id'] = str(i)
        row('retire', 0, 135, 0x0341bc57); rows[-1]['pc'] = hex(self.symbols['ng_recovery'])
        return rows, vectors

    def test_single_no_backend_rejections_and_recovery(self):
        rows, vectors = self.lifecycle_fixture(); result = q.lifecycle(rows, vectors, self.symbols)
        self.assertEqual((result['exceptions'], result['backend_uops']), (1, 1))

    def test_missing_rejection_rejected(self):
        rows, vectors = self.lifecycle_fixture(); rows[2]['trap'] = '0'
        with self.assertRaisesRegex(ValueError, 'single rejected'): q.lifecycle(rows, vectors, self.symbols)

    def test_illegal_csr_backend_rejected(self):
        rows, vectors = self.lifecycle_fixture()
        rows.insert(2, dict(rows[0], event='uop_alloc', cycle='1'))
        with self.assertRaises(ValueError): q.lifecycle(rows, vectors, self.symbols)

    def test_illegal_native_activity_rejected(self):
        rows, vectors = self.lifecycle_fixture()
        vectors.insert(0, dict(vectors[0], arch_seq='0', cycle='2', insn=hex(q.p.opcode(0))))
        with self.assertRaisesRegex(ValueError, 'Rejected narrowing'): q.lifecycle(rows, vectors, self.symbols)

    def test_metadata_and_missing_done_rejected(self):
        rows, vectors = self.lifecycle_fixture(); vectors[1]['vl'] = '128'
        with self.assertRaisesRegex(ValueError, 'metadata drift'): q.lifecycle(rows, vectors, self.symbols)
        rows, vectors = self.lifecycle_fixture()
        with self.assertRaisesRegex(ValueError, 'lifecycle differs'): q.lifecycle(rows, vectors[:-1], self.symbols)

    def test_unknown_return_and_timeout_rejected(self):
        for state in ({}, dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=None),
                      dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, timeout=True)):
            with self.assertRaisesRegex(ValueError, 'OS return'): q.terminal(state, {}, {}, self.prepared)

    def test_tracer_exact_single_exceptions(self):
        rows = self.observed_fixture()
        text = '\n'.join('0ns %s M %s 0 %s' % (r['cycle'], r['pc'], r['insn']) for r in rows) + '\n'
        text += '\n'.join('Exception @ %d, PC: %016x, Cause: Illegal Instruction, tval: %016x' %
            (i, self.symbols[n], q.p.opcode(i)) for i, n in enumerate(q.p.FAULTS))
        self.assertEqual(q.tracer_exact(text, rows, self.symbols)['exceptions'], 1)
        with self.assertRaises(ValueError): q.tracer_exact(text.replace('Illegal Instruction', 'Load Access Fault', 1), rows, self.symbols)

    def test_uvm_errors_not_silently_ignored(self):
        summary = '[ARA_CONTRACT] requests=2 responses=2 exceptions=1 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'
        q.logs(summary, 'Core Test *** SUCCESS ***\nUVM_ERROR : 0\nUVM_FATAL : 0', dict(requests=2))
        with self.assertRaisesRegex(ValueError, 'UVM error'):
            q.logs(summary, 'Core Test *** SUCCESS ***\nUVM_ERROR x [NO_TRAFFIC]', dict(requests=2))

    def native_fixture(self):
        wanted = {i: c for i, c in enumerate(self.reference) if c.vector_writes}
        rejected = list(range(1)); activities = {}
        for seq, c in wanted.items():
            size = 8 if c.instruction == 0x0341bc57 else 512; writes = []
            for reg, value in c.vector_writes.items():
                for word in range(4 if size == 512 else 1):
                    for lane in range(4):
                        be, data = 0, 0
                        for b in range(8):
                            reverse = ((b & 1) << 2) | (b & 2) | ((b >> 2) & 1)
                            natural = word * 32 + reverse * 4 + lane
                            if (reg-min(c.vector_writes))*128+natural < size:
                                be |= 1 << b; data |= ((value >> (8 * natural)) & 255) << (8 * b)
                        writes.append(q.vc.VectorWrite(len(writes), 1, seq, 0, lane,
                            0 if size == 8 else 4, c.instruction, 0, reg * 4 + word, be, data, be))
            activities[seq] = SimpleNamespace(writes=writes, eew=0, vl=size, vstart=0)
        vector = dict(status='PASS', compared_instructions=3, compared_bytes=1032, trapped_requests=rejected,
            skipped_unknown_bytes=0, non_bit_exact_instructions=0, unobservable_instructions=0,
            first_mismatch=None, incomplete_requests=[], unretired_requests=[],
            instructions=[dict(pc=hex(c.pc), instruction=hex(c.instruction), compared_bytes=8 if c.instruction == 0x0341bc57 else 512)
                          for c in wanted.values()])
        return vector, dict(rejected_arch_seqs=rejected), activities, wanted

    def native_check(self, vector, control, activities, wanted):
        with mock.patch.object(q.vc, '_parse_vector_trace', return_value=(4, 1024, activities)), \
             mock.patch.object(q.vc, '_parse_architecture_mapping', return_value=([], [], set(control['rejected_arch_seqs']))), \
             mock.patch.object(q.vc, '_map_architecture_retires', return_value={}), \
             mock.patch.object(q.vc, '_map_spike_commits', return_value={seq: seq for seq in wanted}):
            q.native_exact(vector, control, self.reference, q.life.OUT/'synthetic-narrow-terminal')

    def test_exact_1032_native_bytes_with_real_dataclass(self): self.native_check(*self.native_fixture())

    def test_unknown_wrong_source_duplicate_native_byte(self):
        for mutation in ('unknown', 'source', 'duplicate', 'data'):
            vector, control, activities, wanted = self.native_fixture()
            a = next(iter(activities.values())); w = a.writes[0]
            if mutation == 'unknown': a.writes[0] = replace(w, known_be=0)
            elif mutation == 'source': a.writes[0] = replace(w, source=3)
            elif mutation == 'duplicate': a.writes.append(w)
            else: a.writes[0] = replace(w, data=w.data ^ 1)
            with self.assertRaises(ValueError): self.native_check(vector, control, activities, wanted)

    def test_actual_target_bit_shape_and_zero_hold(self):
        targets=self.pre['targets'];run=q.life.OUT/'synthetic-target-run'
        single=dict(tests=[str(run/'code.vdb')],metrics={})
        for t in targets:
            single['metrics'].setdefault(t['metric'],{})[t['scope']]=dict(
                width=t['width'],checksum=t['checksum'],bits='0x0')
        self.assertFalse(any(h['actual_single_hit'] for h in q.target_hits(single,targets,run)))
        for t in targets:
            single['metrics'][t['metric']][t['scope']]['bits']=hex(1<<(t['width']-1-t['point']['raw_index']))
        self.assertTrue(all(h['actual_single_hit'] for h in q.target_hits(single,targets,run)))
        single['metrics']['cond'][targets[0]['scope']]['checksum']='foreign'
        with self.assertRaises(ValueError):q.target_hits(single,targets,run)

    def test_foreign_target_singleton_and_coordinates_rejected(self):
        run=q.life.OUT/'synthetic-target-run';targets=copy.deepcopy(self.pre['targets'])
        with self.assertRaises(ValueError):q.target_hits(dict(tests=['/foreign/code.vdb']),targets,run)
        targets[0]['point']['raw_index']=225
        with self.assertRaises(ValueError):q.target_hits(dict(tests=[str(run/'code.vdb')]),targets,run)

    def test_collect_bad_terminal_stops_before_trace_or_output(self):
        with tempfile.TemporaryDirectory(dir=q.life.OUT) as temporary:
            root=Path(temporary);run=root/'run';run.mkdir();out=root/'post'
            for name in ('simulation-status.json','manifest.json','started.json'):(run/name).write_text('{}')
            sidecar=run.with_name(run.name+'.prepared.json')
            plan=dict(status=q.STATUS,run=str(run),prepared=str(sidecar),prepared_seal='b'*64,
                preflight=str(q.PRE/'preflight-manifest.json'),preflight_seal=q.PRE_SEAL,
                pins={'/synthetic/pin':'a'*64},raw_gain_requires_latest_formal_population_at_least=735,
                coverage_admitted=False,simulations_started=False,native_cycle_qualified=False,
                expected_checks=2130,exact_illegal_traps=1,static_baseline=735)
            with mock.patch.object(q.life,'OUT',root),mock.patch.object(q.life,'check'), \
                 mock.patch.object(q.life,'read_bound',side_effect=[plan,self.prepared]), \
                 mock.patch.object(q.common,'read_csv') as read_csv:
                with self.assertRaisesRegex(ValueError,'OS return'):q.collect(root/'plan.json','a'*64,out)
                read_csv.assert_not_called();self.assertFalse(out.exists())



if __name__ == '__main__': unittest.main()
