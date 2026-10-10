from dataclasses import replace
import unittest

import prepare_mfpu_restart_word_boundary as m


class IndependentOracle(unittest.TestCase):
    def values(self):
        _, snapshots = m.gold()
        values = {('g75_result',0):6264, ('g75_result',4):0, ('num_failed',0):0, ('tohost',0):1}
        values.update({('mr_vrf',(p*512+i)*8):v for p,s in enumerate(snapshots) for i,v in enumerate(s)})
        for i,start in enumerate(m.STARTS):
            values['mr_before',i*8]=start
            for k,v in enumerate((512,11,0,0,0)): values['mr_csr',(i*5+k)*8]=v
        return values

    def test_complete_oracle(self):
        values=self.values(); m.oracle(lambda name,offset=0,size=8:values.get((name,offset)))
        self.assertEqual(len(m.source_bytes()),3200)
        self.assertEqual(m.decode(m.half_integer(40)),40)
        for phase,start in enumerate((508,511,0)):
            words=m.gold()[1][phase][24*16:]
            elements=[(word >> (16*k)) & 65535 for word in words for k in range(4)]
            self.assertEqual(elements,[m.half_integer(8)]*start+[m.half_integer(40)]*(512-start))

    def test_terminal_missing_failure_or_wrong_check_count(self):
        for key,value in [(('tohost',0),3),(('tohost',0),None),(('g75_result',0),6263),(('num_failed',0),1)]:
            values=self.values(); values[key]=value
            with self.assertRaises(ValueError): m.oracle(lambda name,offset=0,size=8:values.get((name,offset)))

    def test_full_source_unrelated_prefix_destination_and_CSR_negative(self):
        for key in [('mr_vrf',0),('mr_vrf',8*16*8),('mr_vrf',24*16*8),('mr_vrf',511*8),
                    ('mr_csr',0),('mr_csr',4*8),('mr_before',4*8)]:
            values=self.values(); values[key]^=1
            with self.assertRaises(ValueError): m.oracle(lambda name,offset=0,size=8:values.get((name,offset)))

    def test_reordered_phase_oracle_negative(self):
        values=self.values(); values['mr_before',0]=511
        with self.assertRaises(ValueError): m.oracle(lambda name,offset=0,size=8:values.get((name,offset)))


class ActualSpikeNegative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (m.OUT/'preflight.json').exists(): raise unittest.SkipTest('Actual Spike preflight not yet built')
        import json
        cls.record=json.loads((m.OUT/'preflight.json').read_bytes())
        cls.symbols=cls.record['symbols']
        cls.commits=m.reused.reused.old.shared.shared.spike_trace.parse_spike_commits(m.OUT/'spike.trace')

    def test_actual_complete_commits_and_pins(self):
        m.life.check(self.record['pins'])
        self.assertEqual(m.validate_commits(self.commits,self.symbols,m.OPCODE),self.record['checks'])

    def test_actual_target_missing_duplicate_reordered_wrongopcode(self):
        targets=[i for i,c in enumerate(self.commits) if c.pc==self.symbols['mr_target_fma']]
        first,second=targets[:2]
        variants=[self.commits[:first]+self.commits[first+1:],
                  self.commits[:first]+[self.commits[first]]+self.commits[first:],
                  self.commits[:first]+[replace(self.commits[first],instruction=0)]+self.commits[first+1:]]
        ordered=list(self.commits);ordered[first],ordered[second]=ordered[second],ordered[first];variants.append(ordered)
        for commits in variants:
            with self.assertRaises(ValueError):m.validate_commits(commits,self.symbols,m.OPCODE)

    def test_actual_full_source_register_corruption(self):
        index=next(i for i,c in enumerate(self.commits) if c.pc==self.symbols['mr_target_fma'])
        altered=dict(self.commits[index].vector_writes);altered[8]=0
        commits=list(self.commits);commits[index]=replace(commits[index],vector_writes=altered)
        with self.assertRaises(ValueError):m.validate_commits(commits,self.symbols,m.OPCODE)


if __name__=='__main__':unittest.main()
