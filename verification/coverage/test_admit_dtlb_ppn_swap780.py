import copy
import json
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import admit_dtlb_ppn_swap780 as m


class Union(unittest.TestCase):
    def fixture(self):
        before = dict(design={'design': 'sha'}, tests=['old%d' % i for i in range(779)],
                      input_hashes={'/old-source': '0' * 64}, metrics={})
        for metric, count in m.COUNTS.items():
            before['metrics'][metric] = {'scope%d' % i: dict(width=2, checksum='1', bits='0x1')
                                        for i in range(count)}
        single = copy.deepcopy(before); single['tests'] = [str(m.RUN / 'code.vdb')]
        for rows in single['metrics'].values():
            for row in rows.values(): row['bits'] = '0x2'
        return before, single

    def test_complete6162_or_prefix(self):
        before, single = self.fixture(); after = m.full_union(before, single)
        self.assertEqual(after['tests'], before['tests'] + single['tests'])
        self.assertEqual(sum(map(len, after['metrics'].values())), 6162)
        self.assertTrue(all(r['bits'] == '0x3' for rows in after['metrics'].values() for r in rows.values()))

    def test_duplicate_wrong_member_shape_universe_and_bits(self):
        for change in ('duplicate', 'wrong', 'checksum', 'width', 'missing', 'overflow', 'bool'):
            before, single = self.fixture()
            if change == 'duplicate': before['tests'][0] = single['tests'][0]
            elif change == 'wrong': single['tests'] = ['other']
            elif change == 'missing': single['metrics']['line'].pop('scope0')
            else:
                row = single['metrics']['line']['scope0']
                key, value = {'checksum': ('checksum', '2'), 'width': ('width', 3),
                              'overflow': ('bits', '0x8'), 'bool': ('width', True)}[change]
                row[key] = value
            with self.subTest(change=change), self.assertRaises(ValueError): m.full_union(before, single)


class Qualification(unittest.TestCase):
    def fixture(self):
        load = lambda name: json.loads((m.QUAL / name).read_text())
        return [load('qualification.json'), load('scalar-comparison.json'), load('full-memory-audit.json'),
                load('vector-comparison.json'), load('tlb-slot-audit.json'), load('gold-audit.json'),
                json.loads(m.f.runner.PRE.read_text())]

    def test_actual_parent_architecture_obligations(self): m.architecture(*self.fixture())

    def test_partial_memory_bool_counter_and_unknown_vector(self):
        for key, value, index in [('total', 2248, 2), ('skipped', False, 2),
                                  ('matched_instructions', 191474, 1),
                                  ('non_bit_exact_instructions', None, 3)]:
            rows = self.fixture(); rows[index][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.architecture(*rows)

    def test_wrong_actual_ppn_owner_load_and_missing_update(self):
        for change in ('ppn', 'slot', 'load', 'missing'):
            rows = self.fixture(); wave = rows[4]
            if change == 'missing': wave['updates'].pop()
            elif change == 'load': wave['accepted_loads'][0]['load_in_pair'] = 1
            else: wave['updates'][0][change] += 1
            with self.subTest(change=change), self.assertRaises(ValueError): m.architecture(*rows)

    def test_wrong_gold_and_fake_vector_pass(self):
        rows = self.fixture(); rows[5]['software_checks'] -= 1
        with self.assertRaises(ValueError): m.architecture(*rows)
        rows = self.fixture(); rows[3]['status'] = 'PASS'
        with self.assertRaises(ValueError): m.architecture(*rows)


class Native(unittest.TestCase):
    def fixture(self):
        record = m.life.read_bound(m.RUN.with_name(m.RUN.name + '.prepared.json'), m.PREPARED_SHA)
        folder = m.RUN / 'code.vdb/snps/coverage/db/testdata' / m.f.runner.CASE
        return m.toggle.xml(folder / 'siminfo.xml'), m.toggle.xml(folder / 'vcmArguments.xml'), record

    def test_actual_native_command(self):
        sim, args, record = self.fixture()
        m.native_identity(sim, args, record, str(m.life.IMAGE) + '.vdb')

    def test_extra_owner_command_bad_time_and_wrong_design(self):
        for change in ('owner', 'command', 'time', 'design'):
            sim, args, record = self.fixture()
            if change == 'owner': sim.append(copy.deepcopy(sim.find('srctest')))
            elif change == 'command': sim.find('srctest').set('cmdline', 'wrong')
            elif change == 'time': sim.find('srctest').set('finishtime', '0')
            else: args.set('compvdbpath', 'other')
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.native_identity(sim, args, record, str(m.life.IMAGE) + '.vdb')

    def test_dedup_rejects_unsealed_or_candidate_owner(self):
        ledger = ['design'] + ['vdb%d' % i for i in range(779)]
        audit = dict(ledger_members=779, duplicate=False,
                     members=[dict(vdb=x) for x in ledger[1:]], pins={'candidate': 'sha'})
        with patch.object(m, 'dedup', return_value=audit), self.assertRaises(ValueError):
            m.historical(ledger, 'newsha', {})


if __name__ == '__main__': unittest.main()
