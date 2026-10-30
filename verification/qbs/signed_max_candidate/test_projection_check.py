"""Protocol-only mutations; converted historical text is not performance evidence."""
import json
from pathlib import Path
import unittest

from check_projection import check_output, ORDER

ROOT = Path(__file__).resolve().parents[3]


class Protocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT/'verification/qbs/combined_zvfh_m4/projection/build-03/contract.json').read_text())
        cls.contract.update(order=ORDER, both_vector_paths_required=True)
        cls.text = (ROOT/'verification/out/q8k-current-projection-vcs-20261026-01/work/run.vcs.log').read_text()
        cls.text = '\n'.join(line for line in cls.text.splitlines() if 'Q8K_CURRENT' in line)
        cls.text = cls.text.replace('path=generic', 'path=accepted_vector').replace('path=canonical', 'path=signed_max')
        cls.text = cls.text.replace('used=0', 'used=1')

    def test_protocol_and_labels(self):
        result = check_output(self.text, self.contract)
        self.assertEqual([r['path'] for r in result['trials']], ORDER)
        self.assertEqual(set(result['sums']), {'accepted_vector', 'signed_max'})
        self.assertTrue(all(r['used'] == 1 for r in result['trials']))

    def test_reject_mutants(self):
        for before, after in [('used=1', 'used=0'), ('path=signed_max', 'path=canonical'),
                              ('errors=0', 'errors=1'), ('prep_vcsr=5', 'prep_vcsr=4'),
                              ('commands=48', 'commands=47')]:
            with self.subTest(before=before), self.assertRaises(ValueError):
                check_output(self.text.replace(before, after, 1), self.contract)


if __name__ == '__main__':
    unittest.main()
