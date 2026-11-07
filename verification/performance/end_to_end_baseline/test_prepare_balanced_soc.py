from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import prepare_balanced_soc as b


class BalancedSoc(unittest.TestCase):
    def test_exact_graph_inverse_and_fixed_platform(self):
        old = b.PREPARED / 'source'
        original = (b.PREPARED / 'sources256.f').read_text()
        for mode in (0, 1):
            new = Path('/new-sealed-inputs/source')
            text = b.graph(original, old, new, mode)
            self.assertTrue(text.startswith('+define+' + b.EXPERIMENT_DEFINE + '=' + str(mode) + '\n'))
            self.assertNotIn(str(old), text)
            for name in (*b.CLONES, 'qbs_engine_balanced.sv'):
                self.assertEqual(text.splitlines().count(str(new / b.ADDITION_REL / name)), 1)
            restored = [line.replace(str(new) + '/', str(old) + '/') for line in text.splitlines()[1:]
                        if b.ADDITION_REL not in line]
            self.assertEqual(restored, original.splitlines())
            for flag in ('NR_LANES=4', 'VLEN=1024', 'SIM_L2_SIZE_BYTES=16777216'):
                self.assertEqual(text.count('+define+' + flag), original.count('+define+' + flag))

    def test_graph_rejects_width_module_feature_and_external_drift(self):
        original = (b.PREPARED / 'sources256.f').read_text()
        old = b.PREPARED / 'source'
        for text in (original.replace('AXI_DATA_WIDTH=256', 'AXI_DATA_WIDTH=128'),
                     original.replace(str(old / b.VLSU_REL), '/foreign/vlsu.sv'),
                     original + '\n' + str(old / b.VLSU_REL),
                     original + '\n+define+' + b.EXPERIMENT_DEFINE + '=1',
                     original + '\n/foreign/source.sv'):
            with self.assertRaises(ValueError):
                b.graph(text, old, Path('/new'), 1)
        for mode in (True, 2, -1):
            with self.assertRaises(ValueError):
                b.graph(original, old, Path('/new'), mode)

    def test_diagnostics_require_exact_inventory_and_actual_command(self):
        old, new = Path('/old'), Path('/new')
        warning = 'Warning-[KNOWN] retained\n/old/a.sv, 2\n\n'
        argv = ['/tool/vcs', '-f', '/new/sources.f']
        text = 'Command: vcs -f /new/sources.f\n' + warning.replace('/old/', '/new/') + 'CPU time: 1 to compile\n'
        self.assertEqual(b.diagnostic_check(text, argv, warning, old, new)['known_diagnostic_count'], 1)
        for bad in (text.replace('KNOWN', 'UNKNOWN'), text + 'Error-[BAD] bad\n',
                    text.replace('CPU time:', 'unfinished:'), text.replace('sources.f', 'other.f'),
                    text.replace('/new/a.sv', '/foreign/a.sv'), text.replace('retained', 'changed')):
            with self.assertRaises(ValueError):
                b.diagnostic_check(bad, argv, warning, old, new)

    def test_unaccepted_gate_does_not_copy_or_start_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'fresh'
            with patch.object(b, 'RUNS', Path(directory)), \
                 patch.object(b, 'receipt', side_effect=ValueError('Unaccepted prerequisite')), \
                 patch.object(b.shutil, 'copyfile') as copy, \
                 patch.object(b.subprocess, 'Popen') as child:
                with self.assertRaisesRegex(ValueError, 'Unaccepted prerequisite'):
                    b.prepare(output, Path(directory), 'bad', Path(directory), 'bad')
                copy.assert_not_called()
                child.assert_not_called()
                self.assertIn('Unaccepted prerequisite', (output / 'result.json').read_text())

    def test_receipt_rejects_stale_hash_failed_state_and_artifact_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.sv'
            source.write_text('module fixture; endmodule\n')
            inventory = root / 'source-pins.json'
            inventory.write_text(json.dumps({str(source): b.digest(source)}))
            artifact = root / 'run.log'
            artifact.write_text('functional reference checked\n')
            path = root / 'result.json'
            value = dict(state=b.STATES['seed'], post_pins_match=True,
                         source_pins_sha256=b.digest(inventory),
                         artifacts={str(artifact): b.digest(artifact)})
            path.write_text(json.dumps(value))
            with patch.object(b, 'RUNS', root):
                self.assertEqual(b.receipt(root, b.digest(path), b.STATES['seed'], {}), value)
                with self.assertRaises(ValueError):
                    b.receipt(root, '0' * 64, b.STATES['seed'], {})
                with self.assertRaises(ValueError):
                    b.receipt(root, b.digest(path), b.STATES['controller'], {})
                artifact.write_text('changed\n')
                with self.assertRaises(ValueError):
                    b.receipt(root, b.digest(path), b.STATES['seed'], {})
                value['post_pins_match'] = False
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    b.receipt(root, b.digest(path), b.STATES['seed'], {})


if __name__ == '__main__':
    unittest.main()
