import copy
import json
import unittest
import soc_constants61_native_v3 as v


class SavedELTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=json.loads((v.RUN/'config.json').read_text())
        cls.el=(v.RUN/'first.el').read_text()

    def test_actual_saved_el_and_all18_protected(self):
        q=v.replay()
        self.assertEqual((q['fields'],q['scopes'],q['rows_per_stage']),(61,18,9012))
        self.assertFalse(q['native_qualified'])

    def test_semantic_candidate_equivalence(self):
        self.assertEqual(v.el_gate(self.el,self.c),v.el_gate(v.old.candidate(self.c['instances']),self.c))

    def test_net_on_logic_rejected(self):
        with self.assertRaises(Exception):v.el_gate(self.el.replace('"logic ','"net ',1),self.c)

    def test_unknown_type_rejected(self):
        with self.assertRaises(Exception):v.el_gate(self.el.replace('"net ','"wire ',1),self.c)

    def test_partial_net_rejected(self):
        with self.assertRaises(Exception):v.el_gate(self.el.replace('net hart_id_i[2:0]','net hart_id_i[1:0]'),self.c)

    def test_missing_direction_rejected(self):
        with self.assertRaises(Exception):v.el_gate(self.el.replace('Toggle hart_id_i "net','Toggle 0to1 hart_id_i "net'),self.c)

    def test_foreign_annotation_and_directive_rejected(self):
        for text in (self.el.replace(v.old.ANNOTATION,'foreign'),self.el+'Unknown foo\n',self.el+'CHECKSUM: "0 0"\n'):
            with self.assertRaises(Exception):v.el_gate(text,self.c)

    def test_compiled_type_mutation_rejected(self):
        c=copy.deepcopy(self.c)
        i=next(i for i in c['instances'] if i['scope'].endswith('.i_system'))
        next(n for n in i['typed_objects'] if n['name']=='hart_id_i')['type']='1'
        with self.assertRaises(Exception):v.el_gate(self.el,c)

    def test_compiled_port_role_mutation_rejected(self):
        c=copy.deepcopy(self.c)
        i=next(i for i in c['instances'] if i['scope'].endswith('.i_system'))
        next(n for n in i['typed_objects'] if n['name']=='hart_id_i')['portnode']='3'
        with self.assertRaises(Exception):v.el_gate(self.el,c)

    def test_actual_protected_row_change_rejected(self):
        i=self.c['instances'][15]
        before=v.previous.bind(i,(v.RUN/'native_before_15.tsv').read_text())
        applied=v.previous.bind(i,(v.RUN/'native_applied_15.tsv').read_text())
        label='orig_instr.rvftype.repl';applied[label]['coverage']='foreign'
        with self.assertRaises(Exception):v.old.stage_gate(i,before,applied,'applied')

    def test_actual_generated_host_five_phase(self):
        env=v.context()
        q=env['host_hook'](self.c,env['selection'](self.c),v.old.candidate(self.c['instances']))
        self.assertEqual(q['scope_inventories'],90)
        self.assertEqual(q['per_object_GUI_select_calls'],0)


if __name__=='__main__':unittest.main()
