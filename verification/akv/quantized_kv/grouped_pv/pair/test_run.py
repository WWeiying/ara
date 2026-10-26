"""Worker control tests use no tool subprocess or simulated data claims."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('grouped_worker_unit', HERE / 'run.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
fixture = r.local('grouped_worker_fixture', HERE / 'test_check.py').fixture


class WorkerTests(unittest.TestCase):
    def mock_run(self, execute, broken=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'program').mkdir()
            build = root / 'program/build.json'
            build.write_text('{}')
            soc = root / 'soc'
            soc.mkdir()
            elf = root / 'main.elf'
            elf.write_bytes(b'fixture')
            text, golden, rtl = fixture()
            gold = root / 'gold.bin'; gold.write_bytes(golden)
            rtlfile = root / 'vlsu.sv'; rtlfile.write_text(rtl)
            phases = []

            class Execution:
                def __init__(self, output):
                    self.output, self.env, self.state = output, {}, {}

                def save(self):
                    (self.output / 'status.json').write_text(json.dumps(self.state))

                def execute(self, argv, log, timeout, phase):
                    phases.append(phase)
                    log.write_text('fixture only')
                    if phase == 'RUNNING':
                        (log.parent / 'run.vcs.log').write_text(text.replace('errors=0', 'errors=1', 1) if broken else text)
                        (log.parent / 'vector_trace.csv').write_text('fixture')
                    if phase == 'CHECKING':
                        for flag in ('--require-events', '--require-backend', '--require-axi', '--require-axi-write'):
                            assert flag in argv
                        assert '--log' in argv and '--vector-trace' in argv

            args = SimpleNamespace(build=build, build_sha256=r.prep.sha(build), soc_build=soc,
                                   output=root / 'out', timeout=10800, execute_reviewed=execute)
            program = dict(elf=str(elf), elf_sha256=r.prep.sha(elf), golden=str(gold))
            with patch.object(r, 'prepare_inputs', return_value=(program, {'simv': str(soc / 'simv')}, {}, {})), \
                 patch.object(r.original, 'Execution', Execution), \
                 patch.object(r.s, 'image_files', return_value=[]), \
                 patch.object(r.accepted, 'RTL', rtlfile), \
                 patch.object(r.accepted, 'protocol') as protocol:
                if broken:
                    with self.assertRaises(ValueError):
                        r.run(args)
                    self.assertEqual(json.loads((args.output / 'result.json').read_text())['state'], 'FAIL')
                    protocol.assert_not_called()
                else:
                    result = r.run(args)
                    self.assertEqual(result['state'], 'PASS' if execute else 'PREFLIGHT_NOT_RUN')
                    self.assertEqual(result['simulations_launched'], int(execute))
                    self.assertTrue(result['post_pins_match'])
                    if execute:
                        self.assertEqual(len(result['raw_replay']['hardware_records']), 32)
                        protocol.assert_called_once()
                    else:
                        self.assertEqual(phases, [])
            return phases

    def test_preflight_no_subprocess(self):
        self.mock_run(False)

    def test_success_path_closes_receipt(self):
        self.assertEqual(self.mock_run(True), ['MANIFEST_BEFORE', 'IMAGE_CONTRACT', 'RUNNING', 'CHECKING', 'MANIFEST_AFTER'])

    def test_bad_program_stops_before_uvm(self):
        self.assertEqual(self.mock_run(True, True), ['MANIFEST_BEFORE', 'IMAGE_CONTRACT', 'RUNNING'])

    def test_build_sha_fails_before_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'build.json'; path.write_text('{}')
            with patch.object(r.prep, 'checked_build') as checked, self.assertRaises(ValueError):
                r.prepare_inputs(SimpleNamespace(build=path, build_sha256='0'*64))
            checked.assert_not_called()


if __name__ == '__main__':
    unittest.main()
