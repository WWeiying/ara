import json
from pathlib import Path
import tempfile
from types import FunctionType, SimpleNamespace
import unittest
from unittest.mock import patch

import collect_scalar_c910_pattern795_v2 as a


class RunnerAPI(unittest.TestCase):
    def test_real_complete_consumer_API_and_converter_identity(self):
        proxy=a.private_runner()
        self.assertEqual(a.runner_references(a.original.frozen.collect)|
            a.runner_references(a.original.frozen.original.terminal_gate),a.EXPECTED_API)
        self.assertIs(proxy.reused,a.original.runner.old.reused)
        self.assertEqual(proxy.reused.lifecycle.converter.CONVERTER_SHA,
            a.life.digest(proxy.reused.lifecycle.converter.CONVERTER))
        self.assertFalse(hasattr(a.original.runner,'reused'))

    def test_exact_consumer_dependencies_cannot_expand_silently(self):
        with patch.object(a,'runner_references',return_value=a.EXPECTED_API|{'missing'}):
            with self.assertRaises(ValueError):a.private_runner()

    def test_wrong_frozen_source_or_converter_rejected(self):
        digest=a.life.digest
        for module in (a.original,a.original.runner,a.original.frozen):
            target=Path(module.__file__)
            with patch.object(a.life,'digest',side_effect=lambda p:'bad' if Path(p)==target else digest(p)):
                with self.assertRaises(ValueError):a.private_runner()
        target=a.original.runner.old.reused.lifecycle.converter.CONVERTER
        with patch.object(a.life,'digest',side_effect=lambda p:'bad' if Path(p)==target else digest(p)):
            with self.assertRaises(ValueError):a.private_runner()

    def inherited_prefix(self,missing=False):
        # Execute the real inherited full collector through its converter invocation.
        # Only IO/architecture fixtures are substituted; the runner API expression is untouched.
        class ReachedConverter(Exception):pass
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';run.mkdir();out=root/'qualification'
            (run/'console.log').write_text('fixture')
            (run/'commit_trace.csv').write_text('event\nretire\n')
            (run/'vector_trace.csv').write_text('event\nconfig\n')
            (run/'scalar-div-subnormal794.vpd').write_bytes(b'vpd')
            proxy=a.private_runner();proxy.verify=lambda *args,**kwargs:None
            if missing:del proxy.reused
            record={'source_contract':{}}
            fake_life=SimpleNamespace(read_bound=lambda p,h:record,
                save=lambda p,v:p.write_text(json.dumps(v)),digest=a.life.digest)
            def subprocess_run(command,**kw):
                calls.append((command,kw));raise ReachedConverter()
            arch=SimpleNamespace(spike_trace=SimpleNamespace(compare_commit_prefix=lambda *args,**kwargs:{}))
            old=SimpleNamespace(oracle=SimpleNamespace(prior=SimpleNamespace(old=SimpleNamespace(architecture=arch))))
            g=dict(a.original.frozen.collect.__globals__,runner=proxy,life=fake_life,original=old,
                terminal_gate=lambda *args:None,stdout_gate=lambda text:None,
                architecture=lambda *args:{},subprocess=SimpleNamespace(run=subprocess_run,STDOUT=-2))
            fn=FunctionType(a.original.frozen.collect.__code__,g)
            with self.assertRaises(AttributeError if missing else ReachedConverter):fn(run,out,'seal')
            failure=json.loads((out/'failure.json').read_text())
            self.assertEqual(failure['status'],'HOLD_NOT_ADMITTED')
            if missing:self.assertIn('reused',failure['reason']);self.assertFalse(calls)
            else:
                self.assertEqual(calls[0][0],[str(proxy.reused.lifecycle.converter.CONVERTER),
                    str(run/'scalar-div-subnormal794.vpd'),str(out/'probe.vcd')])
                self.assertEqual(calls[0][1]['stderr'],-2)
                self.assertTrue(calls[0][1]['check']);self.assertEqual(calls[0][1]['timeout'],120)

    def test_actual_inherited_call_chain_resolves_converter(self):self.inherited_prefix()

    def test_actual_inherited_missing_API_reproduces_original_failure(self):self.inherited_prefix(missing=True)

    def test_original_collect_clone_uses_only_private_runner(self):
        class Dispatch(Exception):pass
        def factory(code,namespace):
            self.assertIs(code,a.original.collect.__code__)
            self.assertIsNot(namespace['runner'],a.original.runner)
            self.assertIs(namespace['runner'].reused,a.original.runner.old.reused)
            def stop(*args):raise Dispatch()
            return stop
        with patch.object(a,'FunctionType',side_effect=factory):
            with self.assertRaises(Dispatch):a.collect(None,None,'seal')
        self.assertFalse(hasattr(a.original.runner,'reused'))

    def test_qualification_publication_remains_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            core=Path(tmp)/'qualification.json';a.life.save(core,{'sentinel':'unchanged'})
            raw=core.read_bytes()
            with self.assertRaises(FileExistsError):a.life.save(core,{'bad':True})
            self.assertEqual(core.read_bytes(),raw)


if __name__=='__main__':unittest.main()
