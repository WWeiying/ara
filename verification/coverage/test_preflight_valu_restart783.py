"""Independent fixture/gate negatives and actual Spike trace replay."""
from dataclasses import replace
import json
import unittest

import preflight_valu_restart783 as m


def values():
    result = {('g75_result',0):m.CHECKS,('g75_result',4):0,('num_failed',0):0,('tohost',0):1}
    for i,pair in enumerate(m.gold()):
        for side,state in enumerate(pair):
            base = (i*2+side)*m.SNAP_BYTES
            for k,word in enumerate([m.GUARD]*8+state+[m.GUARD]*8):result['vr_snap',base+8*k] = word
        result['vr_requested',8*i] = m.STARTS[i]
        for k,word in enumerate((1024,3,0,0,0)):result['vr_csr',8*(i*5+k)] = word
    return result


class OracleTests(unittest.TestCase):
    def test_complete_before_after_and_guards(self):
        v = values();m.oracle(lambda name,offset=0,size=8:v.get((name,offset)))
        self.assertEqual(len(m.source_bytes()),3200)
        self.assertEqual(sum(len(pair[0])*8+len(pair[1])*8 for pair in m.gold()),98304)
        self.assertEqual(len(v)-4,m.CHECKS-400)

    def test_independent_byte_math_and_phase_reset(self):
        a,b,seed = m.source_groups()
        for i,pair in enumerate(m.gold()):
            before = b''.join(w.to_bytes(8,'little') for w in pair[0][128:256])
            after = b''.join(w.to_bytes(8,'little') for w in pair[1][128:256])
            if i%4==0:self.assertEqual(before,seed)
            start = m.STARTS[i]
            self.assertEqual(after[:start],before[:start])
            self.assertEqual(after[start:],bytes((a[k]+b[k])%256 for k in range(start,1024)))
            self.assertEqual(pair[0][:128],pair[1][:128])
            self.assertEqual(pair[0][256:],pair[1][256:])

    def test_terminal_missing_failed_or_wrong_count(self):
        for key,bad in ((('tohost',0),3),(('tohost',0),None),(('num_failed',0),1),(('g75_result',0),13143)):
            v = values();v[key] = bad
            with self.assertRaises(ValueError):m.oracle(lambda name,offset=0,size=8:v.get((name,offset)))

    def test_before_after_sources_prefix_active_and_guards(self):
        for side,word in ((0,0),(0,8),(0,8+128),(1,8+128),(1,8+255),(1,8+256),(1,8+511),(1,527)):
            v = values();v['vr_snap',side*m.SNAP_BYTES+word*8] ^= 1
            with self.assertRaises(ValueError):m.oracle(lambda name,offset=0,size=8:v.get((name,offset)))

    def test_reordered_start_and_each_csr(self):
        for key in [('vr_requested',0),*[('vr_csr',8*k) for k in range(5)]]:
            v = values();v[key] ^= 1
            with self.assertRaises(ValueError):m.oracle(lambda name,offset=0,size=8:v.get((name,offset)))


class ActualSpikeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((m.OUT/'preflight.json').read_text())
        cls.symbols = cls.record['symbols']
        cls.commits = m.shared.spike_trace.parse_spike_commits(m.OUT/'spike.trace')
        cls.targets = [i for i,c in enumerate(cls.commits) if c.pc==cls.symbols['vr_target_vadd']]

    def test_actual_pins_and_full_trace(self):
        m.life.check(self.record['pins'])
        self.assertEqual(m.validate_commits(self.commits,self.symbols),self.record['checks'])
        self.assertEqual(m.shared.reference_counts(self.commits,self.symbols),self.record['counts'])
        self.assertTrue(self.record['baseline']['exact782_prefix'])
        self.assertLessEqual(self.record['baseline']['remaining_candidate_positions'],422)

    def test_missing_duplicate_reordered_and_wrong_instruction(self):
        first,second = self.targets[0],self.targets[4]
        variants = [self.commits[:first]+self.commits[first+1:],
                    self.commits[:first]+[self.commits[first]]+self.commits[first:],
                    self.commits[:first]+[replace(self.commits[first],instruction=0)]+self.commits[first+1:]]
        swapped = list(self.commits);swapped[first],swapped[second] = swapped[second],swapped[first];variants.append(swapped)
        for trace in variants:
            with self.assertRaises(ValueError):m.validate_commits(trace,self.symbols)

    def test_foreign_register_and_corrupt_destination(self):
        first = self.targets[0]
        for reg in (0,8,15,16,24):
            writes = dict(self.commits[first].vector_writes)
            writes[reg] = writes.get(reg,0)^1
            trace = list(self.commits);trace[first] = replace(trace[first],vector_writes=writes)
            with self.assertRaises(ValueError):m.validate_commits(trace,self.symbols)

    def test_wrong_eew_vl_vstart_lmul_and_vtype(self):
        first = self.targets[0]
        for key,value in (('vector_sew',16),('vector_vl',1023),('vector_vstart',0),('vector_lmul','m4'),('vector_vtype',0)):
            trace = list(self.commits);trace[first] = replace(trace[first],**{key:value})
            with self.assertRaises(ValueError):m.validate_commits(trace,self.symbols)

    def test_wrong_csr_and_missing_csr_writer(self):
        first = next(i for i,c in enumerate(self.commits) if c.pc==self.symbols['vr_read_vl'])
        for writes in ({},{10:1023}):
            trace = list(self.commits);trace[first] = replace(trace[first],gpr_writes=writes)
            with self.assertRaises(ValueError):m.validate_commits(trace,self.symbols)

    def test_wrong_snapshot_and_missing_or_out_of_bounds_store(self):
        address = self.symbols['vr_snap']+64
        first = max(i for i,c in enumerate(self.commits) if any(a==address and d is not None for a,d in c.memory_accesses))
        original = self.commits[first]
        for mode in ('wrong','missing','out_of_bounds'):
            accesses = tuple((a,d^1 if a==address else d) for a,d in original.memory_accesses) if mode=='wrong' else \
                tuple((a+8 if mode=='out_of_bounds' and a==address else a,d) for a,d in original.memory_accesses if mode!='missing' or a!=address)
            trace = list(self.commits);trace[first] = replace(original,memory_accesses=accesses)
            with self.assertRaises(ValueError):m.validate_commits(trace,self.symbols)

    def test_source_guard_write_rejected(self):
        first = self.targets[0]
        trace = list(self.commits);trace[first] = replace(trace[first],memory_accesses=((self.symbols['vr_source'],m.GUARD),))
        with self.assertRaises(ValueError):m.validate_commits(trace,self.symbols)


if __name__=='__main__':unittest.main()
