import copy
import unittest
import prepare_full775_selection_quote_fix as q


class SelectionQuoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c=q.p.life.read_bound(q.SOURCE/'config.json',q.SOURCE_SHA)
        cls.contract=c['branch720'];cls.text=(q.SOURCE/'selection.tcl').read_text()

    def test_actual_complete_failed_selection_reproduces(self):
        with self.assertRaisesRegex(ValueError,'invalid command name'):
            q.host_check(self.text,self.contract)

    def test_actual_complete_fixed_selection_in_procedure(self):
        text=q.fixed_selection(self.text,self.contract)
        result=q.host_check(text,self.contract)
        self.assertEqual((result['array_members'],result['targets'],result['protected']),(24,720,492))
        oldlines=self.text.splitlines(keepends=True);newlines=text.splitlines(keepends=True)
        self.assertEqual(len(oldlines),len(newlines))
        changes=[(a,b) for a,b in zip(oldlines,newlines) if a!=b]
        self.assertEqual(len(changes),24)
        for old,new in changes:
            name,rhs=old[4:].split(' [list',1)
            self.assertEqual(new,'set '+q.p.prior.tcl_atom(name)+' [list'+rhs)

    def test_unknown_scope_and_role_rejected(self):
        for text in (self.text.replace('set ::op1144_keys(', 'set ::op1144_bad(',1),
                     self.text.replace('set ::op1144_keys(ara_tb.', 'set ::op1144_keys(other_tb.',1)):
            with self.assertRaises(ValueError):q.fixed_selection(text,self.contract)

    def test_changed_target_coordinate_rejected(self):
        oldline=next(iter(q.declarations(self.contract)))
        with self.assertRaises(ValueError):q.fixed_selection(self.text.replace(oldline,oldline.replace('{4,21}','{999,21}')),self.contract)

    def test_missing_duplicate_declarations_rejected(self):
        line=next(iter(q.declarations(self.contract)))
        for text in (self.text.replace(line,'',1),self.text+line):
            with self.assertRaises(ValueError):q.fixed_selection(text,self.contract)

    def test_target_protection_mutation_rejected(self):
        fixed=q.fixed_selection(self.text,self.contract)
        line=next(v for k,v in q.declarations(self.contract).items() if 'targets(' in k)
        with self.assertRaises(ValueError):q.host_check(fixed.replace(line,line.replace('{4,21}','{999,21}')),self.contract)

    def test_extra_array_owner_rejected(self):
        fixed=q.fixed_selection(self.text,self.contract)
        with self.assertRaises(ValueError):q.host_check(fixed+'\nset {::op1144_keys(extra)} [list]\n',self.contract)

    def test_contract_boolean_and_duplicate_rejected(self):
        c=copy.deepcopy(self.contract);c['branch_inventory'][0]['target']=1
        with self.assertRaises(ValueError):q.specs(c)
        c=copy.deepcopy(self.contract);c['branch_inventory'][0]['selector']=c['branch_inventory'][1]['selector']
        with self.assertRaises(ValueError):q.specs(c)

    def test_no_unknown_command_mock_or_suppression(self):
        fixed=q.fixed_selection(self.text,self.contract)
        with self.assertRaises(ValueError):q.host_check(fixed+'\ngui_open_cov\n',self.contract)


if __name__=='__main__':unittest.main()
