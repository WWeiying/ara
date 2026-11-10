#!/usr/bin/env python3
"""Host mutations of the actual immutable overlapping PV maintenance trace."""
import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('pv_boundary_audit', Path(__file__).with_name('pv_boundary_audit.py'))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class BoundaryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = a.frozen_runner()
        _, cls.checker, _ = cls.runner.legacy()
        cls.old = cls.checker.old
        cls.trace = a.read_trace(a.VECTOR)
        cls.mixed = [r for r in cls.trace if r['arch_seq'] == '926']
        path = cls.runner.BUILD/'vectors/vectors.json'
        receipt = cls.runner.b.read(cls.runner.BUILD/'build.json')
        cls.runner.b.verify({path: receipt['artifacts'][str(path)]})
        vectors = cls.runner.b.read(path)
        cls.case = next(s for s in cls.checker.cases.attempts(vectors['cases']) if s['kind'] == 'mixed')

    def rows(self):
        return copy.deepcopy(self.mixed)

    def check_data(self, rows):
        uops = a.split_uops(rows)
        self.assertEqual(len(uops), 7)
        for index, uop in enumerate(uops[:-1]):
            reg = 8+index
            chunk = self.case['source'][64*index:64*(index+1)]
            data = {(lane, reg*4+word): self.old.word16(chunk, lane, word)
                    for lane in range(4) for word in range(4)}
            self.old.audit_uop(uop, reg, 64, 1, data, source=3)
        d = self.case['dimension']
        data = {(lane, head*8+word): self.old.word16(self.case['expected'][head*d:(head+1)*d], lane, word)
                for lane in range(4) for head in range(self.case['heads']) for word in range(d//16)}
        self.old.audit_uop(uops[-1], 0, 256, 1, data)

    def write_index(self, rows, vd='8'):
        return next(i for i, r in enumerate(rows) if r['event'] == 'write' and r['vd'] == vd)

    def test_actual_overlap_original_failure_and_exact_data(self):
        with self.assertRaisesRegex(ValueError, '^'+a.SERIAL_ERROR+'$'):
            self.old.split_uops(self.mixed)
        self.check_data(self.mixed)
        self.assertEqual(self.case['id'], 15)
        uops = a.split_uops(self.mixed)
        self.assertEqual([int(u[0]['vd']) for u in uops], [8, 9, 10, 11, 12, 13, 0])
        self.assertLess(int(uops[1][0]['cycle']), int(uops[0][-1]['cycle']))
        self.assertEqual((uops[-2][-1]['cycle'], uops[-1][0]['cycle']), ('3088746', '3088748'))
        self.assertEqual(self.mixed, self.rows())

    def test_global_ownership_and_pv_count(self):
        uops = a.split_active(self.trace)
        self.assertEqual(len(uops), 706)
        self.assertEqual(sum(u[0]['insn'] == a.PV_INSN for u in uops), 30)

    def test_allocation_not_completion_order(self):
        uops = a.split_uops(self.mixed)
        rows = [dict(uops[0][0], cycle='10'), dict(uops[1][0], cycle='11'),
                dict(uops[1][-1], cycle='12'), dict(uops[0][-1], cycle='13')]
        self.assertEqual([u[0]['vd'] for u in a.split_active(rows)], ['8', '9'])

    def test_vid_reuse_only_after_done(self):
        rows = self.rows()
        rows[1]['vid'] = rows[0]['vid']
        with self.assertRaisesRegex(ValueError, 'reused before done'):
            a.split_uops(rows)
        uop = a.split_uops(self.mixed)[0]
        rows = [dict(uop[0], cycle='10'), dict(uop[-1], cycle='11'),
                dict(uop[0], cycle='11'), dict(uop[-1], cycle='12')]
        self.assertEqual(len(a.split_active(rows)), 2)

    def test_swapped_vid_and_identity_fields(self):
        for key, value in dict(vid='1', vd='9', arch_seq='925', insn='048570db', use_vd='0',
                               eew='2', vl='63', vstart='1', nr_lanes='2', vlen_bits='512').items():
            with self.subTest(field=key):
                rows = self.rows()
                rows[self.write_index(rows)][key] = value
                with self.assertRaises(ValueError):
                    a.split_uops(rows)

    def test_full_identity_swap_still_fails_exact_data(self):
        rows = self.rows()
        for r in rows:
            if r['vd'] in ('8', '9'):
                r['vd'] = '9' if r['vd'] == '8' else '8'
        with self.assertRaisesRegex(ValueError, 'identity/geometry drift'):
            self.check_data(rows)

    def test_late_or_unowned_write(self):
        rows = self.rows()
        rows.append(dict(rows[self.write_index(rows, '0')], cycle=rows[-1]['cycle']))
        with self.assertRaisesRegex(ValueError, 'Unowned/late'):
            a.split_uops(rows)
        rows = self.rows()
        rows.insert(0, dict(rows[self.write_index(rows)], cycle=rows[0]['cycle']))
        with self.assertRaisesRegex(ValueError, 'Unowned/late'):
            a.split_uops(rows)

    def test_missing_done_and_duplicate_done(self):
        rows = self.rows()[:-1]
        with self.assertRaisesRegex(ValueError, 'Unfinished'):
            a.split_uops(rows)
        rows = self.rows()
        rows.append(dict(rows[-1]))
        with self.assertRaisesRegex(ValueError, 'Unowned/late'):
            a.split_uops(rows)
        rows = [r for r in self.rows() if not (r['event'] == 'done' and r['vd'] == '8')]
        with self.assertRaisesRegex(ValueError, 'reused before done'):
            a.split_uops(rows)

    def test_unknown_event_missing_alloc_and_empty(self):
        rows = self.rows()
        rows[2]['event'] = 'discard'
        for bad in (rows, self.rows()[1:], []):
            with self.subTest(rows=len(bad)), self.assertRaises(ValueError):
                a.split_uops(bad)

    def test_nonmonotonic_cycle_and_completion_at_write(self):
        rows = self.rows()
        rows[1]['cycle'] = str(int(rows[0]['cycle'])-1)
        with self.assertRaisesRegex(ValueError, 'Nonmonotonic'):
            a.split_uops(rows)
        uop = copy.deepcopy(a.split_uops(self.mixed)[0])
        uop[-1]['cycle'] = uop[-2]['cycle']
        with self.assertRaisesRegex(ValueError, 'Completion before/at write'):
            a.split_active(uop)

    def test_final_allocation_cannot_overlap_or_tie_maintenance_done(self):
        for delta in (-1, 0):
            with self.subTest(delta=delta):
                rows = self.rows()
                last_done = next(i for i, r in enumerate(rows) if r['event'] == 'done' and r['vd'] == '13')
                final = rows.pop(last_done+1)
                final['cycle'] = str(int(rows[last_done]['cycle'])+delta)
                rows.insert(last_done, final)
                with self.assertRaisesRegex(ValueError, 'before all maintenance done'):
                    a.split_uops(rows)

    def test_corrupt_maintenance_and_final_data_source_and_enable(self):
        for vd in ('8', '13', '0'):
            for key, value in dict(wdata='deadbeefdeadbeef', source='2', be='7f', addr='999').items():
                with self.subTest(vd=vd, field=key):
                    rows = self.rows()
                    rows[self.write_index(rows, vd)][key] = value
                    with self.assertRaises(ValueError):
                        self.check_data(rows)

    def test_missing_and_duplicate_write(self):
        for duplicate in (False, True):
            rows = self.rows()
            i = self.write_index(rows)
            if duplicate:
                rows.insert(i, dict(rows[i]))
            else:
                rows.pop(i)
            with self.subTest(duplicate=duplicate), self.assertRaises(ValueError):
                self.check_data(rows)

    def test_schema_and_placeholder_payload(self):
        for key, value in dict(extra='0', cycle='-1', vid='8', insn='0485705', be='gg').items():
            rows = self.rows()
            rows[0][key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                a.split_uops(rows)
        rows = self.rows()
        rows[-1]['wdata'] = '0000000000000001'
        with self.assertRaisesRegex(ValueError, 'Non-write carries'):
            a.split_uops(rows)

    def test_cross_architecture_vid_conflict_not_hidden_by_grouping(self):
        rows = self.rows()
        rows[1].update(vid='0', arch_seq='927')
        with self.assertRaisesRegex(ValueError, 'reused before done'):
            a.split_active(rows)

    def test_scoped_original_failure_and_restore(self):
        original, failures = self.old.split_uops, []
        with a.scoped_splitter(self.old, failures):
            self.assertEqual(self.old.split_uops(self.mixed), a.split_uops(self.mixed))
            lone = a.split_uops(self.mixed)[-1]
            self.assertEqual(self.old.split_uops(lone), original(lone))
        self.assertIs(self.old.split_uops, original)
        self.assertEqual(failures, [dict(arch_seq=926, error=a.SERIAL_ERROR)])
        with self.assertRaisesRegex(RuntimeError, 'sentinel'):
            with a.scoped_splitter(self.old, []):
                raise RuntimeError('sentinel')
        self.assertIs(self.old.split_uops, original)

    def test_unexpected_original_failure_is_not_masked(self):
        def fail(_rows):
            raise ValueError('different failure')
        old = SimpleNamespace(split_uops=fail)
        with self.assertRaisesRegex(ValueError, 'Unexpected original'):
            with a.scoped_splitter(old, []):
                old.split_uops(self.mixed)
        self.assertIs(old.split_uops, fail)

    def test_independent_protocol_exact_match_required(self):
        fresh = {'status': 'PASS', 'issues': [], 'backend_counts': {'alloc': 706}}
        identity = dict.fromkeys(('elf_sha256', 'simv_sha256', 'sim_image_sha256',
                                  'log_sha256', 'vector_trace_sha256'), 'pinned-by-sealed-check')
        old = SimpleNamespace(smoke=SimpleNamespace(check_protocol=lambda *args: None),
                              uvm_dut=SimpleNamespace(check_real_uvm_log=lambda *args, **kw: fresh))
        self.assertEqual(a.check_protocol(old, fresh | identity, {}, {}, None, None), fresh)
        for proof in (fresh | identity | {'extra': 0}, fresh | identity | {'backend_counts': {'alloc': 705}}):
            with self.assertRaisesRegex(ValueError, 'recomputation mismatch'):
                a.check_protocol(old, proof, {}, {}, None, None)

    def test_pinned_anchor_rejects_drift_before_import(self):
        with patch.object(a, 'sha', return_value='0'*64):
            with self.assertRaisesRegex(ValueError, 'Audit anchor drift'):
                a.frozen_runner()


if __name__ == '__main__':
    unittest.main(verbosity=2)
