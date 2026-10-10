import copy
import json
import unittest

import rebind_qbs_m8_phase8_payload_723 as r


class RebindTests(unittest.TestCase):
    def setUp(self):
        self.targets = json.loads(r.PARENT.read_bytes())['targets']
        self.metric = dict(width=21503, checksum='2947893042', bits='0')

    def test_full_identity(self):
        r.reconcile(self.targets, copy.deepcopy(self.targets), self.metric)

    def test_checksum_or_native_signature_drift_rejected(self):
        changed = copy.deepcopy(self.targets)
        changed[0]['attributes']['chksum'] = '0'
        with self.assertRaisesRegex(ValueError, 'full compiled'):
            r.reconcile(self.targets, changed, self.metric)
        self.metric['checksum'] = 0
        with self.assertRaisesRegex(ValueError, 'metric identity'):
            r.reconcile(self.targets, self.targets, self.metric)

    def test_hit_and_missing_target_rejected(self):
        self.metric['bits'] = hex(1 << (21503-1-6475))
        with self.assertRaisesRegex(ValueError, 'already hit'):
            r.reconcile(self.targets, self.targets, self.metric)
        with self.assertRaisesRegex(ValueError, 'target count'):
            r.reconcile(self.targets, self.targets[:-1], self.metric)


if __name__ == '__main__':
    unittest.main()
