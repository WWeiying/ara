"""Bounded differential setup checks; not reference or DUT execution."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from checker import Checker, base, full_config, word

HERE = Path(__file__).resolve().parent
PROFILE = {}


class CacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.gold = full_config()

    def check(self, cls, ordinal=0):
        c = cls(self.config, self.gold)
        c.calls = ordinal
        c.pre, c.cap = 6, 3
        return c

    def events(self, c):
        return list(zip((r['pc'] for r in c.s['stores']), c.expected_setup(c.current())))

    def deliver(self, c, events):
        accepted = []
        try:
            for pc, (address, value, width) in events:
                c.setup_store(pc, address, value, width)
                accepted.append((c.fresh, c.counts['fresh_stores']))
        except (ValueError, KeyError) as e:
            return accepted, type(e).__name__, str(e)
        return accepted, None, None

    def test_all49_equal_across_calls_seed_mask_highbits(self):
        ordinals = (0, 1, 2, 4, 6, 8, 48, 784, 785, 786, 16*560+4*56, 17919)
        for ordinal in ordinals:
            old, new = self.check(base.Checker, ordinal), self.check(Checker, ordinal)
            events = self.events(old)
            self.assertEqual(self.deliver(old, events), self.deliver(new, events))
            self.assertEqual(tuple(old.expected_setup(old.current())), new._source_setup)
            self.assertIsInstance(new._source_setup, tuple)
            self.assertTrue(all(isinstance(row, tuple) and all(type(v) is int for v in row)
                                for row in new._source_setup))
            with self.assertRaises(TypeError):
                new._source_setup[0] = (0, 0, 0)

    def test_once_per_ordinal_not_values_profile(self):
        calls = (0, 1, 2, 560+4*56, 560+4*56+2, 17919)
        original_builder = base.Checker.expected_setup
        constructions = {'old': 0, 'new': 0}
        for label, cls in [('old', base.Checker), ('new', Checker)]:
            c = self.check(cls)
            def counted(instance, g):
                constructions[label] += 1
                return original_builder(instance, g)
            for ordinal in calls:
                c.calls, c.fresh = ordinal, 0
                events = list(zip((r['pc'] for r in c.s['stores']), original_builder(c, c.current())))
                with patch.object(base.Checker, 'expected_setup', counted):
                    outcome = self.deliver(c, events)
                self.assertIsNone(outcome[1])
            self.assertEqual(c.counts['fresh_stores'], len(calls)*49)
        self.assertEqual(constructions, {'old': len(calls)*49, 'new': len(calls)})
        PROFILE.update(ordinals=list(calls), old_builder_calls=constructions['old'],
                       new_builder_calls=constructions['new'], actual_store_events_each=len(calls)*49,
                       source_tuples_old=constructions['old']*49, source_tuples_new=constructions['new']*49,
                       scope='Small synthetic construction-count proof, not raw runtime performance')

    def test_real_oracle_transition_invalidates_by_ordinal(self):
        c = self.check(Checker, 1)
        g = c.current()
        c.record_index = g['record_index']
        for i, (pc, event) in enumerate(self.events(c)):
            if 16 <= i < 32:
                k = i-16
                record = word(c.memory, c.a['oracle_records']+8*g['record_index'], 8)
                row = (record >> (48 if k%2 == 0 else 56)) & 255
                address = c.a['input_periods']+64*row+8*(k//2)
                c.input_load(c.s['input_loads'][k]['pc'], address, word(c.memory,address,8), 8)
            c.setup_store(pc, *event)
        prior = c._source_setup
        c.active = dict(read=False, vstart=0, flags=g['flags'])
        value = 91 | (sum(min(bits)<<i for i,bits in enumerate(g['allowed']))<<8) | (91<<24)
        c.oracle(c.a['output'], value, 4)
        self.assertEqual(c.calls, 2)
        pc, event = self.events(c)[0]
        self.assertNotEqual(event, prior[0])  # mode0 -> mode1
        c.setup_store(pc, *event)
        self.assertEqual(c._setup_ordinal, 2)
        self.assertIsNot(c._source_setup, prior)
        self.assertEqual(c._source_setup[0], event)

    def test_missing_duplicate_wrong_PC_address_width_high_value(self):
        for kind in ('missing_same', 'duplicate_same', 'missing_tail', 'wrong_pc',
                     'address', 'width', 'high32', 'old_mask'):
            old, new = self.check(base.Checker, 786), self.check(Checker, 786)
            events = self.events(old)
            if kind == 'missing_same': del events[30]
            elif kind == 'duplicate_same': events.insert(31, events[30])
            elif kind == 'missing_tail':
                # Following helper index0 still requires all49; no stale-value shortcut.
                events = events[:-1]
            else:
                i = 30 if kind != 'old_mask' else 0
                pc, (address, value, width) = events[i]
                if kind == 'wrong_pc': pc = events[i-1][0]
                elif kind == 'address': address += 8
                elif kind == 'width': width = 4
                elif kind == 'high32': value ^= 1<<63
                else: value = 0xffffffffffffffff
                events[i] = (pc, (address,value,width))
            a, b = self.deliver(old, events), self.deliver(new, events)
            self.assertEqual(a, b)
            if kind != 'missing_tail': self.assertEqual(a[1], 'ValueError')
            else:
                for c in (old,new):
                    with self.assertRaisesRegex(ValueError, 'Complete setup'):
                        c.helper(dict(x={30:0},f={},mem=[]), (4,0))

    def test_instance_isolation_and_source_not_actual(self):
        a, b = self.check(Checker, 0), self.check(Checker, 784)
        for c in (a,b):
            pc, event = self.events(c)[0]
            c.setup_store(pc, *event)
        self.assertIsNot(a._source_setup, b._source_setup)
        self.assertNotEqual(a._source_setup[16:32], b._source_setup[16:32])
        c = self.check(Checker, 784)
        pc, (address,value,width) = self.events(c)[0]
        with self.assertRaisesRegex(ValueError,'Exact49'):
            c.setup_store(pc,address,value^1,width)
        self.assertEqual(c._source_setup[0], (address,value,width))
        self.assertEqual(c.fresh, 0)


if __name__ == '__main__':
    # Reuse every original short test against the successor via its normal import.
    path = HERE.parent/'reference_entry01/test_checker.py'
    spec = importlib.util.spec_from_file_location('sealed_fp32_short_tests',path)
    old_tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_tests)
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(old_tests.Tests),
                               unittest.defaultTestLoader.loadTestsFromTestCase(CacheTests)])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        with (HERE/'cache_profile.json').open('x') as f:
            json.dump(PROFILE,f,indent=2);f.write('\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
