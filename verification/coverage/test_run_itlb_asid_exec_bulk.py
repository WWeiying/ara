import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import run_itlb_asid_exec_bulk as r


def record():
    output=r.life.OUT/'itlb-bulk-test-never-run'
    preflight=r.life.OUT/'itlb-asid-exec-bulk-preflight-agent-20261007-01/preflight.json'
    return dict(schema=r.SCHEMA,driver_variant=r.VARIANT,case=r.original.CASE,
        output=str(output),timeout_s=600,baseline=str(r.collector.BASE),
        baseline_seal=r.collector.BASE_SHA,measurement_base=773,
        preflight_seal=r.collector.PREFLIGHT_SHA,preflight_static_base=771,
        preflight=str(preflight),coverage_admitted=False,automatic_retry=False,
        command=r.command(preflight.parent/'input.elf',output))


class Runner(unittest.TestCase):
    def test_exact_record_and_bounded_flags(self):
        value=record();r.validate_record(value)
        self.assertIn('+NO_FSDB',value['command'])
        self.assertEqual(value['command'].count('-cm'),1)
        self.assertIn('line+cond+fsm+tgl+branch',value['command'])
        self.assertEqual(value['command'][-1],str(r.original.PROBE))

    def test_reject_command_base_timeout_or_authority_change(self):
        for key,value in [('timeout_s',601),('measurement_base',771),('automatic_retry',True),
            ('coverage_admitted',True),('baseline_seal','0'*64),('preflight_seal','0'*64),
            ('schema',r.original.__name__),('driver_variant','original')]:
            data=record();data[key]=value
            with self.assertRaises(ValueError):r.validate_record(data)
        data=record();data['command'].append('+FSDB')
        with self.assertRaises(ValueError):r.validate_record(data)

    def test_wrong_preflight_rejected_before_read_or_run(self):
        with patch.object(r.life,'read_bound',side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError,'preflight seal'):
                r.prepare(Path('/foreign'),'0'*64,r.life.OUT/'never-created')

    def test_retained_bulk_preflight_exact_reference(self):
        path=Path(record()['preflight'])
        q=r.life.read_bound(path,r.collector.PREFLIGHT_SHA)
        self.assertEqual(q['counts']['matched_instructions'],103572)
        self.assertEqual(q['software_checks'],10966)
        self.assertEqual(q['trap_count'],48)


if __name__=='__main__':unittest.main()
