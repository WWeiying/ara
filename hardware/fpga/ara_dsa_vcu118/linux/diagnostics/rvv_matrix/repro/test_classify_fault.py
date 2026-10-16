import unittest
from classify_fault import classify


BEGIN = 'RVV_FAULT_BEGIN unmapped=0 store=0 boundary=1 mode=3 split=0'
CONTEXT = ('RVV_FAULT_CONTEXT sig=11 code=2 address=4096 expected_address=4103 '
           'pc=100 expected_pc=100 vstart=1 expected_start=8 vl=8 vtype=5')
RETURN = 'RVV_FAULT_RETURN status=0 faults=1 expected_faults=0 handler_errors=1'
CHECK = 'RVV_FAULT_CHECK errors=2'


class FaultTraceTests(unittest.TestCase):
    def test_unexpected_fault_and_context(self):
        result = classify('\n'.join((BEGIN, CONTEXT, RETURN, CHECK)))
        trial, = result['trials']
        self.assertEqual(result['completed'], 1)
        self.assertTrue(trial['unexpected_fault'])
        self.assertEqual(trial['context_mismatches'][0]['vstart'], dict(actual=1, expected=8))
        self.assertNotIn('pc', trial['context_mismatches'][0])
        self.assertFalse(result['original_failure_equivalence_proven'])

    def test_incomplete_is_not_completed(self):
        result = classify(BEGIN + '\n' + CONTEXT)
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['incomplete'], 1)

    def test_no_fault_case(self):
        returned = RETURN.replace('faults=1', 'faults=0').replace('handler_errors=1', 'handler_errors=0')
        result = classify('\n'.join((BEGIN, returned, CHECK.replace('errors=2', 'errors=0'))))
        self.assertFalse(result['trials'][0]['fault_count_mismatch'])

    def test_malformed_order_rejected(self):
        for lines in ((RETURN,), (BEGIN, BEGIN), (BEGIN, CHECK), (BEGIN, RETURN, CONTEXT),
                      (BEGIN, RETURN, RETURN), (BEGIN + ' mode=3',)):
            with self.assertRaises(ValueError):
                classify('\n'.join(lines))


if __name__ == '__main__':
    unittest.main()
