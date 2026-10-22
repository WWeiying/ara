import copy
import json
import unittest
from unittest.mock import patch
import admit_fclass_divsqrt784 as a


def authority():
    q = json.loads(a.QUAL.read_bytes()); c = json.loads(a.CLOSURE.read_bytes())
    proof = json.loads((a.QUAL.parent / 'store75-context-proof.json').read_bytes())
    return q, c, proof


def bitmaps():
    before = dict(design={'shape': 'same'}, tests=['old%d' % n for n in range(783)], metrics={}, input_hashes={})
    single = dict(design={'shape': 'same'}, tests=[str(a.RUN / 'code.vdb')], metrics={}, input_hashes={})
    for metric, count in a.COUNTS.items():
        before['metrics'][metric] = {str(i): dict(width=4, checksum='1', bits='1') for i in range(count)}
        single['metrics'][metric] = {str(i): dict(width=4, checksum='1', bits='2') for i in range(count)}
    return before, single


class Admission(unittest.TestCase):
    def test_actual_joint_reviewed_authority(self): a.joint_authority(*authority())

    def test_missing_or_wrong_closure(self):
        for key, value in (('core_qualification_sha', '0' * 64), ('core_qualification', '/other'),
            ('core_qualification_unchanged', False), ('original_checks_preserved', False), ('coverage_admitted', True)):
            with self.subTest(key=key):
                q, c, proof = authority(); c[key] = value
                with self.assertRaises(ValueError): a.joint_authority(q, c, proof)

    def test_missing_core_or_successor_pins_rejected(self):
        for which in ('core', 'helper', 'test', 'obligation'):
            q, c, proof = authority()
            if which == 'core': name = str(a.QUAL)
            elif which == 'helper': name = str(a.Path(__file__).with_name('collect_fclass_divsqrt783_store75.py'))
            elif which == 'test': name = str(a.Path(__file__).with_name('test_collect_fclass_divsqrt783_store75.py'))
            else: name = next(iter(q['input_pins']))
            c['input_pins'].pop(name)
            with self.subTest(which=which):
                with self.assertRaises(ValueError): a.joint_authority(q, c, proof)

    def test_wrong_omitted_or_extra_store_proof_rejected(self):
        for kind in ('missing', 'duplicate', 'context', 'order', 'writer_filtered'):
            q, c, proof = authority()
            if kind == 'missing': proof['records'].pop()
            if kind == 'duplicate': proof['records'][1]['arch_seq'] = proof['records'][0]['arch_seq']
            if kind == 'context': proof['records'][0]['after']['vl'] = 8
            if kind == 'order': proof['records'][0]['done_cycle'] = proof['records'][0]['alloc_cycle'] - 1
            if kind == 'writer_filtered': proof['no_writer_or_byte_filtered'] = False
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError): a.joint_authority(q, c, proof)

    def test_partial_native_or_memory_rejected(self):
        for kind in ('prefix', 'unknown', 'writer', 'init', 'memory', 'CSR', 'exception'):
            q, c, proof = authority()
            if kind == 'prefix': q['vector']['status'] = 'PREFIX'
            if kind == 'unknown': q['vector']['skipped_unknown_bytes'] = 1
            if kind == 'writer': q['native']['writers'].pop()
            if kind == 'init': q['native']['initialization_bytes'] = 1024
            if kind == 'memory': q['scalar_memory']['scalar_memory_accesses'] -= 1
            if kind == 'CSR': q['signature']['CSR_values'] -= 1
            if kind == 'exception': q['lifecycle']['exceptions'] = 1
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError): a.joint_authority(q, c, proof)

    def test_exact_6162_or_preserves_every_old_bit(self):
        before, single = bitmaps(); after = a.full_union(before, single)
        self.assertEqual(after['tests'], before['tests'] + single['tests'])
        self.assertEqual(len(after['tests']), 784)
        self.assertEqual(sum(len(v) for v in after['metrics'].values()), 6162)
        self.assertTrue(all(int(r['bits'], 16) == 3 for rows in after['metrics'].values() for r in rows.values()))

    def test_population_duplicate_or_shape_failclosed(self):
        for kind in ('prefix', 'duplicate', 'shape', 'width', 'overflow', 'scope', 'metric'):
            before, single = bitmaps()
            if kind == 'prefix': before['tests'].pop()
            if kind == 'duplicate': before['tests'][0] = single['tests'][0]
            if kind == 'shape': single['metrics']['cond']['0']['checksum'] = '2'
            if kind == 'width': single['metrics']['line']['0']['width'] = 5
            if kind == 'overflow': single['metrics']['fsm']['0']['bits'] = '10'
            if kind == 'scope': single['metrics']['branch'].pop('0')
            if kind == 'metric': single['metrics'].pop('fsm')
            with self.subTest(kind=kind):
                with self.assertRaises((ValueError, KeyError)): a.full_union(before, single)

    def test_corrupt_combiner_cannot_drop_old_bits(self):
        before, single = bitmaps(); bad = a.bitmap.combine(before, single)
        bad['metrics']['cond']['0']['bits'] = '2'
        with patch.object(a.bitmap, 'combine', return_value=bad):
            with self.assertRaises(ValueError): a.full_union(before, single)

    def test_arbitrary_qualification_or_baseline_rejected_before_IO(self):
        with self.assertRaises(ValueError): a.evaluate(a.QUAL, '0' * 64, a.runner.BASE, a.runner.BASE_SHA)
        with self.assertRaises(ValueError): a.evaluate(a.QUAL, a.QUAL_SHA, a.runner.BASE.parent, a.runner.BASE_SHA)


if __name__ == '__main__': unittest.main()
