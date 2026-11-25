import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('operator_campaign', HERE / 'campaign.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CampaignTests(unittest.TestCase):
    def test_success_and_real_failures(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'log'
            for suffix in ('', '\nUVM_ERROR : 0\nUVM_FATAL : 0\n'):
                p.write_text('Core Test *** SUCCESS ***' + suffix)
                c.successful_log(p)
            for suffix in ('\nUVM_ERROR : 1\n', '\nFatal: failed assertion', '\nFAILED', '\nError-[bad]'):
                p.write_text('Core Test *** SUCCESS ***' + suffix)
                with self.assertRaises(ValueError):
                    c.successful_log(p)
            p.write_text('simulation completed but no firmware result')
            with self.assertRaises(ValueError):
                c.successful_log(p)

    def test_source_pin_drift(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'input'; p.write_text('one')
            pins = {str(p): c.sha(p)}
            c.verify(pins)
            p.write_text('two')
            with self.assertRaises(RuntimeError):
                c.verify(pins)

    def test_no_duplicate_cases_or_excess_parallelism(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); m = root / 'manifest.json'
            with patch.object(c, 'OUT', root):
                for cases, parallel in (([], 1), ([{'id':'a'}, {'id':'a'}], 1),
                                        ([{'id':'../bad'}], 1), ([{'id':'ok'}], 5)):
                    m.write_text(json.dumps(dict(cases=cases)))
                    with self.assertRaises(ValueError):
                        c.prepare(root / 'operator_campaign_test', root / 'soc', m, parallel)

    def test_command_failure_not_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(RuntimeError):
                c.command(['/bin/false'], root, root/'log', {}, 5, root/'status.json', 'TEST')

    def test_preserve_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                c.prepare(Path(d), Path(d), Path(d), 4)


if __name__ == '__main__':
    unittest.main()
