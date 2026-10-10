import json
import unittest
from unittest.mock import patch

import capture_sldu_two763_json as c
import test_capture_sldu_two763 as original


class JsonNativeTests(original.NativeTests):
    def setUp(self):
        self.binding=patch.object(original,'c',c)
        self.binding.start()
        self.addCleanup(self.binding.stop)

    def test_canonical_owner_roundtrip_exact(self):
        _,owner,_=c.bound()
        canonical=json.loads(json.dumps(owner))
        self.assertNotEqual(owner,canonical)
        self.assertEqual(json.loads(json.dumps(owner)),canonical)
        bad=json.loads(json.dumps(owner))
        bad['issue_pointer_writers'][0][0]=915
        self.assertNotEqual(json.loads(json.dumps(owner)),bad)
        bad=json.loads(json.dumps(owner))
        bad['descriptor_writers'].pop()
        self.assertNotEqual(json.loads(json.dumps(owner)),bad)


if __name__=='__main__':unittest.main()
