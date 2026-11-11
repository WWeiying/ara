import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import run as r


class Tests(unittest.TestCase):
    def test_real_frozen_worker_service_recipe(self):
        base = r.worker(r.BASE)
        with tempfile.TemporaryDirectory() as d:
            model = Path(d)/'model'; model.mkdir(); out = Path(d)/'launch'
            (model/'source-pins.json').write_text('{}')
            (model/'prepare.json').write_text(json.dumps(dict(state='PREPARED_NOT_EXECUTED', provider_granted=True)))
            ps, rs = r.sha(model/'source-pins.json'), r.sha(model/'prepare.json')
            old = base.service_command(model, ps, rs)
            new = r.command(base, model, ps, rs, out)
            at = old.index(str(model/'inputs/run.py'))
            want = old[:at]; want[want.index('--property=RuntimeMaxSec=6300')] = '--property=RuntimeMaxSec=10800'
            self.assertEqual(new[:at], want)
            self.assertIn('--property=MemoryMax=8G', new); self.assertIn('--property=CPUQuota=100%', new)
            self.assertEqual(new[at:], [str(out/'inputs/run.py'), 'run', '--output', str(out), '--review-sha256', r.PLACEHOLDER])
            self.assertEqual(r.GUEST_SECONDS, 5400); self.assertEqual(r.SERVICE_SECONDS-r.GUEST_SECONDS, 5400)
    def test_prelink_not_authorized(self):
        base = r.worker(r.BASE)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'source-pins.json').write_text('{}')
            (p/'prepare.json').write_text(json.dumps(dict(state='LINKED_PROVIDER_NOT_AUTHORIZED', provider_granted=False)))
            with self.assertRaises(ValueError): r.command(base, p, r.sha(p/'source-pins.json'), r.sha(p/'prepare.json'), p/'launch')
    def test_budget_mismatch_rejected(self):
        base=argparse.Namespace(service_command=lambda *a: ['--property=RuntimeMaxSec=6400'])
        with self.assertRaises(ValueError): r.command(base, Path('/m'), 'p', 'r', Path('/l'))
    def test_timing_preserves_return_and_exception(self):
        with tempfile.TemporaryDirectory() as d:
            t=r.Timing(Path(d)/'timings'); value=object(); fn=Mock(return_value=value)
            self.assertIs(t.wrap('verify',fn)({'x':'y'}),value); fn.assert_called_once_with({'x':'y'})
            error=ValueError('strict failure'); fail=Mock(side_effect=error)
            with self.assertRaises(ValueError) as cm: t.wrap('verify',fail)()
            self.assertIs(cm.exception,error);fail.assert_called_once_with()
            self.assertEqual([row['status'] for row in t.finished],['returned','raised'])
    def test_nested_timing_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            t=r.Timing(Path(d)/'timings'); inner=t.wrap('identity',lambda: 42)
            self.assertEqual(t.wrap('replay',inner)(),42)
            self.assertEqual([row['depth'] for row in t.finished],[1,0])
    def test_early_worker_rejection_retains_timing_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'timings';t=r.Timing(p)
            self.assertTrue(p.is_file());self.assertEqual(t.finished,[])
            self.assertEqual(r.sha(p),r.hashlib.sha256(b'').hexdigest())
    def test_guest_timeout_forwarded_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            child=argparse.Namespace(pid=123,wait=Mock(return_value=0))
            original_wait=child.wait
            process=argparse.Namespace(Popen=Mock(return_value=child))
            base=argparse.Namespace(verify=Mock(), checked_s3=Mock(),load=Mock(),subprocess=process)
            r.instrument(base,Path('/m'),r.Timing(Path(d)/'timings'))
            actual=base.subprocess.Popen(['qemu'],stdout=5)
            self.assertIs(actual,child);self.assertEqual(actual.wait(timeout=5400),0)
            process.Popen.assert_called_once_with(['qemu'],stdout=5)
            original_wait.assert_called_once_with(timeout=5400)
    def test_full_checker_result_and_exception_retained(self):
        with tempfile.TemporaryDirectory() as d:
            check=Mock(return_value={'strict':'proof'}); module=argparse.Namespace(check=check)
            base=argparse.Namespace(verify=Mock(),checked_s3=Mock(),load=Mock(return_value=module),subprocess=Mock())
            r.instrument(base,Path('/m'),r.Timing(Path(d)/'timings'))
            self.assertEqual(base.load(Path('/m/inputs/check.py'),'checker').check('/m'),{'strict':'proof'})
            check.assert_called_once_with('/m')
            check.side_effect=ValueError('numerical mismatch')
            with self.assertRaisesRegex(ValueError,'numerical mismatch'):module.check('/m')
    def test_no_direct_launch_or_automatic_retry(self):
        self.assertEqual(r.PLACEHOLDER,'@LAUNCH_PINS_SHA256@')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):r.fresh(Path(d))
    def test_json_duplicates_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x'
            for text in ('{"x":1,"x":2}','{"x":NaN}'):
                p.write_text(text)
                with self.assertRaises(ValueError):r.read(p)


if __name__=='__main__':unittest.main()
