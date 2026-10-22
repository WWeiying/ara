import copy
import json
import unittest

from finalize_gap37_control import stored_form


def fixture():
    return {'schema': 'fence-rvfi-elf-capture-controller-v1', 'status': 'PASS',
            'commit_evidence': {'rounds': [
                {'round': r, 'checked_stores': {k: {'cycle': k + 1, 'data': hex(k + r)}
                                               for k in range(0, 520, 8)}}
                for r in range(2)]}, 'uart': {'checks': 458, 'failures': 0}}


class SerializationRecovery(unittest.TestCase):
    def test_exact_json_semantics_without_input_mutation(self):
        proof = fixture()
        original = copy.deepcopy(proof)
        self.assertEqual(stored_form(proof), json.loads(json.dumps(proof)))
        self.assertEqual(proof, original)
        self.assertNotEqual(proof, stored_form(proof))

    def test_does_not_mask_changed_value(self):
        original = fixture()
        corrupted = copy.deepcopy(original)
        corrupted['commit_evidence']['rounds'][0]['checked_stores'][0]['data'] = '0xbad'
        self.assertNotEqual(stored_form(corrupted), json.loads(json.dumps(original)))

    def test_does_not_mask_other_fields(self):
        original = fixture()
        corrupted = copy.deepcopy(original)
        corrupted['uart']['failures'] = 1
        self.assertNotEqual(stored_form(corrupted), json.loads(json.dumps(original)))

    def test_reject_partial_and_extra_maps(self):
        for missing in (True, False):
            proof = fixture()
            stores = proof['commit_evidence']['rounds'][0]['checked_stores']
            if missing:
                del stores[512]
            else:
                stores[520] = {}
            with self.assertRaises(ValueError):
                stored_form(proof)

    def test_reject_noninteger_and_ambiguous_keys(self):
        for key in ('0', '00', False):
            proof = fixture()
            stores = proof['commit_evidence']['rounds'][0]['checked_stores']
            value = stores.pop(0)
            stores[key] = value
            with self.assertRaises(ValueError):
                stored_form(proof)

    def test_reject_wrong_schema_or_rounds(self):
        for key, value in (('schema', 'old'), ('status', 'REJECTED')):
            proof = fixture()
            proof[key] = value
            with self.assertRaises(ValueError):
                stored_form(proof)
        for rounds in ([], [fixture()['commit_evidence']['rounds'][0]]):
            proof = fixture()
            proof['commit_evidence']['rounds'] = rounds
            with self.assertRaises(ValueError):
                stored_form(proof)


if __name__ == '__main__':
    unittest.main()
