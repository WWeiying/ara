import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import eight_policy_csv_fix_runtime as fix
import run_eight_policy_csv_fix as runner
import test_prepare_run_rvh_nine_policy as wiring


class CSVFixTests(unittest.TestCase):
    def test_real_snapshot_dependency_regression(self):
        case=wiring.WiringTests('test_real_csv_dependency_eight_snapshot_six_stages')
        case.test_real_csv_dependency_eight_snapshot_six_stages()

    def test_entry_helper_before_original_eight_source(self):
        text=fix.TCL.read_text()
        self.assertLess(text.index('csv-row-library.tcl'),text.index('lzc_snapshot_eight_policy_runtime.tcl'))
        self.assertLess(text.index('EIGHT_CSV_WRITER_INSTALLED'),text.index('lzc_snapshot_eight_policy_runtime.tcl'))
        self.assertNotIn('gui_',text)
        self.assertIn(fix.shared.CSV_SOURCE,fix.dependencies())

    def test_single_claim_private_lifecycle_unchanged(self):
        self.assertIn("open('x')",inspect.getsource(runner.claim_once))
        self.assertIs(runner.invoke_run.__globals__['generic'],fix)
        self.assertIs(fix.six,fix.eight.six)
        self.assertIn('generic.verify',inspect.getsource(runner.invoke_run))

    def test_synthetic_729_prepare_check_no_relabel_or_mutation(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);base=root/'base';out=root/'fixed';base.mkdir()
            for name in (*fix.eight.prior.HELPERS,'six-library.tcl','seven-selection.tcl',
                         'snapshot-selection.tcl','combined-eight.el','config.json'):
                (base/name).write_text('original '+name)
            pins={str(p):fix.frozen.sha(p) for p in base.iterdir()}
            source=dict(population=729,admission_sha256='formal729',pins=pins)
            (base/'runtime-plan.json').write_text(json.dumps(source))
            seal=fix.frozen.sha(base/'runtime-plan.json')
            before={str(p):fix.frozen.sha(p) for p in base.iterdir()}
            cfg=dict(population=729,admission_manifest_sha256='formal729',pins=pins,
                     plan={'tool_identity':{}},inputs=['design'])
            context=Mock()
            with patch.object(fix.frozen,'OUT',root),\
                 patch.object(fix.eight,'read_config',return_value=(context,cfg)),\
                 patch.object(fix.eight.prior.lifecycle.tool,'launch_command',return_value=['pinned-dve']):
                with self.assertRaises(ValueError):fix.prepare(out,base,seal,727)
                self.assertFalse(out.exists())
                plan=fix.prepare(out,base,seal,729)
                plan_seal=fix.frozen.sha(out/fix.PLAN)
                actual,derived=fix.read_config(out,plan_seal)
                self.assertIs(actual,context)
                self.assertEqual(derived['population'],729)
                self.assertEqual((plan['targets'],plan['protected'],plan['audited']),fix.COUNTS)
                self.assertEqual((out/'combined-eight.el').read_bytes(),(base/'combined-eight.el').read_bytes())
                self.assertEqual(before,{str(p):fix.frozen.sha(p) for p in base.iterdir()})
                self.assertFalse((out/'DVEfiles').exists())
                launch=runner.prepare_entry(out,plan_seal)
                launch_seal=fix.frozen.sha(out/runner.PLAN)
                self.assertEqual(runner.reviewed_entry(out,launch_seal)[2],derived)
                with self.assertRaises(ValueError):runner.prepare_entry(out,plan_seal)
                changed=copy.deepcopy(launch);changed['population']=727
                (out/runner.PLAN).write_text(json.dumps(changed))
                with self.assertRaises(ValueError):runner.reviewed_entry(out,fix.frozen.sha(out/runner.PLAN))
                helper=out/'csv-row-library.tcl';helper.write_text('proc csv_row {args} {}')
                with self.assertRaises(ValueError):fix.read_config(out,plan_seal)

    def test_csv_install_marker_required_even_after_core_verifier(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'DVEfiles').mkdir()
            (out/'DVEfiles/dve_gui.log').write_text('missing marker\n')
            # Replace only the core verifier for this marker negative test.
            def fake_verify(output,seal):return {'files':{}}
            with patch.object(fix.eight,'verify',fake_verify),self.assertRaises(ValueError):
                fix.verify(out,'seal')


if __name__=='__main__':unittest.main()
