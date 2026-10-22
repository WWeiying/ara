import json
from pathlib import Path
import unittest

import inventory_ptw_pmp0_candidates as candidate


class PMPZeroProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = candidate.ROOT
        names = ['hardware/src/ara_soc.sv', 'hardware/deps/cva6/core/include/build_config_pkg.sv',
                 'hardware/deps/cva6/core/pmp/src/pmp.sv',
                 'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv']
        cls.sources = [(root / n).read_text() for n in names]

    def test_actual_configuration_chain(self):
        proof = candidate.source_proof(*self.sources)
        self.assertEqual(proof['pmp_entries'], 0)
        self.assertEqual(proof['allow_access'], 1)
        self.assertIn('ordinary page-table faults', proof['retained'])

    def test_positive_pmp_config_rejected(self):
        sources = list(self.sources)
        sources[0] = sources[0].replace('cfg.NrPMPEntries          = 0;', 'cfg.NrPMPEntries = 8;')
        with self.assertRaises(ValueError):
            candidate.source_proof(*sources)

    def test_changed_allow_or_extra_state_entry_rejected(self):
        for index, replacement in ((2, self.sources[2].replace("end else assign allow_o = 1'b1;",
                                                               "end else assign allow_o = 1'b0;")),
                                   (3, self.sources[3] + '\nassign state_d = PROPAGATE_ACCESS_ERROR;')):
            sources = list(self.sources)
            sources[index] = replacement
            with self.assertRaises(ValueError):
                candidate.source_proof(*sources)


if __name__ == '__main__':
    unittest.main()
