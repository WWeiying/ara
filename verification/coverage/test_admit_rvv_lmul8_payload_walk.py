import unittest
import admit_rvv_lmul8_payload_walk as p

class Gates(unittest.TestCase):
    def test_empty_population_rejected(self):
        with self.assertRaises(ValueError):p.union(dict(tests=[]),dict(tests=[]))
    def test_duplicate_new_test_rejected(self):
        with self.assertRaises(ValueError):
            p.union(dict(tests=[str(p.RUN/'code.vdb')]*743),dict(tests=[str(p.RUN/'code.vdb')]))
    def test_partial_universe_rejected(self):
        with self.assertRaises(ValueError):
            p.union(dict(tests=[str(i) for i in range(743)],metrics={}),
                    dict(tests=[str(p.RUN/'code.vdb')],metrics={}))

if __name__=='__main__':unittest.main()
