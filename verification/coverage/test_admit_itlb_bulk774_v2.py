from pathlib import Path
import unittest
from unittest.mock import patch
import admit_itlb_bulk774_v2 as a


class HistoricalAuthority(unittest.TestCase):
    def fixture(self):
        ledger=['/design']+[str(i) for i in range(773)]
        pins={'/historical/receipt.json':'sealed'}
        result=dict(ledger_members=773,duplicate=False,pins=dict(pins),
                    members=[dict(vdb=p) for p in ledger[1:]])
        return ledger,pins,result

    def test_candidate_metadata_excluded_not_duplicate_bypassed(self):
        ledger,pins,result=self.fixture()
        polluted=dict(pins,**{'/candidate/qualification.json':'new'})
        with patch.object(a.old.core,'baseline',return_value=({},ledger,pins)),\
             patch.object(a.old,'dedup',return_value=result) as dedup:
            self.assertEqual(a.historical_dedup(ledger,'candidate',polluted),result)
            dedup.assert_called_once_with(ledger,'candidate',pins)

    def test_prefix_and_authority_conflict_rejected_before_scan(self):
        ledger,pins,_=self.fixture()
        with patch.object(a.old.core,'baseline',return_value=({},ledger,pins)),\
             patch.object(a.old,'dedup',side_effect=AssertionError('must not scan')):
            for wrong_ledger,evidence in ((ledger[:-1],pins),(ledger,{}),
                                          (ledger,{'/historical/receipt.json':'changed'})):
                with self.assertRaises(ValueError):a.historical_dedup(wrong_ledger,'candidate',evidence)

    def test_true_duplicate_failure_propagates(self):
        ledger,pins,_=self.fixture()
        with patch.object(a.old.core,'baseline',return_value=({},ledger,pins)),\
             patch.object(a.old,'dedup',side_effect=ValueError('Duplicate historical ELF')):
            with self.assertRaisesRegex(ValueError,'Duplicate historical ELF'):
                a.historical_dedup(ledger,'same',pins)

    def test_foreign_unbound_resolved_elf_rejected(self):
        ledger,pins,result=self.fixture();result['pins']['/foreign.elf']='new'
        with patch.object(a.old.core,'baseline',return_value=({},ledger,pins)),\
             patch.object(a.old,'dedup',return_value=result):
            with self.assertRaisesRegex(ValueError,'formal773 pin'):
                a.historical_dedup(ledger,'candidate',pins)

    def test_missing_member_or_order_changed_rejected(self):
        ledger,pins,result=self.fixture()
        result['members'][0],result['members'][1]=result['members'][1],result['members'][0]
        with patch.object(a.old.core,'baseline',return_value=({},ledger,pins)),\
             patch.object(a.old,'dedup',return_value=result):
            with self.assertRaises(ValueError):a.historical_dedup(ledger,'candidate',pins)

    def test_actual_773_baseline_has_no_candidate_vdb_or_elf(self):
        _,ledger,pins=a.old.core.baseline()
        candidate=a.life.OUT/'itlb-asid-exec-bulk-preflight-agent-20261007-01/input.elf'
        self.assertNotIn(str(a.old.RUN/'code.vdb'),ledger)
        result=a.historical_dedup(ledger,a.life.digest(candidate),pins)
        self.assertEqual(result['ledger_members'],773)
        self.assertTrue(all(str(candidate) not in row['ELF_candidates'] for row in result['members']))

    def test_actual_complete_evaluate_does_not_write_admission(self):
        with patch.object(a.life,'save',side_effect=AssertionError('evaluate must not write')):
            products,ledger=a.evaluate()
        self.assertEqual(len(ledger.splitlines()),775)
        self.assertEqual(products['status.json']['aggregate_passed'],774)
        self.assertEqual(products['status.json']['target_new_serialized_positions'],862)
        self.assertEqual(products['status.json']['scoped_toggle_new_serialized_positions'],948)
        self.assertFalse(products['status.json']['official_percentage_claimed'])
        self.assertEqual(len(products['combined-bits.json']['tests']),774)
        self.assertEqual(products['status.json']['raw_delta'],dict(line=0,cond=0,branch=0,fsm=0))


if __name__=='__main__':unittest.main()
