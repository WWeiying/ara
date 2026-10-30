import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('reader_handoff_worker',HERE/'run.py')
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class ReaderRunTest(unittest.TestCase):
    def test_exporter_inventory_includes_wrapper_and_platform_elf(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            (home/'bin').mkdir()
            wrapper=home/'bin/.wrapper'
            wrapper.write_bytes(b'#!/bin/sh\n')
            entry=home/'bin/fsdbreport'
            entry.symlink_to('.wrapper')
            backend=home/'platform/LINUX64/bin/fsdbreport'
            backend.parent.mkdir(parents=True)
            backend.write_bytes(b'\x7fELFfixture')
            self.assertEqual(set(r.exporter_files(entry)),{entry,wrapper,backend})
            pinned=r.s.hashes(r.exporter_files(entry))
            backend.write_bytes(b'\x7fELFchanged')
            self.assertNotEqual(r.s.hashes(r.exporter_files(entry)),pinned)
            with self.assertRaises(ValueError):
                r.exporter_files(wrapper)

    def test_rejects_unbuilt_or_wrong_fault_fixture(self):
        for data in ({},{'state':'PASS'},{'state':'READER_HANDOFF_BUILT_NOT_EXECUTED','expected_traps':0}):
            with patch.object(r.s,'read_json',return_value=data),self.assertRaises(ValueError):
                r.checked_build(Path('/synthetic/build'))

    def test_no_simulator_without_bounded_argument(self):
        from argparse import Namespace
        for timeout in (0,901,-1):
            args=Namespace(timeout=timeout)
            with self.assertRaises(ValueError):
                r.run(args)

    def test_worker_requires_wave_and_independent_protocol_before_pass(self):
        source=(HERE/'run.py').read_text()
        for required in ('check_log(log.read_text()',"check_cycles(out/'cycles/cycles.csv')",
                         "'--require-axi-write'", "manifest('manifest-after')", 'identity()',
                         "'+AKV_PERF'", "'+QBS_PERF'", "'RUNNING'", "'EXTRACTING'"):
            self.assertIn(required,source)
        self.assertLess(source.index('waves=check_cycles('),source.index("parsed.update(state='PASS'"))
        self.assertLess(source.index('s.check_result('),source.index("parsed.update(state='PASS'"))
        self.assertNotIn("'+NO_FSDB', '+FSDB'",source)


if __name__=='__main__':
    unittest.main()
