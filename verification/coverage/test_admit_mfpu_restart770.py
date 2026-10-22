import copy
import json
import unittest
import admit_mfpu_restart770 as a


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.q=json.loads((a.QUAL/'qualification.json').read_bytes())
    def reject(self,change):
        q=copy.deepcopy(self.q);change(q)
        with self.assertRaises(ValueError):a.contract(q)
    def test_actual_qualified(self):a.contract(self.q)
    def test_failed(self):self.reject(lambda q:q.update(status='FAILED'))
    def test_missing_checks(self):self.reject(lambda q:q.update(software_checks=6263))
    def test_missing_CSR(self):self.reject(lambda q:q.update(CSR_words=59))
    def test_short_VRF(self):self.reject(lambda q:q.update(full_VRF_snapshot_bytes=4096))
    def test_short_guards(self):self.reject(lambda q:q.update(source_guard_bytes=3199))
    def test_response_loss(self):self.reject(lambda q:q['lifecycle'].update(responses=224))
    def test_backend_loss(self):self.reject(lambda q:q['lifecycle'].update(backend_uops=145))
    def test_pending(self):self.reject(lambda q:q['protocol']['last'].update(after=1))
    def test_unknown_vector(self):self.reject(lambda q:q['vector'].update(skipped_unknown_bytes=1))
    def test_partial_vector(self):self.reject(lambda q:q['vector'].update(compared_bytes=14375))
    def test_missing_per_FMA(self):self.reject(lambda q:q['per_instruction_FMA_oracles'].pop())
    def test_wrong_restart(self):self.reject(lambda q:q['per_instruction_FMA_oracles'][0].update(start=0))
    def test_zero_gain(self):self.reject(lambda q:q['raw_gain'].update(target_new_serialized_positions=0))
    def test_old_base(self):self.reject(lambda q:q['raw_gain'].update(baseline=768))
    def test_foreign_source_seal(self):self.reject(lambda q:q['raw_gain'].update(baseline_seal='0'*64))
    def test_duplicate_769(self):
        with self.assertRaises(ValueError):a.union({'tests':['same']*769},{'tests':[str(a.case.OUT/'code.vdb')]})
    def test_foreign_single(self):
        with self.assertRaises(ValueError):a.union({'tests':[str(i) for i in range(769)]},{'tests':['foreign']})
    def test_expected_pin_conflict(self):
        with self.assertRaises(ValueError):a.life.merge_pins({'/f':'a'*64},{'/f':'b'*64})
    def test_actual_complete_parent_replay(self):
        replay=a.life.read_bound(a.REPLAY/'qualification.json',a.REPLAY_SHA)
        a.replay_equal(self.q,replay)
    def test_replay_scalar_mutation(self):
        q=copy.deepcopy(self.q);q['scalar']['matched_scalar_writes']-=1
        with self.assertRaises(ValueError):a.replay_equal(self.q,q)
    def test_replay_raw_position_mutation(self):
        q=copy.deepcopy(self.q)
        target=next(t for t in q['raw_gain']['target_objects'] if t['new_serialized_positions'])
        target['new_serialized_positions'][0]+=1
        with self.assertRaises(ValueError):a.replay_equal(self.q,q)
    def test_replay_schema_extra(self):
        q=copy.deepcopy(self.q);q['unexpected']=True
        with self.assertRaises(ValueError):a.replay_equal(self.q,q)


if __name__=='__main__':unittest.main()
