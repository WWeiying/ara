import unittest

from rms_norm_completion import completed_caller,BEFORE,AFTER


class RMSNormCompletionTests(unittest.TestCase):
    def test_only_completion_order_and_scope_change(self):
        original='prefix timing=complete_call\n'+BEFORE+'suffix'
        changed=completed_caller(original)
        self.assertIn(AFTER,changed)
        self.assertEqual(changed.replace(AFTER,BEFORE).replace('timing=call_and_csr_completion','timing=complete_call'),original)
        self.assertLess(changed.index('vc=vcsr()'),changed.index('elapsed=cycle()'))

    def test_drift_or_duplicate_anchor_rejects(self):
        for text in ('timing=complete_call',BEFORE,BEFORE+BEFORE+'timing=complete_call'):
            with self.assertRaises(ValueError):completed_caller(text)


if __name__=='__main__':unittest.main()
