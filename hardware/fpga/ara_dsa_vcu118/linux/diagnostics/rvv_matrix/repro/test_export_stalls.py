import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from export_stalls import export
from trace_masks import sha


class ExportStallTests(unittest.TestCase):
    def test_reaudit_gate_and_complete_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); roots = [base / 'trace', base / 'single']
            proof_dir = base / 'proof'; proof_dir.mkdir()
            proof = dict(confirmed=True, cases=[dict(trigger='measured', opcode=('code', 'asm'))])
            for file in ('original_report.json', 'trace_report.json', 'single_report.json'):
                (proof_dir / file).write_text('{}')
            (proof_dir / 'symptoms.json').write_text(json.dumps(proof))
            for root in roots:
                (root / 'case').mkdir(parents=True)
                (root / 'case' / 'source.c').write_text('source')
                (root / 'case' / 'original_rebuilt.elf').write_bytes(b'original')
                binary = root / 'overlay/opt/ara-tests'; binary.mkdir(parents=True)
                (binary / 'case').write_bytes(b'candidate')
                (root / 'manifest.json').write_text(json.dumps(dict(cases=[dict(
                    name='case', original_name='parent', scenario_sources={'source.c': 'hash'})])))
            with patch('export_stalls.audit_move', return_value=proof) as check:
                out = base / 'out'
                result = export('fp_move', *roots, proof_dir, 'cross-', out)
                check.assert_called_once()
                self.assertFalse(result['complete_historical_coverage'])
                hashes = json.loads((out / 'hashes.json').read_text())
                for file, digest in hashes.items():
                    self.assertEqual(sha(out / file), digest)
                self.assertIn('single/source.c', hashes)
                (proof_dir / 'symptoms.json').write_text('{}')
                with self.assertRaises(ValueError):
                    export('fp_move', *roots, proof_dir, 'cross-', base / 'bad')
                self.assertFalse((base / 'bad').exists())


if __name__ == '__main__':
    unittest.main()
