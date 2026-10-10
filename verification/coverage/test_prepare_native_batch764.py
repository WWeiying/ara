import copy
import json
from pathlib import Path
import unittest
import prepare_native_batch764 as p


class SuccessorTests(unittest.TestCase):
    def test_unknown_duplicate_and_missing_profile_rejected(self):
        for values in (['other=x'],['vmfpu10=x','vmfpu10=y'],['vmfpu10']):
            with self.assertRaises(Exception):p.pairs(values)

    def test_no_runtime_or_launch_interface(self):
        self.assertFalse(hasattr(p,'run'))

    def test_fixed_parent_approved764_and_sldu_seals(self):
        self.assertEqual(p.life.digest(p.MANIFEST),p.MANIFEST_SHA)
        with self.assertRaises(Exception):p.load_native('sldu2',p.life.OUT/'not-existing','0'*64)

    def test_predecessor_not_qualified_rejected(self):
        c=dict(population=763,qualified_fsm_union=161,schema=p.predecessor.SCHEMA,output=str(p.PREDECESSOR))
        with self.assertRaises(Exception):p.predecessor_gate(dict(status='PREPARED_NO_DVE'),c)

    def test_actual_vmfpu_parent_qualified_gates(self):
        q=p.life.read_bound(p.life.OUT/'vmfpu-ten-native762-agent-20261007-01/capture-result.json',p.VMFPU_SHA)
        p.native_gate('vmfpu10',q)
        q=copy.deepcopy(q);q['protected_reachable_reset_arcs']=19
        with self.assertRaises(Exception):p.native_gate('vmfpu10',q)

    def test_actual_vmfpu_complement_merge(self):
        c=json.loads((p.PREDECESSOR/'config.json').read_bytes())
        addition=json.loads((p.life.OUT/'vmfpu-ten-native762-agent-20261007-01/config.json').read_bytes())['plan']
        plan,added=p.merge_fsm(c['plan'],addition)
        self.assertEqual(len(added),10)
        self.assertEqual(plan['targets'],c['plan']['targets']+10)
        self.assertEqual(plan['protected'],c['plan']['protected']-10)
        self.assertEqual(len(plan['groups']),len(c['plan']['groups']))
        with self.assertRaises(Exception):p.merge_fsm(plan,addition)

    def test_wrong_complement_and_checksum_rejected(self):
        c=json.loads((p.PREDECESSOR/'config.json').read_bytes())
        a=json.loads((p.life.OUT/'vmfpu-ten-native762-agent-20261007-01/config.json').read_bytes())['plan']
        wrong=copy.deepcopy(a);wrong['groups'][0]['rows'][0]['attributes']['line']='1'
        with self.assertRaises(Exception):p.merge_fsm(c['plan'],wrong)
        wrong=copy.deepcopy(a);wrong['groups'][0]['checksum']='foreign'
        with self.assertRaises(Exception):p.merge_fsm(c['plan'],wrong)

    def test_full_shape_OR_and_prefix_gate(self):
        before=dict(design={},tests=[str(i) for i in range(763)],metrics={})
        one=dict(design={},tests=['new'],metrics={})
        actual=dict(design={},tests=before['tests']+['new'],metrics={})
        for i in range(6162):
            k=str(i);before['metrics'][k]={'scope':dict(width=2,checksum='x',bits='1')}
            one['metrics'][k]={'scope':dict(width=2,checksum='x',bits='2')}
            actual['metrics'][k]={'scope':dict(width=2,checksum='x',bits='3')}
        book=dict(schema='QBS_PHASE_HISTORICAL764_NATIVE_ADMISSION_V1',explicit_parent_authorized=True,
                  baseline_seal=p.predecessor.MANIFEST_SHA,baseline=str(p.predecessor.MANIFEST.parent))
        status=dict(aggregate_passed=764,coverage_admitted=True)
        p.population_gate(book,actual,before,one,status)
        actual['metrics']['0']['scope']['bits']='2'
        with self.assertRaises(Exception):p.population_gate(book,actual,before,one,status)

    def test_failed_c910_or_unqualified_scalar_rejected(self):
        for key in ('c910240','scalarDWC3','sldu2'):
            with self.assertRaises(Exception):p.native_gate(key,dict(status='FAILED',population_application=False))


if __name__=='__main__':unittest.main()
