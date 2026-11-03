import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from collect_shared_mul_ppa import collect

class CollectorTests(unittest.TestCase):
    def fixture(self, root):
        for name, area in (('baseline',100),('shared',80)):
            d=root/name;d.mkdir();(d/'source.sv').write_text('fixed source')
            (d/'status.json').write_text(json.dumps({'state':'PASS'}))
            (d/'manifest.json').write_text(json.dumps({'period_ns':1,'setup_uncertainty_ns':.15,
                'hashes':{'source.sv':hashlib.sha256(b'fixed source').hexdigest()}}))
            (d/'metrics.tsv').write_text(f'area_um2\t{area}\nclk_i_slack_ns\t-0.1\nclk_i_arrival_ns\t0.95\n')

    def test_reduction(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.fixture(root)
            self.assertAlmostEqual(collect(root)['area_reduction_percent'],20)

    def test_reject_changed_inputs(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.fixture(root);(root/'shared/source.sv').write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed input'):collect(root)

    def test_reject_incomplete(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.fixture(root);(root/'shared/status.json').write_text('{"state":"RUNNING"}')
            with self.assertRaisesRegex(ValueError,'not complete'):collect(root)

    def test_reject_invalid_area(self):
        for area in ('', 'nan', '0', '-1'):
            with self.subTest(area=area), tempfile.TemporaryDirectory() as t:
                root=Path(t);self.fixture(root)
                (root/'shared/metrics.tsv').write_text(
                    f'area_um2\t{area}\nclk_i_slack_ns\t0\nclk_i_arrival_ns\t0.85\n')
                with self.assertRaises(ValueError):collect(root)

if __name__=='__main__':unittest.main()
