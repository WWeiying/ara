import copy
import tempfile
import unittest
from pathlib import Path
import qualify_operand_mask_data_02_defined as m


class DefinedPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=m.q.vc.compare_vector_commits(m.q.PRE/'spike.trace',
            m.p.RUN/'commit_trace.csv',m.p.RUN/'vector_trace.csv',0x80000000)

    def test_actual_full_trace_policy(self):
        result=m.policy_audit(m.p.RUN/'commit_trace.csv',m.p.RUN/'vector_trace.csv',self.raw)
        self.assertEqual(result['unknown_active_bytes'],0)
        self.assertEqual(result['agnostic_tail_bytes'],64)
        self.assertEqual(result['preserved_identity_bytes'],1024)

    def test_actual_terminal(self):
        _,_,term=m.q.prefix((m.p.RUN/'commit_trace.csv').read_bytes())
        self.assertEqual((term['cycle'],term['order']),(247776,191287))

    def test_missing_reordered_duplicate_site(self):
        for mode in ('missing','reorder','duplicate'):
            r=copy.deepcopy(self.raw)
            if mode=='missing': r['instructions'].pop()
            elif mode=='reorder': r['instructions'].reverse()
            else: r['instructions'][0]=copy.deepcopy(r['instructions'][1])
            with self.assertRaises(ValueError): m.summary_gate(r)

    def test_unapproved_skipped_site(self):
        r=copy.deepcopy(self.raw); r['instructions'][0]['skipped_unknown_bytes']=1
        with self.assertRaises(ValueError): m.summary_gate(r)

    def test_wrong_policy_opcode(self):
        r=copy.deepcopy(self.raw); r['instructions'][7]['instruction']='0x6b8800d7'
        with self.assertRaises(ValueError): m.summary_gate(r)

    def test_unknown_active_and_other_business_bytes(self):
        for args in ((13,1,15,None,255,1),(13,2,16,None,0,1),
                     (12,1,16,None,0,1),(13,1,32,None,0,1),(13,1,16,None,255,1)):
            with self.assertRaises(ValueError): m.byte_gate(*args)
        self.assertFalse(m.byte_gate(13,1,16,None,0,1))

    def test_nonbitexact_mismatch_trap_incomplete(self):
        for key,value in (('non_bit_exact_instructions',1),('first_mismatch',{}),
                          ('trapped_requests',[53]),('incomplete_requests',[13])):
            r=copy.deepcopy(self.raw);r[key]=value
            with self.assertRaises(ValueError): m.summary_gate(r)

    def test_zero_mask_must_have_no_enabled_writes(self):
        raw=(m.p.RUN/'vector_trace.csv').read_text().splitlines()
        fields=raw[0].split(','); seq=fields.index('arch_seq'); event=fields.index('event')
        be=fields.index('be')
        for i,line in enumerate(raw[1:],1):
            values=line.split(',')
            if values[seq]=='53' and values[event]=='write':
                values[be]='01';raw[i]=','.join(values);break
        else: self.fail('Actual zero-mask native write row absent')
        with tempfile.TemporaryDirectory(dir=m.q.OUT) as directory:
            path=Path(directory)/'mutated-vector.csv';path.write_text('\n'.join(raw)+'\n')
            with self.assertRaises(ValueError):
                m.policy_audit(m.p.RUN/'commit_trace.csv',path,self.raw)


if __name__=='__main__': unittest.main()
