from pathlib import Path
import unittest
from unittest.mock import patch

import eight_policy_csv_fix_729_wiring_v2 as w


class EndpointTests(unittest.TestCase):
    def context(self):
        p=w.prior.identity
        return w.Context(p.ADMISSION,p.ADMISSION_SEAL,729)

    def test_actual_missing_main_readelf_alias_bound_only_by_sealed_endpoint(self):
        context=self.context();ledger=context.ledger();pins={}
        ledger_path=str(context.admission/'evidence-pins.json')
        manifest=w.frozen.load_sealed(context.admission/'admission-manifest.json',context.seal)
        pins[ledger_path]=manifest['output_pins'][ledger_path]
        with patch.object(w.prior.Context,'source_binding',return_value={'actual_consumer_wiring':{}}):
            result=context.source_binding(pins)
        link='/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-readelf'
        self.assertNotIn(link,ledger)
        proof=result['original_catalog_endpoint_binding'][link]
        self.assertEqual(proof['ledger_authority'],'/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-readobj')
        self.assertFalse(proof['historical_alias_invocation_claim'])
        self.assertEqual(pins[link],pins[proof['resolved']])
        self.assertEqual(pins[link],ledger[proof['ledger_authority']])
        self.assertTrue({str(w.SCRIPT),str(w.TEST)}<=result['actual_consumer_wiring'].keys())

    def test_missing_wrong_endpoint_authority_rejected(self):
        for ledger in ({},{'alias':'wrong'},{'endpoint':'wrong'}):
            context=self.context();context._ledger=ledger
            with patch.object(w.prior.Context,'source_binding',return_value={'actual_consumer_wiring':{}}),\
                 patch.dict(w.frozen.INHERITED_TOOL_LINKS,{'alias':'literal'},clear=True),\
                 patch.object(w.frozen,'tool_link_identity',return_value={
                     'link_target':'literal','resolved':'endpoint','sha256':'expected'}),self.assertRaises(ValueError):
                context.source_binding({})

    def test_complete_original_gates_and_private_consumers_preserved(self):
        self.assertIs(w.Context.admission_inputs,w.prior.Context.admission_inputs)
        self.assertIs(w.Context.check_config,w.prior.Context.check_config)
        old_reader=w.prior.eight.six.read_config
        api=w.eight_backend()
        self.assertIs(w.prior.eight.six.read_config,old_reader)
        self.assertIs(api.read_config.__globals__['six'].Context,w.Context)
        self.assertIs(w.fixed_backend().read_config.__globals__['eight'].read_config.__globals__['six'].Context,w.Context)
        runner=w.runner_backend()
        self.assertIs(runner.SCRIPT,w.SCRIPT)
        self.assertIs(runner.generic.six.Context,w.Context)
        self.assertIs(runner.invoke_run.__globals__['generic'],runner.generic)


if __name__=='__main__':unittest.main()
