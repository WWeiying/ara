import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pair_final_acceptance', Path(__file__).with_name('acceptance.py'))
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


class TestAcceptance(unittest.TestCase):
    def fixture(self, root):
        directory = root/'run'
        work = directory/'work'
        work.mkdir(parents=True)
        for name in ('run.vcs.log', 'vector_trace.csv'):
            (work/name).write_text(name)
        inputfile = directory/'input'
        inputfile.write_text('sealed')
        (directory/'source-pins.json').write_text(json.dumps({str(inputfile): acceptance.sha(inputfile)}))
        measured = dict(state='PASS', measured_total_cycles=[1000, 700, 710, 1010])
        vector = dict(native_commands=2566)
        proof = dict(status='PASS', issues=[], elf_sha256='elf',
            log_sha256=acceptance.sha(work/'run.vcs.log'), vector_trace_sha256=acceptance.sha(work/'vector_trace.csv'))
        (work/'uvm_result.json').write_text(json.dumps(proof))
        builddir = directory/'build'
        builddir.mkdir()
        (builddir/'build.json').write_text(json.dumps(dict(sdk_head=acceptance.SDK)))
        report = dict(state='PASS', post_pins_match=True, independent_protocol_checked=True,
            source_pins_sha256=acceptance.sha(directory/'source-pins.json'),
            artifacts={str(p): acceptance.sha(p) for p in work.iterdir()}, kind='qwen3_abba',
            performance_measured=True, hardware_changed=False, whole_model=False, build=str(builddir),
            measured=measured, vector_command_work=vector, software_sha256='elf')
        (directory/'result.json').write_text(json.dumps(report))
        fresh, vectors = copy.deepcopy(measured), copy.deepcopy(vector)
        checker = SimpleNamespace(check_run=lambda *_: copy.deepcopy(fresh),
                                  check_vector_workcounts=lambda *_: copy.deepcopy(vectors))
        return directory, report, checker

    def test_inventory_rejects_drift_and_incomplete_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory, report, _ = self.fixture(Path(tmp))
            self.assertEqual(acceptance.inventory(directory), report)
            for key, value in [('state', 'TIMEOUT'), ('independent_protocol_checked', False),
                               ('post_pins_match', False)]:
                bad = copy.deepcopy(report)
                bad[key] = value
                (directory/'result.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    acceptance.inventory(directory)
            (directory/'result.json').write_text(json.dumps(report))
            (directory/'work/run.vcs.log').write_text('different')
            with self.assertRaises(ValueError):
                acceptance.inventory(directory)

    def test_current_run_recomputes_values_and_binds_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, report, checker = self.fixture(root)
            with patch.object(acceptance, 'OUT', root), \
                 patch.object(acceptance.owner, 'checked_software', return_value=({}, {})), \
                 patch.object(acceptance, 'load', return_value=checker):
                self.assertEqual(acceptance.current_run('run', 'integration', 'qwen3_abba'), report)
                bad = copy.deepcopy(report)
                bad['measured']['measured_total_cycles'][1] = 1
                (directory/'result.json').write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError, 'Raw numerical/work'):
                    acceptance.current_run('run', 'integration', 'qwen3_abba')
                (directory/'result.json').write_text(json.dumps(report))
                (directory/'build/build.json').write_text(json.dumps(dict(sdk_head='old')))
                with self.assertRaisesRegex(ValueError, 'integrated SDK'):
                    acceptance.current_run('run', 'integration', 'qwen3_abba')


if __name__ == '__main__':
    unittest.main()
