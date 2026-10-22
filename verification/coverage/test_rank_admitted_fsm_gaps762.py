import unittest
import xml.etree.ElementTree as ET
import rank_admitted_fsm_gaps762 as audit


class RankTests(unittest.TestCase):
    def fixture(self):
        definition = ET.fromstring('<fsmdef><fsmfsm name="state_q" chksum="m">'
            '<state id="0" name="Idle"/><state id="1" name="Busy"/>'
            '<transition fromid="0" toid="1" line="9"/>'
            '</fsmfsm></fsmdef>')
        return dict(tests=['test_%d' % i for i in range(762)], metrics=dict(fsm={
            audit.original.SCOPE + '.unit': dict(bits='0x4', width=3, checksum='c')})), {'c': definition}

    def test_qualified_exclusion_only_marks_exact_identity(self):
        bitmap, definitions = self.fixture()
        scope = audit.original.SCOPE + '.unit'
        excluded = {(scope, 'state_q', 'm', 'Transition', 'Idle->Busy')}
        row = audit.rank(bitmap, definitions, excluded)[0]
        self.assertEqual(row['remaining_states'], 1)
        self.assertEqual(row['remaining_transitions'], 0)
        self.assertEqual(len(row['missing']), 2)

    def test_duplicate_membership_rejected(self):
        bitmap, definitions = self.fixture()
        bitmap['tests'][-1] = bitmap['tests'][0]
        with self.assertRaises(ValueError): audit.rank(bitmap, definitions, set())

    def test_shape_mismatch_rejected(self):
        bitmap, definitions = self.fixture()
        row = next(iter(bitmap['metrics']['fsm'].values()))
        row['width'] = 4
        with self.assertRaises(ValueError): audit.rank(bitmap, definitions, set())

    def test_foreign_checksum_rejected(self):
        bitmap, definitions = self.fixture()
        with self.assertRaises(ValueError): audit.rank(bitmap, {}, set())


if __name__ == '__main__': unittest.main()
