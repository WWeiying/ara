"""Offline admission gates; no simulator, no publication, no new qualification."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import admit_gather_war798 as a


class Admission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = a.life.read_bound(a.QUAL, a.Q_SHA)
        cls.before, cls.bt, cls.ledger, _ = a.g.baseline()
        def doc(name):
            p = a.QUAL.parent / name
            return a.life.read_bound(p, cls.q['input_pins'][str(p)])
        cls.single, cls.st, cls.at = (doc(n) for n in
            ('single-bits.json', 'single-toggle-bits.json', 'proposed-combined-toggle-bits.json'))
        cls.targets = a.life.read_bound(a.RUN.with_name(a.RUN.name + '.prepared.json'), a.PREPARED_SHA)['targets']

    def test_actual_sealed_successor_qualification(self):
        a.qualification(self.q)

    def test_failed_status_and_identity_flags_rejected(self):
        for key, value in (('status', 'FAIL_OR_HOLD_NOT_ADMITTED'), ('prepared_seal', '0'*64),
                           ('coverage_admitted', True), ('EDA_launched', True), ('RTL_modified', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                a.qualification(dict(self.q, **{key:value}))

    def test_all16_vector_no_skip_stop_or_incomplete(self):
        for key, value in (('compared_instructions', 15), ('compared_bytes', 16383),
                           ('skipped_unknown_bytes', True), ('stopped_at_spike_index', 0),
                           ('incomplete_requests', [1]), ('non_bit_exact_instructions', 1)):
            bad = copy.deepcopy(self.q)
            bad['native']['architectural_vector_diff'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                a.qualification(bad)

    def test_missing_duplicate_and_partial_primary_writer_rejected(self):
        for mode in ('missing', 'duplicate', 'partial', 'boolphase'):
            bad = copy.deepcopy(self.q)
            rows = bad['native']['primary_writers']
            if mode == 'missing':
                rows.pop()
            elif mode == 'duplicate':
                rows[-1] = rows[0]
            elif mode == 'partial':
                rows[0]['compared_bytes'] = 1023
            else:
                rows[0]['phase'] = True
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                a.qualification(bad)

    def test_scalar_skip_mismatch_and_guard_drift_rejected(self):
        for key, value in (('skipped_unobservable_register_values', 1), ('mismatch', 'bad'),
                           ('matched_instructions', 39051), ('ara_trap_events', 1)):
            bad = copy.deepcopy(self.q)
            bad['scalar'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                a.qualification(bad)
        bad = copy.deepcopy(self.q)
        bad['footprint']['CSR_values'] = 23
        with self.assertRaises(ValueError):
            a.qualification(bad)

    def test_q_no_gain_missing_four_slots_or_boolean_slots_rejected(self):
        for changes in (dict(target_new_slots=0), dict(target_queue_slots=[0, 1, 2]),
                        dict(target_queue_slots=[False, 1, 2, 3]), dict(full2989=False)):
            bad = copy.deepcopy(self.q)
            bad['raw_gain'].update(changes)
            with self.assertRaises(ValueError):
                a.qualification(bad)

    def test_complete6162_exact797_ordered_prefix_and_unique_sample(self):
        after = a.full_union(self.before, self.single)
        self.assertEqual(after['tests'], self.ledger[1:] + [str(a.RUN / 'code.vdb')])
        self.assertEqual(sum(map(len, after['metrics'].values())), 6162)
        after['tests'][0], after['tests'][1] = after['tests'][1], after['tests'][0]
        with self.assertRaises(ValueError):
            a.g.mature.exact_raw_union(self.before, self.single, after, population=797)

    def test_metric_universe_shape_overflow_and_wrong_candidate(self):
        for mode in ('missing', 'shape', 'overflow', 'boolwidth', 'foreign', 'duplicate'):
            bad = copy.deepcopy(self.single)
            scope = next(iter(bad['metrics']['line']))
            if mode == 'missing':
                del bad['metrics']['line'][scope]
            elif mode == 'shape':
                bad['metrics']['line'][scope]['checksum'] = 'foreign'
            elif mode == 'overflow':
                bad['metrics']['line'][scope]['bits'] = hex(1 << bad['metrics']['line'][scope]['width'])
            elif mode == 'boolwidth':
                bad['metrics']['line'][scope]['width'] = True
            else:
                bad['tests'] = ['/foreign.vdb' if mode == 'foreign' else self.before['tests'][0]]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                a.full_union(self.before, bad)

    def test_metric_or_lost_hit_rejected(self):
        after = a.full_union(self.before, self.single)
        scope = next(k for k, v in after['metrics']['line'].items() if int(v['bits'], 16))
        after['metrics']['line'][scope]['bits'] = '0x0'
        with self.assertRaises(ValueError):
            a.g.mature.exact_raw_union(self.before, self.single, after, population=797)

    def test_all2989_or_and_negative_corruption(self):
        a.toggle_or(self.bt, self.st, self.at)
        for mode in ('missing', 'shape', 'negative', 'overflow', 'lost'):
            bad = copy.deepcopy(self.at)
            scope = next(k for k, v in bad.items() if int(v['bits'], 16))
            if mode == 'missing':
                del bad[scope]
            elif mode == 'shape':
                bad[scope]['checksum'] = 'foreign'
            else:
                bad[scope]['bits'] = {'negative':'-0x1', 'overflow':hex(1 << bad[scope]['width']), 'lost':'0x0'}[mode]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                a.toggle_or(self.bt, self.st, bad)

    def test_actual_four_slot_gain18_all_toggle118(self):
        gain, _ = a.raw_gain(self.before, self.single, a.full_union(self.before, self.single),
                            self.bt, self.st, self.at, self.targets)
        a.exact(gain, self.q['raw_gain'], 'Actual successful q gain')
        self.assertEqual(gain['target_new_slots'], 18)
        self.assertEqual(gain['full_toggle_new_slots'], 118)

    def test_real_or_without_target_gain_rejected(self):
        with self.assertRaises(ValueError):
            a.raw_gain(self.before, self.single, a.full_union(self.before, self.single),
                       self.bt, self.bt, self.bt, self.targets)

    def test_typed_canonical_comparison_rejects_tuple_bool_and_extra(self):
        a.exact({'items':(1, 2)}, {'items':[1, 2]}, 'JSON roundtrip')
        for bad in ({'n':True}, {'n':1.0}, {'n':1, 'extra':0}, {}):
            with self.assertRaises(ValueError):
                a.exact({'n':1}, bad, 'typed')

    def test_failed_package_and_foreign_q_rejected_before_reads(self):
        with patch.object(a.life, 'read_bound') as read:
            with self.assertRaises(ValueError):
                a.evaluate(a.life.OUT / 'gather-war797-qualified-parent-20261008-01/qualification.json', a.Q_SHA)
            with self.assertRaises(ValueError):
                a.evaluate(a.QUAL, '0'*64)
            read.assert_not_called()

    def test_membership_extra_missing_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / 'raw'
            p.touch()
            pins = {str(p):a.life.digest(p)}
            a.membership(root, pins)
            with self.assertRaises(ValueError):
                a.membership(root, {})
            (root / 'extra').touch()
            with self.assertRaises(ValueError):
                a.membership(root, pins)
            (root / 'extra').unlink()
            (root / 'link').symlink_to(p)
            with self.assertRaises(ValueError):
                a.membership(root, pins)

    def test_unique_elf_rejects_existing_authoritative_hash(self):
        with tempfile.TemporaryDirectory() as d:
            elf = Path(d) / 'new.elf'
            elf.write_bytes(b'fixture')
            sha = a.life.digest(elf)
            manifest = dict(command=['+PRELOAD='+str(elf)], elf_sha256=sha)
            old = dict(ledger_members=797, duplicate=False,
                       members=[dict(vdb=v, ELF_candidates={'old':sha}) for v in self.ledger[1:]])
            base = dict(output_pins={str(a.BASE / 'elf-ledger-dedup.json'):'a'*64})
            with patch.object(a.life, 'read_bound', return_value=old):
                with self.assertRaises(ValueError):
                    a.historical(base, self.ledger, {str(elf):sha}, manifest)

    def test_admit_requires_parent_and_never_evaluates_without_it(self):
        with patch.object(a, 'evaluate') as evaluate:
            with self.assertRaises(ValueError):
                a.main(['admit', '--output', '/tmp/no-admit798', '--seal', '0'*64,
                        '--qualification', str(a.QUAL), '--qualification-seal', a.Q_SHA])
            evaluate.assert_not_called()

    def test_prepare_cannot_authorize_publication(self):
        with patch.object(a, 'evaluate') as evaluate:
            with self.assertRaises(ValueError):
                a.main(['prepare', '--output', '/tmp/no-admit798', '--parent-authorized',
                        '--qualification', str(a.QUAL), '--qualification-seal', a.Q_SHA])
            evaluate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
