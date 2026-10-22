from dataclasses import replace
import unittest
import run_mfpu_restart_word_boundary769 as m


class Gates(unittest.TestCase):
    def test_command(self):
        cmd=m.command(m.OUT)
        self.assertEqual(cmd.count('+COMMIT_TOHOST=80001000'),1)
        self.assertIn('+NO_FSDB',cmd)
        self.assertNotIn('-ucli',cmd)
        self.assertIn('+PRELOAD='+str(m.gold.OUT/'input.elf'),cmd)

    def test_formal769(self):
        _,ledger=m.baseline();self.assertEqual(len(ledger),770)
        self.assertEqual(len(set(ledger)),770)

    def test_vector_no_unknown_or_partial(self):
        clean=dict(status='PASS',skipped_unknown_bytes=0,non_bit_exact_instructions=0,
                   unobservable_instructions=0,incomplete_requests=[],unretired_requests=[],trapped_requests=[],
                   instructions=[dict(status='PASS',unknown_write_bytes=0,skipped_unknown_bytes=0,mismatch_count=0)])
        m.vector_gate(clean)
        for key,value in [('status','FAIL'),('skipped_unknown_bytes',1),('non_bit_exact_instructions',1),
                          ('unobservable_instructions',1),('incomplete_requests',[1]),('trapped_requests',[1])]:
            with self.assertRaises(ValueError):m.vector_gate(dict(clean,**{key:value}))
        bad=dict(clean,instructions=[dict(clean['instructions'][0],unknown_write_bytes=1)])
        with self.assertRaises(ValueError):m.vector_gate(bad)

    def test_protocol_exact_lastdrain_and_negatives(self):
        text=('\n'.join((
            '[ARA_CONTRACT_TRACE] sample=pre_edge cycle=15 req=1/1 fire=1 id=2 insn=b3041c57 resp=0/1 fire=0 id=0 exc=0 pending=00 stalled=00 errors=0000000',
            '[ARA_CONTRACT_TRACE] sample=pre_edge cycle=25 req=0/1 fire=0 id=0 insn=00000000 resp=1/1 fire=1 id=2 exc=0 pending=04 stalled=00 errors=0000000')))
        req=[(10,2,m.gold.OPCODE)];resp=[(20,2)]
        self.assertEqual(m.protocol(text,req,resp,30)['last']['after'],0)
        for bad in (text.replace('pending=04','pending=00'),text.replace('errors=0000000','errors=0000001'),
                    text.splitlines()[0],text.replace('cycle=25','cycle=24'),text.replace('id=2 insn','id=3 insn')):
            with self.assertRaises(ValueError):m.protocol(bad,req,resp,30)
        with self.assertRaises(ValueError):m.protocol(text,req,resp,20)

    def test_missing_scalar_and_lifecycle_rejected(self):
        with self.assertRaises(ValueError):m.scalar_check([],[],{'tohost':0x80001000})
        with self.assertRaises(ValueError):m.lifecycle([],[])


if __name__=='__main__':unittest.main()
