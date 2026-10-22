import unittest
import preflight_akv_tile_range_capture as case


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.sym={name:0x80010000+i*0x10000 for i,name in enumerate(case.NAMES)}
        self.mem={self.sym[name]+i:b for name,data in case.expected(self.sym).items() for i,b in enumerate(data)}

    def test_complete(self):
        case.validate_memory(self.mem,self.sym)

    def test_corrupt_each_region(self):
        for name,data in case.expected(self.sym).items():
            with self.subTest(name=name):
                mem=dict(self.mem); mem[self.sym[name]+len(data)-1]^=1
                with self.assertRaises(ValueError): case.validate_memory(mem,self.sym)

    def test_missing_full_readback(self):
        del self.mem[self.sym['entropy_snapshots']+4095]
        with self.assertRaises(ValueError): case.validate_memory(self.mem,self.sym)

    def test_truncated_index(self):
        for i in range(4,8): self.mem[self.sym['tile_observed_indices']+i]=0
        with self.assertRaises(ValueError): case.validate_memory(self.mem,self.sym)

    def test_wrong_trap_count(self):
        self.mem[self.sym['entropy_trap_count']]=2
        with self.assertRaises(ValueError): case.validate_memory(self.mem,self.sym)


if __name__=='__main__': unittest.main()
