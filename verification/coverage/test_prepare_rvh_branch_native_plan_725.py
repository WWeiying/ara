import copy
import json
import unittest

import prepare_rvh_branch_native_plan_725 as subject


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=json.loads((subject.STATIC/'inventory.json').read_bytes())

    def test_real_sealed_38_groups_pilot3_full247_protection(self):
        p=subject.make_plan(self.evidence)
        self.assertEqual(p['pilot_counts'],dict(scopes=1,targets=3,audited_branch_positions=100,protected=97))
        self.assertEqual(p['full_counts']['protected'],1533)
        self.assertEqual(len(p['group_selectors']),38)
        self.assertFalse(p['full_expansion_authorized'])
        self.assertFalse(p['application_approval'])

    def test_all_selector_native_identity_pending_not_xml_transplant(self):
        p=subject.make_plan(self.evidence)
        selectors=[s for g in p['group_selectors'] for s in g['selectors']]
        self.assertEqual(len(selectors),247)
        for s in selectors:
            self.assertIsNone(s['actual_GUI_meta'])
            self.assertIsNone(s['actual_native_signature'])
            self.assertTrue(s['direct_rvh_expressions'])

    def test_source_file_checksum_and_hit_mismatch_rejected(self):
        g=self.evidence['groups'][0]
        for mutate in ('file','checksum','hit'):
            row=copy.deepcopy(g['targets'][0])
            if mutate=='file': row['point']['file_id']='bad'
            elif mutate=='checksum': row['point']['attributes']['chksum']='bad'
            else: row['hit725']=True
            with self.assertRaises(ValueError): subject.selector(g,row)

    def test_missing_outside_protection_rejected(self):
        e=copy.deepcopy(self.evidence)
        outside=next(x for x in e['protected_outside_matching_groups'] if x['scope']==subject.PILOT)
        outside['protected_outside_matching_groups'].pop()
        with self.assertRaises(ValueError): subject.make_plan(e)

    def test_payload_is_closed_gate_data_only(self):
        text=subject.selection_payload(subject.make_plan(self.evidence)['pilot_scopes'])
        self.assertIn('set rvh_native_binding_gate 0',text)
        self.assertIn('{'+subject.PILOT+'|branch} {}',text)
        self.assertNotIn('gui_',text)
        self.assertNotIn('rename ',text)
        self.assertNotIn('{*}',text)


if __name__=='__main__': unittest.main()
