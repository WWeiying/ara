"""Actual captured cancellation and byte fixtures, with owner/shape/data mutations."""
import copy
import json
import unittest
from unittest.mock import patch
import postprocess_vmfpu_ured_reset763 as m


class CapturedTests(unittest.TestCase):
    def setUp(self):
        self.pre=json.loads((m.old.PRE/'preflight.json').read_bytes())
        reset=m.old.audit.events.run.reset
        _,self.commits=reset.read_csv(m.old.QUAL/'epoch0/commit_trace.csv')
        _,self.rows=reset.read_csv(m.old.QUAL/'epoch0/vector_trace.csv')
        self.pending={}
        for row in self.rows:
            if row['event']=='alloc':self.pending[int(row['vid'])]=row
            elif row['event']=='done':self.pending.pop(int(row['vid']))
        self.path=m.old.QUAL/'epoch0/commit_trace.csv'

    def test_actual_cancelled_exact37_38(self):
        result=m.cancelled_binding(self.pending,self.path,self.pre)
        self.assertEqual([r['arch_seq'] for r in result],[37,38])
        self.assertEqual([r['pc'] for r in result],
                         [self.pre['symbols']['ured_ones'],self.pre['symbols']['ured_reduce']])

    def test_all_owner_shape_mutations(self):
        for field,new in [('arch_seq','36'),('vid','7'),('insn','06809156'),('eew','2'),('vl','127'),
                          ('vstart','1'),('vd','9'),('source','1'),('lane','1'),('cycle','8567')]:
            rows=copy.deepcopy(self.pending);rows[0][field]=new
            with self.subTest(field=field),self.assertRaises(ValueError):
                m.cancelled_binding(rows,self.path,self.pre)

    def test_extra_missing_owner(self):
        for keys in ([0],[0,1,2]):
            rows={k:self.pending[k%2] for k in keys}
            with self.assertRaises(ValueError):m.cancelled_binding(rows,self.path,self.pre)

    def test_wrong_real_pc(self):
        pre=copy.deepcopy(self.pre);pre['symbols']['ured_reduce']+=4
        with self.assertRaises(ValueError):m.cancelled_binding(self.pending,self.path,pre)

    def seed(self,rows):
        with patch.object(m,'arch_mapping',return_value=m.arch_mapping(self.path)):
            return m.initial_bytes(self.commits,rows,self.pre)

    def test_full_actual4224_bytes(self):self.assertEqual(self.seed(self.rows),4224)

    def test_seed_corrupt_missing_duplicate_source(self):
        index=next(i for i,r in enumerate(self.rows) if r['event']=='write')
        for action in ('corrupt','missing','duplicate','source','be'):
            rows=copy.deepcopy(self.rows)
            if action=='corrupt':rows[index]['wdata']='0000000000000000'
            elif action=='missing':rows.pop(index)
            elif action=='duplicate':rows.append(rows[index])
            elif action=='source':rows[index]['source']='1'
            else:rows[index]['be']='fe'
            with self.subTest(action=action),self.assertRaises(ValueError):self.seed(rows)


if __name__=='__main__':unittest.main()
