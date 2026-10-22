import copy
import unittest

import soc_constants61_native as tool


class Native61Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = tool.life.read_bound(tool.SOURCE, tool.SOURCE_SHA)
        cls.instances = tool.instances(cls.proof)
        cls.config = dict(instances=cls.instances, design='host', vdb='host', test='host')
        cls.el = tool.candidate(cls.instances)

    def test_actual_complete_binary_targets(self):
        fields = [s for i in self.instances for s in i['signals']]
        self.assertEqual((len(self.instances), len(fields)), (18, 61))
        self.assertEqual(sorted(s['left']+1 for s in fields), [3]+[64]*60)
        self.assertEqual(sum(s['left']+1 for s in fields), 3843)
        for i in self.instances:
            for s in i['signals']:
                self.assertEqual(next(n for n in i['typed_objects'] if n['name']==s['name'])['kind'], 'vectornode')

    def test_actual_exact_el(self):
        self.assertTrue(tool.el_gate(self.el, self.config))

    def test_foreign_empty_checksum(self):
        with self.assertRaises(Exception):
            tool.el_gate(self.el+'\nCHECKSUM: "0 0"\n', self.config)

    def test_partial_target_rejected(self):
        with self.assertRaises(Exception):
            tool.el_gate(self.el.replace('[63:0]', '[62:0]', 1), self.config)

    def test_missing_target_rejected(self):
        lines=self.el.splitlines()
        lines.pop(next(i for i,v in enumerate(lines) if v.startswith('Toggle ')))
        with self.assertRaises(Exception):
            tool.el_gate('\n'.join(lines), self.config)

    def test_mda_target_rejected(self):
        proof=copy.deepcopy(self.proof)
        proof['candidates'][0]['compiled_attributes']['left']='62'
        with self.assertRaises(Exception):
            tool.instances(proof)

    def test_initial_x_claim_rejected(self):
        proof=copy.deepcopy(self.proof)
        proof['candidates'][0]['initial_X_or_delta_instrumentation_qualified']=True
        with self.assertRaises(Exception):
            tool.instances(proof)

    def test_protected_and_reset_cells_strict(self):
        i=self.instances[0]
        label=tool.labels(i)[0]
        before={label:dict(handle='1',name=label,type='port',coverage='0%',display='0%')}
        actual=copy.deepcopy(before);actual[label]['display']='excluded'
        tool.stage_gate(i,before,actual,'applied')
        with self.assertRaises(Exception):tool.stage_gate(i,before,actual,'reset')
        actual[label]['type']='signal'
        with self.assertRaises(Exception):tool.stage_gate(i,before,actual,'applied')
        before['protected']=dict(before[label]);actual=copy.deepcopy(before)
        actual['protected']['coverage']='100%'
        with self.assertRaises(Exception):tool.stage_gate(i,before,actual,'applied')

    def test_actual_generated_full_five_stage_no_object_select(self):
        result=tool.host_hook(self.config,tool.selection(self.config),self.el)
        self.assertEqual(result['scope_inventories'],90)
        self.assertEqual(result['per_object_GUI_select_calls'],0)
        self.assertFalse(result['EDA_started'])

    def test_transitive_tcl_closure(self):
        pins=tool.frozen.tcl_pins(tool.TCL)
        self.assertIn(str(tool.TCL),pins)
        self.assertIn(str(tool.HERE/'fpnew_tied90_local.tcl'),pins)
        self.assertIn(str(tool.HERE/'mfpu272_five_phase.tcl'),pins)


if __name__=='__main__':unittest.main()
