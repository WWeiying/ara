import unittest
from run_shared_fma_soc import parse


def log(shared=1):
    return ('Core Test *** SUCCESS ***\nPASSED: /tests/vfadd.c!\n'
            + '\n'.join(f'FMA_SOC_SUMMARY lane{i} shared={shared} cycles=100 issued=10 retired=10 '
                         'blocked=0 latency_wait=0 fma=0,3,3,4' for i in range(4))
            + '\n$finish at simulation time 1000\n')


class Collector(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse(log(),'rv64uv-ara-vfadd',1)['finish_time'],1000)

    def test_rejects_errors(self):
        for text in (log()+'\nError: wrong answer',log().replace('SUCCESS','FAILED'),
                     log().replace('vfadd.c','vfmul.c'),log().replace('retired=10','retired=9'),
                     log().replace('lane3','lane2'),log().replace('shared=1','shared=0'),
                     log().replace('issued=10 retired=10','issued=0 retired=0'),
                     log().replace('$finish at simulation time 1000','')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text,'rv64uv-ara-vfadd',1)


if __name__=='__main__': unittest.main()
