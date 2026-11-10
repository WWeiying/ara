#!/usr/bin/env python3
import copy
from collections import Counter
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('complete_call_runner_test', HERE/'run.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def rows(kind):
    _,_,old = r.legacy()
    result = []
    for i,expected in enumerate(r.expected_akv(kind),1):
        row = dict.fromkeys(old.PERF_FIELDS,0)
        row.update(expected)
        row.update(seq=i,success=1,busy_cycles=100,context_ready=int(row['command'] != 3))
        row['read_payload_bytes'] = row['q_external_bytes']+row['kv_external_bytes']+64*row['v2_full']
        result.append(row)
    return result


def text(rows):
    _,_,old = r.legacy()
    totals = Counter()
    for row in rows:
        for key in old.SUMMARY_FIELDS-{'records','success_records','fault_records','validation_fault_records'}:
            totals[key] = max(totals[key],row[key]) if key == 'read_outstanding_max' else totals[key]+row[key]
    totals.update(records=len(rows),success_records=len(rows),fault_records=0,validation_fault_records=0)
    fmt = lambda row:' '.join(f'{k}={v}' for k,v in row.items())
    return '\n'.join(['[AKV_PERF] '+fmt(row) for row in rows]+['[AKV_PERF_SUMMARY] '+fmt(totals)])


class RunTests(unittest.TestCase):
    def test_exact_work_and_lifecycle(self):
        for kind,commands,counts in (('smoke',4,[4]),('abba',482,[237,4,4,237])):
            result = r.check_akv(text(rows(kind)),kind)
            self.assertEqual(result['commands'],commands)
            self.assertEqual(result['per_call_commands'],counts)
        self.assertEqual([x['command'] for x in r.expected_akv('smoke')],[4,5,5,3])

    def test_omitted_or_duplicated_commands_rejected(self):
        source = rows('abba')
        for altered in (source[:-1],source+[source[-1]],source[:237]+source[238:]):
            for i,row in enumerate(altered,1): row['seq'] = i
            with self.assertRaises(ValueError): r.check_akv(text(altered),'abba')

    def test_payload_fault_and_lifetime_mutations_rejected(self):
        source = rows('smoke')
        for key,value in (('q_external_bytes',0),('kv_external_bytes',0),('read_payload_bytes',0),
                          ('context_ready',0),('success',0),('validation_fault',1),('busy_cycles',0)):
            altered = copy.deepcopy(source)
            altered[0][key] = value
            with self.assertRaises(ValueError,msg=key): r.check_akv(text(altered),'smoke')
        with self.assertRaises(ValueError): r.check_akv(text(source)+ '\n[AKV_PERF] x=1','smoke')

    def test_numerical_oracle_unchanged_and_label_updated(self):
        class Checker:
            def check_numerical(self, log, software):
                self.asserted = (log,software)
                return dict(complete_call_cycles=[100,80,82,102],
                            complete_call_strong_rotation_over_resident_pv=101/81,
                            complete_call_reduction_fraction=1-81/101,numerical_checked=True)
        old = Checker()
        sw = dict(kind='abba')
        with patch.object(r,'legacy',return_value=(old,old,None)):
            result = r.check_numerical('unchanged log',sw)
        self.assertEqual(old.asserted,('unchanged log',sw))
        self.assertEqual(result['complete_call_mean_cycles'],dict(rvv=101,resident_qk_pv=81))
        self.assertEqual(result['rvv_over_resident_qk_pv'],101/81)
        self.assertNotIn('complete_call_strong_rotation_over_resident_pv',result)

    def test_both_frozen_firmware_builds_valid(self):
        for kind in ('smoke','abba'):
            receipt,pins = r.software(r.b.OUT/('stage3_attention_build_'+kind+'_20261110_01'))
            self.assertEqual(receipt['kind'],kind)
            self.assertIn(receipt['elf'],pins)
            self.assertIn(receipt['golden']['native_tile64'],pins)

    def test_frozen_worker_and_single_attempt_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'source-pins.json').write_text('{}')
            review = r.b.sha(out/'source-pins.json')
            with patch.object(r,'verify_prepared',return_value=({'python':'/usr/bin/python3'},)):
                command = r.service_command(out,review)
                self.assertIn(str(out/'inputs/run.py'),command)
                self.assertIn('--property=KillMode=control-group',command)
                self.assertNotIn('nohup',command)
                (out/'attempt.json').write_text('{}')
                with self.assertRaises(ValueError): r.service_command(out,review)

    def test_legacy_helpers_and_protocol_inventory(self):
        smoke,_,_ = r.legacy()
        self.assertTrue(smoke.checker_inventory())
        self.assertTrue(all((r.ROOT/p).is_file() for p in r.LEGACY))
        self.assertTrue((r.SHARED/'geometry.py').is_file())

    def test_executed_receipts_must_match_reviewed_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'work').mkdir()
            (out/'source-pins.json').write_text('{}')
            plan = dict(commands=dict(simulation=['simv','+original'],protocol=['python','checker']))
            owner = dict(unit=r.service_unit(out),main_pid=42,owner_pid=42,
                         cgroup='/user.slice/'+r.service_unit(out))
            r.b.save(out/'owner.json',owner)
            r.b.save(out/'attempt.json',dict(review_sha256=r.b.sha(out/'source-pins.json'),**owner))
            originals = {}
            for name,key,seconds in (('console','simulation',5400),('checker','protocol',900)):
                p = out/'work'/(name+'.command.json')
                originals[p] = dict(argv=plan['commands'][key],cwd=str(out/'work'),timeout_seconds=seconds)
                r.b.save(p,originals[p])
            r.execution_receipts(out,plan)
            for p,original in originals.items():
                for key,wrong in (('argv',['wrong-command']),('cwd','/wrong'),('timeout_seconds',1)):
                    p.write_text(json.dumps(dict(original,**{key:wrong})))
                    with self.assertRaises(ValueError): r.execution_receipts(out,plan)
                p.unlink()
                with self.assertRaises(FileNotFoundError): r.execution_receipts(out,plan)
                r.b.save(p,original)
            (out/'owner.json').write_text(json.dumps(dict(owner,main_pid=99)))
            with self.assertRaises(ValueError): r.execution_receipts(out,plan)


if __name__ == '__main__': unittest.main()
