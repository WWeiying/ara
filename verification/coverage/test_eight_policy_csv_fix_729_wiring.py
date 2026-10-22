import inspect
from pathlib import Path
import unittest
from unittest.mock import patch

import eight_policy_csv_fix_729_wiring as w


class WiringTests(unittest.TestCase):
    def test_context_uses_base_gates_and_exact729_identity(self):
        self.assertIs(w.Context.admission_inputs,w.identity.base.Context.admission_inputs)
        self.assertIs(w.Context.check_config,w.identity.base.Context.check_config)
        self.assertIs(w.Context.pin,w.identity.Context.pin)

    def test_no_global_mutation_private_six_reader(self):
        old_reader=w.eight.six.read_config
        api=w.eight_backend()
        self.assertIs(w.eight.six.read_config,old_reader)
        self.assertIs(api.prepare.__globals__['six'].read_config,w.read_six)
        self.assertIs(api.read_config.__globals__['six'].read_config,w.read_six)
        self.assertEqual(api.prepare.__code__,w.eight.prepare.__code__)
        self.assertEqual(api.read_config.__code__,w.eight.read_config.__code__)

    def test_csv_reader_and_verifier_consume_same_private_family(self):
        old_eight=w.fixed.eight
        api=w.fixed_backend()
        self.assertIs(w.fixed.eight,old_eight)
        self.assertIs(api.read_config.__globals__['eight'].read_config.__globals__['six'].read_config,w.read_six)
        self.assertIs(api.verify.__globals__['read_config'],api.read_config)
        self.assertEqual(api.verify.__code__,w.fixed.verify.__code__)
        self.assertTrue({w.SCRIPT,w.TEST,w.identity.SCRIPT,w.identity.TEST}<=set(api.dependencies()))

    def test_foreground_runner_consumes_actual_adapter_and_pins(self):
        api=w.runner_backend()
        self.assertIs(api.SCRIPT,w.SCRIPT)
        self.assertIs(api.invoke_run.__globals__['generic'],api.generic)
        self.assertIs(api.generic.read_config.__globals__['eight'].read_config.__globals__['six'].read_config,w.read_six)
        self.assertIs(api.generic.six.read_config,w.read_six)
        self.assertIn('generic.verify',inspect.getsource(api.invoke_run))
        self.assertIn("open('x')",inspect.getsource(api.claim_once))

    def test_source_binding_pins_consumer_code_without_changing_parent(self):
        context=w.Context(w.identity.ADMISSION,w.identity.ADMISSION_SEAL,729)
        pins={}
        with patch.object(w.identity.Context,'source_binding',return_value={'preserved_gate':True}):
            result=context.source_binding(pins)
        self.assertTrue(result['preserved_gate'])
        self.assertEqual(result['actual_consumer_wiring'],{str(p):w.frozen.sha(p) for p in (w.SCRIPT,w.TEST)})
        self.assertTrue(result['actual_consumer_wiring'].items()<=pins.items())

    def test_cli_has_no_eda_launch_mode(self):
        text=inspect.getsource(w.main)
        self.assertNotIn('run-reviewed',text)
        self.assertNotIn('Popen',text)


if __name__=='__main__':unittest.main()
