import copy
import json
import unittest
from unittest.mock import patch

import prepare_mask_store_snapshot_cond24 as p


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = json.loads(p.PROOF.read_bytes())
        cls.candidates, cls.hold = p.split_candidates(cls.proof['candidates'])
        cls.candidates = copy.deepcopy(cls.candidates)
        for c in cls.candidates:
            c['module_checksum'] = '2909207138'

    def native(self, rows=None):
        rows = self.candidates if rows is None else rows
        result = []
        for i, c in enumerate(rows):
            point = c['point']
            # Deliberately unrelated to XML condregid and row order.
            result.append(dict(scope=c['scope'], module_checksum=c['module_checksum'],
                metric_checksum=c['checksum'], native_id=str(800+i),
                point_checksum=point['attributes']['chksum'], expression=point['expression'],
                width=point['attributes']['width'], bit='-1', vector_id='77', vector=point['vector']))
        return result

    def test_real24_and_branch8_hold(self):
        self.assertEqual(len(self.candidates),24)
        self.assertEqual(len(self.hold),8)
        self.assertTrue(all('HOLD' in r['decision'] for r in self.hold))

    def test_all_condition_neighbors_and_port8_preserved(self):
        rows = p.groups(self.candidates,self.proof['protected']+self.hold)
        self.assertEqual(len(rows),36)
        self.assertEqual(sum(len(r['targets']) for r in rows),24)
        self.assertTrue(all(not r['targets'] for r in rows if '[8]' in r['expression']))
        self.assertTrue(all(r['retained'] for r in rows))

    def test_branch_cannot_be_capture_target(self):
        with self.assertRaises(ValueError):
            p.groups(self.candidates[:-1]+self.hold[:1],self.proof['protected'])

    def test_hit_candidate_rejected(self):
        changed=copy.deepcopy(self.proof['candidates']);changed[0]['hit_before']=True
        with self.assertRaises(ValueError):p.split_candidates(changed)

    def test_duplicate_candidate_rejected(self):
        changed=copy.deepcopy(self.proof['candidates']);changed[1]=changed[0]
        with self.assertRaises(ValueError):p.split_candidates(changed)

    def test_native_IDs_observed_not_XML_guessed(self):
        p.bind(self.native(),self.candidates)

    def test_wrong_checksum_rejected(self):
        records=self.native();records[0]['point_checksum']='999'
        with self.assertRaises(ValueError):p.bind(records,self.candidates)

    def test_extra_protected_record_rejected(self):
        with self.assertRaises(ValueError):p.bind(self.native()+self.native()[:1],self.candidates)

    def test_missing_native_record_rejected(self):
        with self.assertRaises(ValueError):p.bind(self.native()[1:],self.candidates)

    def test_wrong_vector_rejected(self):
        records=self.native();records[0]['vector']='0'
        with self.assertRaises(ValueError):p.bind(records,self.candidates)

    def test_native_ID_alias_rejected(self):
        records=self.native();records[1]['native_id']=records[0]['native_id']
        with self.assertRaises(ValueError):p.bind(records,self.candidates)

    def test_protected_branch_directive_not_condition_format(self):
        with self.assertRaises(ValueError):
            p.parse_records('CHECKSUM: "1 2"\nINSTANCE: dut\nBranch 1 "3" "expr" (0) "expr"\n')

    def test_whole_instance_rejected(self):
        with self.assertRaises(ValueError):p.parse_records('CHECKSUM: "1 2"\nINSTANCE: dut\n')

    def test_fresh_output_gate_before_any_EDA(self):
        with patch.object(p,'evidence',side_effect=AssertionError('should not reach evidence')):
            with self.assertRaises(ValueError):p.prepare(p.OUT)


if __name__ == '__main__':
    unittest.main()
