import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
from audit_fp16_repair_shards import audit


class ExecutedUnionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'outcomes').mkdir()
        for s in range(32):
            ids = set(range(s, 464, 32))
            bits = [sum(1 << (i % 64) for i in ids if i // 64 == word)
                    for word in range(8)]
            text = (f'vfncvt_int8: {len(ids)} cases, VLEN=1024\n'
                    f'vfncvt_int8_checks: ordinals=464 bytes=100 active=50 csr={3 * len(ids)}\n'
                    'vfncvt_int8_ids: ' + ' '.join(f'{b:x}' for b in bits) + '\n')
            console = self.root / f's{s}/console.log'
            console.parent.mkdir()
            console.write_text(text)
            record = {'status': 'PASS', 'passed_only': True,
                      'files': {str(console): hashlib.sha256(console.read_bytes()).hexdigest()}}
            self.outcome(s).write_text(json.dumps(record))

    def outcome(self, s):
        return self.root / 'outcomes' / f'extra-rvv-repair_fp16_int8_s{s}.json'

    def test_complete_union(self):
        self.assertEqual(audit(self.root)['cases'], 464)

    def test_timeout_is_not_partial_credit(self):
        p = self.outcome(31)
        record = json.loads(p.read_text())
        record['status'] = 'TIMEOUT'
        p.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_modified_console_rejected(self):
        (self.root / 's0/console.log').write_text('vfncvt_int8: 15 cases, VLEN=1024\n')
        with self.assertRaises(ValueError):
            audit(self.root)


if __name__ == '__main__':
    unittest.main()
