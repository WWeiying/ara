"""Wrong builds, unchecked predecessors and non-beneficial experiments stop early."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_common_attention as r
import audit_attention as audit


class CommonRunTest(unittest.TestCase):
    def test_wrong_build_rejected_before_artifacts(self):
        good=dict(state='COMMON_ENTRY_BUILT_NOT_EXECUTED',execution='NOT_RUN',post_pins_match=True,
            common_entry=True,mapping_timed=True,admission_timed=True,heads=6,head_dim=128,
            visible_tokens=128,expected_commands=16,trials=4,outputs_per_trial=768,kv_head=0,
            exact_scale_bits='3db504f3',kind='q8_0')
        for key,value in [('state','BUILT_NOT_EXECUTED'),('execution','RUN'),('post_pins_match',False),
            ('common_entry',False),('mapping_timed',False),('admission_timed',False),('heads',1),
            ('expected_commands',0),('exact_scale_bits','3db504ed')]:
            with self.subTest(key=key),patch.object(r.s,'read_json',return_value=dict(good,**{key:value})), \
                    patch.object(r.s,'digest') as digest:
                with self.assertRaises(ValueError): r.checked_build(Path('/unused'))
                digest.assert_not_called()

    def test_unchecked_predecessor_rejected(self):
        status=dict(state='PASS',child_pid=None)
        result=dict(state='PASS',post_pins_match=True,simulator_exit_code=0,independent_protocol_checked=True)
        for source,key,value in [('status','state','RUNNING'),('status','child_pid',12),
            ('result','state','FAIL'),('result','post_pins_match',False),
            ('result','simulator_exit_code',1),('result','independent_protocol_checked',False)]:
            a,b=dict(status),dict(result)
            (a if source=='status' else b)[key]=value
            with self.subTest(source=source,key=key),patch.object(audit.s,'read_json',side_effect=[a,b]), \
                    patch.object(audit.s,'digest') as digest:
                with self.assertRaises(ValueError): audit.checked_attention(Path('/unused'))
                digest.assert_not_called()

    def test_no_benefit_does_not_launch_vcs(self):
        with tempfile.TemporaryDirectory(prefix='common-no-benefit-') as tmp:
            root=Path(tmp); build=root/'build'; prior=root/'prior'; out=root/'run'
            build.mkdir(); prior.mkdir()
            (prior/'status.json').write_text(json.dumps(dict(build=str(build))))
            (prior/'result.json').write_text('{}')
            image={'image':'pin'}
            report=dict(kind='q8_0',accepted_image_pins=image,original_build=str(build),
                elf='/unused/elf',simv='/unused/simv')
            args=argparse.Namespace(build=build,prerequisite=prior,output=out,timeout=10)
            with patch.object(r,'checked_build',return_value=(report,{})), \
                    patch.object(r,'checked_attention',return_value=(dict(kind='q8_0'),image,{},
                        dict(speedup=0.99,sums={'0':99,'1':100}))), \
                    patch.object(r.s,'hashes',return_value={}),patch.object(r.s,'verify_pins'), \
                    patch.object(r.Execution,'execute') as execute:
                r.run(args)
                execute.assert_not_called()
            result=json.loads((out/'result.json').read_text())
            self.assertEqual(result['state'],'NO_BENEFIT_NOT_RUN')
            self.assertTrue(result['prior_functionally_passed'])
            self.assertEqual(json.loads((out/'status.json').read_text())['state'],'NO_BENEFIT_NOT_RUN')


if __name__=='__main__': unittest.main()
