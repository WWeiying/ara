import unittest
import preflight_c910_float_edge_initialized as p


class InitializedSoftware(unittest.TestCase):
    def test_original_matrix_source_unchanged(self):
        self.assertEqual(p.life.digest(p.old.APP), p.ORIGINAL_APP_SHA)
        text = p.APP.read_text()
        self.assertIn('#include "c910_float_edge.c"', text)
        for base in (8,16,24): self.assertIn('vmv.v.i v'+str(base)+', 0', text)

    def test_gold_48cases_unchanged(self):
        for width in (16,32,64):
            for rm in (0,1):
                for kind in range(8): self.assertEqual(p.gold(width,kind,rm), p.old.gold(width,kind,rm))

    def test_missing_initialization_rejected(self):
        with self.assertRaises(ValueError): p.initialization([], {'edge_initial_config': 0})

    def test_actual_initialization_zero_and_wrong_byte_rejected(self):
        import copy
        directory = p.life.OUT / 'c910-float-edge-initialized-preflight777-agent-20261007-01'
        symbols = {n:p.build._elf_symbol(directory/'input.elf',p.build.LLVM/'llvm-readelf',n) for n in p.SYMBOLS}
        commits = p.build.parse_spike_commits(directory/'spike.trace')
        self.assertEqual(p.initialization(commits,symbols)['bytes'],3072)
        altered = copy.deepcopy(commits)
        init = next(c for c in altered if c.pc==symbols['edge_initial_v8'])
        init.vector_writes[8] = 1
        with self.assertRaises(ValueError): p.initialization(altered,symbols)


if __name__ == '__main__': unittest.main()
