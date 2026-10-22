import unittest
from types import SimpleNamespace
import check_operand_mask_data_preflight as oracle


def commits():
    rows = []
    for phase in range(4):
        add, mask, gather = oracle.expected(phase)
        for op, data in zip(oracle.OPS, (add, mask, gather)):
            writes = {1:data} if isinstance(data, int) else {
                24+r:int.from_bytes(data[128*r:128*(r+1)], 'little') for r in range(8)}
            rows.append(SimpleNamespace(instruction=op, vector_writes=writes))
    return rows


class OracleTest(unittest.TestCase):
    def test_all_four_phases(self):
        self.assertEqual(oracle.validate(commits()), 8256)

    def test_result_mutation(self):
        rows = commits(); rows[0].vector_writes[27] ^= 1 << 513
        with self.assertRaises(AssertionError): oracle.validate(rows)

    def test_mask_mutation(self):
        rows = commits(); rows[7].vector_writes[1] ^= 1 << 97
        with self.assertRaises(AssertionError): oracle.validate(rows)

    def test_oob_gather_mutation(self):
        rows = commits(); rows[11].vector_writes[31] = 1
        with self.assertRaises(AssertionError): oracle.validate(rows)

    def test_missing_target(self):
        with self.assertRaises(AssertionError): oracle.validate(commits()[:-1])

    def test_phase_reorder(self):
        rows = commits(); rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaises(AssertionError): oracle.validate(rows)


if __name__=='__main__': unittest.main()
