import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'vcu118'))
spec = importlib.util.spec_from_file_location('stage_dual_reset', HERE / 'stage_dual_reset.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StageTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source'
        source.mkdir()
        files = {module.WRAPPER: b'  logic ui_resetn;\n    .rst_no(ui_resetn), .init_no()\n  );\nif (Channel == 0) begin : gen_ethernet\n',
                 'constraints/cdc.xdc': b'old constraint',
                 'rtl/keep.sv': b'unchanged'}
        for name in ('dual_inval_clock_fix', 'dual_ethernet', 'mmu_ppn_fix'):
            files['provenance/' + name + '.json'] = b'{}'
        for name, data in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (source / 'SHA256SUMS').write_text(''.join(
            f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in files.items()))
        cdc = root / 'new_cdc.xdc'
        cdc.write_bytes(b'new constraint')
        return source, cdc

    def test_only_intended_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cdc = self.fixture(root)
            target = root / 'output/package'
            module.stage(source, target, cdc)
            self.assertEqual((target / 'rtl/keep.sv').read_bytes(), b'unchanged')
            self.assertNotIn('ui_resetn_sync', (source / module.WRAPPER).read_text())
            self.assertIn('ui_resetn_sync', (target / module.WRAPPER).read_text())
            for row in (target / 'SHA256SUMS').read_text().splitlines():
                digest, name = row.split('  ', 1)
                self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), digest)
            with self.assertRaises(ValueError):
                module.stage(source, target, cdc)
            with self.assertRaises(RuntimeError):
                module.stage(target, root / 'double/package', cdc)

    def test_corrupted_source_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cdc = self.fixture(root)
            (source / 'rtl/keep.sv').write_text('changed')
            target = root / 'target'
            with self.assertRaises(ValueError):
                module.stage(source, target, cdc)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
