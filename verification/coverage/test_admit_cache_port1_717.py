import copy
import json
import unittest

import admit_cache_port1_717 as m


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {key: json.loads((m.CANDIDATE / name).read_bytes()) for key, name in (
            ('sample', 'sample-bits.json'), ('combined', 'proposed-combined-bits.json'),
            ('status', 'status.json'), ('hits', 'target-hit-audit.json'), ('delta', 'raw-bitmap-delta.json'),
            ('scalar', 'scalar-comparison.json'), ('vector', 'vector-comparison.json'),
            ('architecture', 'architecture-audit.json'), ('contract', 'contract-audit.json'))}
        cls.data['before'] = json.loads((m.audit.BASE / 'combined-bits.json').read_bytes())
        cls.data['targets'] = json.loads((m.audit.runner.PRE / 'target-before.json').read_bytes())
        cls.data['inputs'] = (m.CANDIDATE / 'proposed-inputs.txt').read_text()

    def test_actual_candidate(self):
        m.validate(self.data)

    def reject(self, change):
        data = copy.deepcopy(self.data)
        change(data)
        with self.assertRaises(ValueError):
            m.validate(data)

    def test_extra_member(self):
        self.reject(lambda d: d['combined']['tests'].append('unproven.vdb'))

    def test_changed_prefix(self):
        self.reject(lambda d: d['combined']['tests'].reverse())

    def test_false_replay_claim(self):
        self.reject(lambda d: d['hits'].update(replay_FSM_sample_observed=True))

    def test_false_fsm_gain(self):
        self.reject(lambda d: d['delta']['metrics'].update(fsm=1))

    def test_scalar_bool_not_count(self):
        self.reject(lambda d: d['scalar'].update(skipped_unobservable_register_values=False))

    def test_wrong_signature(self):
        self.reject(lambda d: d['architecture'].update(checks=34))

    def test_vector_pass_not_zero_unobservable(self):
        self.reject(lambda d: d['vector'].update(status='PASS'))


if __name__ == '__main__':
    unittest.main()
