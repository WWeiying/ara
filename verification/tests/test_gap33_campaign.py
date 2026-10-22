import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1] / 'coverage'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('gap33', HERE / 'run_gap33_20261001.py')
gap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gap)


class Gap33Tests(unittest.TestCase):
    def row(self, name='case', digest='new'):
        return dict(name=name, elf_sha256=digest, vdb='/tmp/' + name + '.vdb',
                    status='PASS', passed_only=True, vdb_valid=True,
                    coverage_test=name, vdb_files={'metric': 'hash'})

    def test_matrix_and_source_parameters(self):
        self.assertEqual(len(gap.NAMES), 17)
        self.assertEqual(len(set(gap.NAMES)), 17)
        for sew in (8, 16, 32, 64):
            for lmul in (1, 2, 4, 8):
                stem = f'vcoverage_gap33_e{sew}_m{lmul}'
                source = gap.full.ROOT / 'apps/riscv-tests/isa/rv64uv' / (stem + '.c')
                self.assertIn(f'#define G_SEW {sew}', source.read_text())
                self.assertIn(f'#define G_LMUL m{lmul}', source.read_text())

    @patch.object(gap.full.batch, 'valid_vdb', return_value={'metric': 'hash'})
    def test_verified_result_admitted(self, valid):
        row = self.row()
        self.assertEqual(gap.admitted([row], 'image', {'old'}), [row])

    def test_failed_result_rejected(self):
        row = self.row(); row['status'] = 'FAIL'
        with self.assertRaisesRegex(ValueError, 'unverified'):
            gap.admitted([row], 'image')

    @patch.object(gap.full.batch, 'valid_vdb', return_value={'metric': 'hash'})
    def test_duplicate_vdb_rejected(self, valid):
        with self.assertRaisesRegex(ValueError, 'duplicate result'):
            gap.admitted([self.row(), self.row()], 'image')

    @patch.object(gap.full.batch, 'valid_vdb', return_value={'metric': 'hash'})
    def test_duplicate_old_elf_rejected(self, valid):
        with self.assertRaisesRegex(ValueError, 'duplicate new ELF'):
            gap.admitted([self.row(digest='old')], 'image', {'old'})

    @patch.object(gap.full.batch, 'valid_vdb', return_value={'metric': 'different'})
    def test_changed_database_rejected(self, valid):
        with self.assertRaisesRegex(ValueError, 'VDB drift'):
            gap.admitted([self.row()], 'image')


if __name__ == '__main__':
    unittest.main()
