import copy
import json
import unittest

import verify_qbs_payload_side1792_732_json as p


class CanonicalJSONTests(unittest.TestCase):
    def setUp(self):
        self.expected = dict(pins={'source':'hash'}, candidates=[('scope',1,'01')],
                             protected_count=41214, native_qualified=False)
        self.saved = json.loads(json.dumps(self.expected))

    def test_only_tuple_to_json_array(self):
        p.compare(self.saved,self.expected)

    def reject(self, mutate):
        changed=copy.deepcopy(self.saved);mutate(changed)
        with self.assertRaises(ValueError):p.compare(changed,self.expected)

    def test_pin_drift(self): self.reject(lambda d:d['pins'].update(source='wrong'))
    def test_scope_drift(self): self.reject(lambda d:d['candidates'][0].__setitem__(0,'other'))
    def test_vector_drift(self): self.reject(lambda d:d['candidates'][0].__setitem__(2,'11'))
    def test_missing_candidate(self): self.reject(lambda d:d['candidates'].clear())
    def test_protection_drift(self): self.reject(lambda d:d.update(protected_count=41213))
    def test_native_claim(self): self.reject(lambda d:d.update(native_qualified=True))
    def test_boolean_is_not_zero(self): self.reject(lambda d:d.update(native_qualified=0))
    def test_extra_field(self): self.reject(lambda d:d.update(apply=True))


if __name__ == '__main__':
    unittest.main()
