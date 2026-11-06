import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audit import digest
import run_supply_sdk as runner


class SupplyRunTests(unittest.TestCase):
    def test_binding_rejects_drift_and_wrong_expected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input'; path.write_bytes(b'a'); pins = {}
            runner.bind(pins, path, digest(path))
            path.write_bytes(b'b')
            with self.assertRaises(ValueError): runner.bind(pins, path)
            with self.assertRaises(ValueError): runner.bind({}, path, '0'*64)

    def test_incomplete_gate_does_not_admit_sdk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'result.json').write_text(json.dumps(dict(state='WAITING_MEMORY_RESULT_EVENTS')))
            with patch.object(runner, 'GATE', root), self.assertRaises(ValueError):
                runner.acceptance_gate({})

    def test_partial_publication_does_not_poison_retry_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / 'result.json'; path.write_text('{')
            pins = {}
            with patch.object(runner, 'GATE', root), self.assertRaises(json.JSONDecodeError):
                runner.acceptance_gate(pins)
            self.assertEqual(pins, {})
            path.write_text(json.dumps(dict(state='PASS')))
            def checked(candidate):
                runner.bind(candidate, path)
                self.assertEqual(json.loads(path.read_text())['state'], 'PASS')
                return digest(path)
            with patch.object(runner, '_acceptance_gate', side_effect=checked):
                self.assertEqual(runner.acceptance_gate(pins), digest(path))
            self.assertEqual(pins, {str(path.resolve()): digest(path)})

    def test_invalid_workload_cannot_select_other_hardware(self):
        for kind, width in (('prefill', 512), ('unknown', 128), ('decode', 64)):
            with self.assertRaises(ValueError): runner.inputs(kind, width)


if __name__ == '__main__': unittest.main()
