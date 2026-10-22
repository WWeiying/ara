import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import collect_vmacc_c_fifo773 as q
import test_qualify_queue_mask_source_lifetime_terminal as fixtures


class RealReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = q.runner.preflight()
        cls.ref = q.p.old.build.parse_spike_commits(Path(cls.pre['reference']))[5:5 + 36339]
        cls.rows = []
        for i, c in enumerate(cls.ref):
            values = {k: v for k, v in c.gpr_writes.items() if k}
            rd = next(iter(values), 0)
            addr = rm = wm = data = 0
            access = q.common.scalar_memory(c.instruction)
            if access is not None:
                kind, size = access
                addr, value = c.memory_accesses[0]
                mask = ((1 << size) - 1) << (addr & 7)
                if kind == 'read':
                    rm = mask
                else:
                    wm, data = mask, value
            cls.rows.append(dict(event='retire', order=str(i), pc=hex(c.pc), insn=hex(c.instruction),
                trap='0', rd=str(rd), rd_wdata=hex(values.get(rd, 0)), mem_addr=hex(addr),
                mem_rmask=hex(rm), mem_wmask=hex(wm), mem_wdata=hex(data)))
        cls.mapping = {seq: i for seq, i in enumerate(i for i, c in enumerate(cls.ref) if c.vector_writes)}
        cls.activities = {}
        records = []
        for seq, i in cls.mapping.items():
            c = cls.ref[i]
            source = 4 if c.instruction & 127 == 7 else 1 if c.instruction >> 26 == 0x2d else 0
            ws = []
            for reg, value in c.vector_writes.items():
                ws.extend(q.vc.VectorWrite(**dict(w.__dict__, instruction=c.instruction))
                          for w in fixtures.writes(reg, value, seq, source))
            cls.activities[seq] = SimpleNamespace(instruction=c.instruction, vl=c.vector_vl,
                vstart=0, allocations=1, completions=1, writes=ws)
            records.append(dict(pc=hex(c.pc), instruction=hex(c.instruction), status='PASS',
                unknown_write_bytes=0, skipped_unknown_bytes=0, mismatch_count=0))
        cls.result = dict(status='PASS', compared_instructions=19, skipped_unknown_bytes=0,
            non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024, trapped_requests=[],
            first_mismatch=None, incomplete_requests=[], unretired_requests=[],
            unobservable_instructions=0, instructions=records,
            compared_bytes=sum(len(c.vector_writes) * 128 for c in cls.ref))

    def native(self, activities=None, result=None):
        with patch.object(q.runner, 'preflight', return_value=self.pre), \
             patch.object(q.vc, 'compare_vector_commits', return_value=result or self.result), \
             patch.object(q.vc, '_parse_vector_trace', return_value=(4, 1024, activities or self.activities)), \
             patch.object(q.vc, '_parse_architecture_mapping', return_value=({}, {}, {})), \
             patch.object(q.vc, '_map_architecture_retires', return_value={}), \
             patch.object(q.vc, '_map_spike_commits', return_value=self.mapping):
            return q.native(Path('/fixture-not-DUT'), self.ref)

    def test_full_real_reference_signature(self):
        self.assertEqual(q.footprint(self.rows, self.pre['symbols'])['checks'], 2344)

    def test_full_native_known_tail_reference_fixture(self):
        result, proof = self.native()
        self.assertEqual(proof['required_active_bytes'], 18420)
        self.assertEqual(proof['observed_known_bytes'], result['compared_bytes'])
        self.assertEqual(len(proof['allocations']), 12)

    def test_full_compressed_scalar_memory(self):
        q.memory.scalar_memory_exact(self.rows, self.ref)

    def test_missing_retirement(self):
        with self.assertRaises(ValueError): q.footprint(self.rows[:-1], self.pre['symbols'])

    def test_wrong_trap(self):
        rows = copy.deepcopy(self.rows); rows[0]['trap'] = '1'
        with self.assertRaises(ValueError): q.footprint(rows, self.pre['symbols'])

    def test_wrong_tohost(self):
        rows = copy.deepcopy(self.rows); rows[-1]['mem_wdata'] = '3'
        with self.assertRaises(ValueError): q.footprint(rows, self.pre['symbols'])

    def test_corrupt_source_readback(self):
        rows = copy.deepcopy(self.rows)
        r = next(r for r in reversed(rows) if int(r['mem_addr'], 16) == self.pre['symbols']['vmacc_ring_source'] and int(r['mem_rmask'], 16))
        r['rd_wdata'] = hex(int(r['rd_wdata'], 16) ^ 1)
        self.assertEqual(sum(a != b for a, b in zip(rows, self.rows)), 1)
        with self.assertRaises(ValueError): q.footprint(rows, self.pre['symbols'])

    def mutate_native(self, field, value):
        a = copy.deepcopy(self.activities)
        seq = next(s for s, x in a.items() if x.instruction >> 26 == 0x2d)
        w = a[seq].writes[0]
        a[seq].writes[0] = q.vc.VectorWrite(**dict(w.__dict__, **{field: value}))
        return a

    def test_wrong_source(self):
        with self.assertRaises(ValueError): self.native(self.mutate_native('source', 0))

    def test_unknown_bytes(self):
        with self.assertRaises(ValueError): self.native(self.mutate_native('known_be', 0))

    def test_wrong_eew(self):
        with self.assertRaises(ValueError): self.native(self.mutate_native('eew', 1))

    def test_wrong_owner(self):
        with self.assertRaises(ValueError): self.native(self.mutate_native('arch_seq', 999))

    def test_missing_active_byte(self):
        with self.assertRaises(ValueError): self.native(self.mutate_native('be', 254))

    def test_duplicate_write(self):
        a = copy.deepcopy(self.activities); a[0].writes.append(a[0].writes[0])
        with self.assertRaises(ValueError): self.native(a)

    def test_wrong_tail(self):
        a = copy.deepcopy(self.activities); seq = max(a); w = a[seq].writes[-1]
        a[seq].writes[-1] = q.vc.VectorWrite(**dict(w.__dict__, data=w.data ^ 1))
        with self.assertRaises(ValueError): self.native(a)

    def test_missing_completion(self):
        a = copy.deepcopy(self.activities); a[0].completions = 0
        with self.assertRaises(ValueError): self.native(a)

    def test_skipped_unknown_rejected(self):
        r = dict(self.result, skipped_unknown_bytes=1)
        with self.assertRaises(ValueError): self.native(result=r)


class RunGateTests(unittest.TestCase):
    def test_command_exact_no_recompile(self):
        c = q.runner.command(q.life.OUT / 'unit-not-run')
        self.assertEqual(c[0], str(q.life.IMAGE)); self.assertIn('+NO_FSDB', c)
        self.assertIn('line+cond+fsm+tgl+branch', c); self.assertEqual(q.runner.BUDGET, 600)

    def test_existing_output_rejected(self):
        with self.assertRaises(ValueError): q.runner.prepare(q.life.OUT)

    def test_preflight_hash_drift(self):
        with patch.object(q.life, 'read_bound', side_effect=ValueError('pin drift')):
            with self.assertRaises(ValueError): q.runner.preflight()

    def test_lifecycle_positive(self):
        rows, vectors = fixtures.GateTests().lifecycle_fixture()
        self.assertEqual(q.control.lifecycle(rows, vectors)['requests'], 1)

    def test_lifecycle_owner_drift(self):
        rows, vectors = fixtures.GateTests().lifecycle_fixture(); vectors[-1]['arch_seq'] = '99'
        with self.assertRaises(ValueError): q.control.lifecycle(rows, vectors)

    def test_terminal_timeout(self):
        state = dict(status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED', returncode=-9, timeout=True)
        with patch.object(Path, 'read_bytes', return_value=json.dumps(state).encode()):
            with self.assertRaises(ValueError): q.terminal(Path('/fixture'), {})


if __name__ == '__main__':
    unittest.main()
