import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
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

    def test_binding_pins_include_exact_successor_and_ancestry(self):
        pins=r.binding_pins()
        self.assertEqual(pins[str(r.READER)],r.READER_SHA)
        self.assertIn(str(r.ORIGINAL/'run.py'),pins)
        self.assertIn(str(r.V3/'result.json'),pins)
    def test_model_prepare_binds_adapter_without_editing_worker(self):
        base=argparse.Namespace(sealed_inputs=lambda:{'original':'ancestry'},prepare=Mock())
        with patch.object(r,'HERE',r.ORIGINAL),patch.object(r,'worker',return_value=base):
            args=argparse.Namespace(binding_source_sha256=r.identity())
            r.model_prepare(args)
            base.prepare.assert_called_once_with(args)
            self.assertEqual(args.source_sha256,r.V2_SOURCE_SHA)
            self.assertEqual((args.s3_reader,args.s3_reader_sha256),(r.READER,r.READER_SHA))
            self.assertEqual(base.sealed_inputs(),{'original':'ancestry',**r.binding_pins()})
    def test_model_requires_recorded_binding_closure(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);c=dict(s3_reader=str(r.READER),s3_reader_sha256=r.READER_SHA,s3=dict(r.ADMITTED_IMAGE))
            (p/'contract.json').write_text(json.dumps(c));pins=r.binding_pins()
            (p/'source-pins.json').write_text(json.dumps(pins))
            self.assertEqual(r.model_binding(p),c)
            del pins[str(r.ORIGINAL/'run.py')]
            (p/'source-pins.json').write_text(json.dumps(pins))
            with self.assertRaises(ValueError):r.model_binding(p)
    def test_reader_rebind_preserves_full_original_call(self):
        report=dict(r.ADMITTED_IMAGE)
        pins={'x':'y'};original=Mock(return_value=(report,pins))
        base=argparse.Namespace(checked_s3=original);r.bind_reader(base)
        actual=base.checked_s3(r.READER,r.READER_SHA,Path('/aggregate'),'b'*64)
        self.assertIs(actual[0],report);self.assertIs(actual[1],pins)
        original.assert_called_once_with(r.READER,r.READER_SHA,Path('/aggregate'),'b'*64)
        for field,value in [('qemu_build',str(r.OUT/'stage5_qemu_build_20261110_06')),
                            ('qemu_build_receipt_sha256','93506639dda6fc22dc66733ca2160c5ba7b799787e8fb8f5e4d067ed37d3c3d6'),
                            ('executable_sha256','1deb41c75cc507030994765971d5a3d91f17e958c195bf60b4fb5563eb880a6f'),
                            ('qemu_prepare_receipt_sha256','0'*64)]:
            old=report[field];report[field]=value
            with self.assertRaises(ValueError):base.checked_s3(r.READER,r.READER_SHA,Path('/aggregate'),'b'*64)
            report[field]=old
        for field,value in [('scoped_qbs_audit','/old-audit'),('checker_correction_explicit',True),
                            ('original_qbs_execution_state','FAIL')]:
            report[field]=value
            with self.assertRaises(ValueError):base.checked_s3(r.READER,r.READER_SHA,Path('/aggregate'),'b'*64)
            del report[field]
    def test_wrong_reader_is_rejected_before_replay(self):
        original=Mock();base=r.bind_reader(argparse.Namespace(checked_s3=original))
        for path,digest in [(r.READER.with_name('run.py'),r.READER_SHA),
                            (r.READER.with_name('run_v3.py'),'2ba39edd9dcf9b62b9a136aa87929b654d4721df814bd1e4b20f0a4e43af5118'),
                            (r.READER,'0'*64)]:
            with self.assertRaises(ValueError):base.checked_s3(path,digest,'/aggregate','b'*64)
        original.assert_not_called()


if __name__=='__main__':unittest.main()
