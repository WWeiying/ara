from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import run_queue_mask_source_lifetime_simulation as r

class RunnerTests(unittest.TestCase):
    def setUp(self):self.out=r.life.OUT/'queue-mask-run-unit-not-created'
    def test_exact_command(self):
        c=r.command(self.out)
        self.assertEqual(c[0],str(r.life.IMAGE));self.assertEqual(c.count('+PRELOAD='+str(r.ELF)),1)
        self.assertIn('+NO_FSDB',c);self.assertIn('+COMMIT_TRACE='+str(self.out/'commit_trace.csv'),c)
        self.assertIn('+VECTOR_TRACE='+str(self.out/'vector_trace.csv'),c)
        self.assertNotIn('+ARA_DEBUG_GROUP_HAZARD',c)
    def test_budget(self):
        self.assertEqual(r.BUDGET,600);self.assertEqual(r.RETIREMENTS,96979)
    def test_unauthorized_run_rejected_before_prepare(self):
        with patch.object(r,'prepare',side_effect=AssertionError('must not prepare')):
            with self.assertRaises(ValueError):r.main(['run','--output',str(self.out),'--prepared-seal','a'*64])
    def test_verify_cannot_authorize(self):
        with self.assertRaises(ValueError):r.main(['verify','--output',str(self.out),'--prepared-seal','a'*64,'--parent-authorized'])
    def test_missing_seal(self):
        with self.assertRaises(ValueError):r.main(['run','--output',str(self.out),'--parent-authorized'])
    def test_no_retry_existing_directory(self):
        with patch.object(Path,'exists',return_value=True):
            with self.assertRaises(ValueError):r.prepare(self.out)
    def test_foreign_directory(self):
        with self.assertRaises(ValueError):r.manifest(Path('/tmp/foreign'))
    def test_execution_record_drift(self):
        with patch.object(r,'prepare',return_value={'timeout_s':600}):
            with self.assertRaises(ValueError):r.invoke_run(self.out,{'timeout_s':450})
    def test_private_foreground_namespace(self):
        old={k:getattr(r.frozen,k) for k in ('PRE','BUDGET','ELF_SEAL','command','preflight')}
        ns=r.lifecycle_namespace()
        self.assertEqual(ns['BUDGET'],600);self.assertEqual(ns['ELF_SEAL'],r.ELF_SHA)
        self.assertEqual(ns['command'](self.out),r.command(self.out))
        self.assertIs(ns['run'].__globals__,ns)
        for k,v in old.items():self.assertIs(getattr(r.frozen,k),v)
    def test_private_execution_without_module_mutation(self):
        record={'timeout_s':600};calls=[];old=r.frozen.BUDGET
        with patch.object(r,'prepare',return_value=record),patch.object(r,'lifecycle_namespace',
                return_value={'run':lambda out,rec:calls.append((out,rec))}):
            r.invoke_run(self.out,record)
        self.assertEqual(calls,[(self.out,record)]);self.assertEqual(r.frozen.BUDGET,old)
    def test_actual_sealed_fixture_and_primary(self):
        pre,pins,counts=r.verify_preflight()
        self.assertEqual(len(pre['targets']),4)
        self.assertTrue(all(t['before'] is False and t['point']['raw_index']==665 and
                            t['point']['vector']=='010' for t in pre['targets']))
        self.assertEqual(pins[str(r.ELF)],r.ELF_SHA)
        self.assertEqual(counts['matched_instructions'],96979)
        self.assertTrue(pre['tail_policy']['agnostic_tail_not_exported_or_read_by_C'])
    def test_actual_budget_context(self):
        rows,pins=r.budget_evidence()
        self.assertEqual(len(rows),2);self.assertEqual(len(pins),4)
        self.assertLess(max(row['linear_context_estimate_s'] for row in rows)*1.15,r.BUDGET)
    def test_terminal_prefix_not_spin_count(self):
        def c(mem):return SimpleNamespace(memory_accesses=mem,gpr_writes={},vector_writes={})
        counts=r.reference_counts([c(()),c(((42,1),)),c(()),c(())],42)
        self.assertEqual(counts['matched_instructions'],2);self.assertEqual(counts['post_terminal_records'],2)
    def test_duplicate_terminal_rejected(self):
        c=SimpleNamespace(memory_accesses=((42,1),),gpr_writes={},vector_writes={})
        with self.assertRaises(ValueError):r.reference_counts([c,c],42)
    def test_wrong_terminal_rejected(self):
        c=SimpleNamespace(memory_accesses=((42,3),),gpr_writes={},vector_writes={})
        with self.assertRaises(ValueError):r.reference_counts([c],42)

if __name__=='__main__':unittest.main()
