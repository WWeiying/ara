import copy
import json
import unittest
from unittest.mock import patch

import admit_akv_canonical_kfault790 as a


class TestAdmission(unittest.TestCase):
    def fixture(self):
        before=dict(design={'shape':'a'},tests=['old'],input_hashes={'/old':'a'*64},
                    metrics={'line':{'scope':dict(width=4,checksum='1',bits='0x1')}})
        new=dict(design={'shape':'a'},tests=['new'],input_hashes={'/new':'b'*64},
                 metrics={'line':{'scope':dict(width=4,checksum='1',bits='0x2')}})
        return before,new

    def gate(self,b,n):
        with patch.object(a,'COUNTS',{'line':1}):return a.union_gate(b,n,1)

    def test_exact_OR(self):
        b,n=self.fixture();r=self.gate(b,n)
        self.assertEqual(r['metrics']['line']['scope']['bits'],'0x3')
        self.assertEqual(r['tests'],['old','new'])

    def test_duplicate_VDB(self):
        b,n=self.fixture();n['tests']=['old']
        with self.assertRaises(Exception):self.gate(b,n)

    def test_missing_scope(self):
        b,n=self.fixture();n['metrics']['line']={}
        with self.assertRaises(Exception):self.gate(b,n)

    def test_extra_scope(self):
        b,n=self.fixture();n['metrics']['line']['extra']=n['metrics']['line']['scope']
        with self.assertRaises(Exception):self.gate(b,n)

    def test_wrong_checksum(self):
        b,n=self.fixture();n['metrics']['line']['scope']['checksum']='2'
        with self.assertRaises(Exception):self.gate(b,n)

    def test_overflow(self):
        b,n=self.fixture();n['metrics']['line']['scope']['bits']='0x10'
        with self.assertRaises(Exception):self.gate(b,n)

    def test_empty_input_hashes(self):
        b,n=self.fixture();n['input_hashes']={}
        with self.assertRaises(Exception):self.gate(b,n)

    def test_conflicting_pin(self):
        b,n=self.fixture();n['input_hashes']={'/old':'b'*64}
        with self.assertRaises(Exception):self.gate(b,n)

    def test_actual_both_parent_receipts_and_full_OR(self):
        _,before,ledger,pins=a.baseline(a.BASE,a.BASE_SHA,789)
        for phase in (0,1):
            q,single,tgl,qpins=a.sample(phase,pins)
            self.assertEqual(len(tgl),2989)
            after=a.union_gate(before,single,789+phase)
            self.assertEqual(sum(len(rows) for rows in after['metrics'].values()),6162)
            self.assertEqual(after['tests'],before['tests']+[str(a.RUNS[phase]/'code.vdb')])
            before=after

    def test_bad_owner(self):
        q=json.loads(a.QUALS[0].read_text());q['architecture']['owners'][0]['requests']=187
        with self.assertRaises(Exception):a.qualification_gate(q,0)

    def test_wrong_fault_phase(self):
        q=json.loads(a.QUALS[0].read_text())
        with self.assertRaises(Exception):a.qualification_gate(q,1)

    def test_bad_epoch(self):
        q=json.loads(a.QUALS[0].read_text());q['cycles']['global_terminal_evidence']['VCD_EOF_timestamp']+=1
        with self.assertRaises(Exception):a.qualification_gate(q,0)

    def test_unknown_terminal(self):
        q=json.loads(a.QUALS[0].read_text());q['cycles']['global_terminal_evidence']['held_idle_until_EOF']=False
        with self.assertRaises(Exception):a.qualification_gate(q,0)

    def test_toggle_lost_bit(self):
        before={'s':dict(width=4,checksum='1',bits='0x1')}
        with self.assertRaises(Exception):a.toggle_gain(before,{'s':dict(width=4,checksum='1',bits='0x2')})

    def test_phase1_cannot_use789(self):
        with self.assertRaises(Exception):a.baseline(a.BASE,a.BASE_SHA,790)


if __name__=='__main__':unittest.main()
