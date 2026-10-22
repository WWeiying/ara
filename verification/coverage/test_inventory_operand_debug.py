import unittest
from inventory_operand_debug import contained


class RegionTests(unittest.TestCase):
    def test_inside_line(self):
        self.assertTrue(contained(dict(line='678', statements=[dict(line_num='678')]), 'line'))

    def test_functional_statement_prevents_whole_block_exclusion(self):
        self.assertFalse(contained(dict(line='678', statements=[dict(line_num='678'),
                                   dict(line_num='535')]), 'line'))

    def test_functional_header_prevents_exclusion(self):
        self.assertFalse(contained(dict(line='535', statements=[dict(line_num='678')]), 'line'))

    def test_branch_outside_rejected(self):
        self.assertFalse(contained(dict(line='600', expressions=[dict(id='600')]), 'branch'))

    def test_inside_branch(self):
        self.assertTrue(contained(dict(line='1102', expressions=[dict(id='1102')]), 'branch'))

    def test_mixed_branch_rejected(self):
        self.assertFalse(contained(dict(line='1102', expressions=[dict(id='1102'),
                                   dict(id='518')]), 'branch'))


if __name__ == '__main__':
    unittest.main()
