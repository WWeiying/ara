import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import audit_qbs_canonical_repair as a


OLD = a.ROOT / 'verification/out/gap71-canonical-qbs-positive779-run-agent-20261008-03'


def good_log():
    return ('Core Test *** SUCCESS ***\n'
            'GAP71 gap71_qbs_fault backend=custom-dut snapshots=2 '
            'digest=e25c1b20694aefa5 traps=2\n'
            'PASSED: gap71_qbs_fault checks=160 errors=0\n'
            '[QBS_PERF] success=0 fault=1 validation_fault=0 read_fault=2 '
            'translations=2 commit_groups=0\n'
            '[QBS_PERF] success=1 fault=0 validation_fault=0 read_fault=0 '
            'translations=3 read_ranges=3 payload_bytes=452\n'
            'UVM_ERROR : 0\nUVM_FATAL : 0\n')


class RepairAuditTests(unittest.TestCase):
    def test_original_elf_and_reference_contract(self):
        info, pins = a.fixture_contract(a.ORIGINAL_ELF)
        self.assertFalse(info['software_reference'])
        self.assertEqual(info['words']['gap71_site'], 0x00b5045b)
        self.assertIn(str(a.FIXTURE / 'reference.elf'), pins)
        self.assertFalse(any('simv' in key or '/hardware/' in key
                             or 'admission' in key for key in pins))

    def test_altered_elf_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            elf = Path(temp) / 'input.elf'
            blob = bytearray(a.ORIGINAL_ELF.read_bytes())
            blob[-1] ^= 1
            elf.write_bytes(blob)
            with self.assertRaisesRegex(ValueError, 'hash changed'):
                a.fixture_contract(elf)

    def test_software_fallback_elf_rejected(self):
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            a.fixture_contract(a.FIXTURE / 'reference.elf')

    def test_160_checks_and_perf_gates(self):
        uart, perf = a.log_gate(good_log())
        self.assertEqual(uart['checks'], 160)
        self.assertEqual(perf['commands'], 2)
        self.assertEqual(perf['mmu_faults'], 1)

    def test_missing_or_bad_checks_rejected(self):
        mutations = [('checks=160', 'checks=144'), ('errors=0', 'errors=1'),
                     ('digest=e25c1b20694aefa5', 'digest=0000000000000000'),
                     ('traps=2', 'traps=1'), ('commit_groups=0', 'commit_groups=1'),
                     ('payload_bytes=452', 'payload_bytes=448'),
                     ('translations=2', 'translations=0'),
                     ('Core Test *** SUCCESS ***', 'Core Test *** FAILED ***')]
        for before, after in mutations:
            with self.subTest(after=after), self.assertRaises(ValueError):
                a.log_gate(good_log().replace(before, after))

    def test_uvm_and_assertion_errors_rejected(self):
        for error in ('UVM_ERROR : 1', 'UVM_FATAL bad',
                      'Error: assertion failed', 'Error-[ASRT] failed',
                      'Fatal: failed', 'UVM_ERROR : 0 extra'):
            with self.subTest(error=error), self.assertRaises(ValueError):
                a.log_gate(good_log() + error + '\n')

    def test_original_failed_capture_rejected_without_converter(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            shutil.copyfile(a.ORIGINAL_ELF, run / 'input.elf')
            for name in ('run.vcs.log', 'console.log', 'commit_trace.csv',
                         'vector_trace.csv', 'qbs-canonical-focused.vpd'):
                (run / name).symlink_to(OLD / name)
            with patch.object(a.subprocess, 'run') as convert:
                with self.assertRaisesRegex(ValueError, 'Simulator/self-check failure'):
                    a.audit(run)
                convert.assert_not_called()
            self.assertFalse((run / 'qbs-canonical-audit').exists())

    def test_new_image_argv_and_original_probe(self):
        command = a.simulation_command('/new/build/simv', '/new/run')
        self.assertEqual(command[0], '/new/build/simv')
        for arg in ('+PRELOAD=/new/run/input.elf', '+ARA_DEBUG_EEW',
                    '+QBS_PERF', '+COMMIT_TOHOST=80001000'):
            self.assertIn(arg, command)
        self.assertEqual(command[-2:], ['-do', str(a.PROBE)])
        self.assertFalse(any('repaired-aligned-build' in arg for arg in command))

    def fixture(self, run):
        (run / 'input.elf').write_bytes(a.ORIGINAL_ELF.read_bytes())
        for name in ('run.vcs.log', 'console.log'):
            (run / name).write_text(good_log())
        for name in ('commit_trace.csv', 'vector_trace.csv', 'qbs-canonical-focused.vpd'):
            (run / name).write_text('mock-only\n')

    def test_orchestration_all_strict_gates_required(self):
        # Mock orchestration only, never an RTL PASS. Original checker tests
        # separately exercise numerical, owner, recovery and cycle mutations.
        architecture = dict(owner=dict(full_scalar_compared_words=4688),
                            last_cycle=1234, recovery=dict(status='MOCK_ONLY'))
        for failure in (None, 'markers', 'native_architecture', 'cycle_wave'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                run = Path(temp)
                self.fixture(run)

                def convert(command, **kwargs):
                    Path(command[-1]).write_text('mock-vcd\n')

                with patch.object(a.strict, 'markers') as markers, \
                        patch.object(a.strict, 'native_architecture',
                                     return_value=copy.deepcopy(architecture)) as native, \
                        patch.object(a.strict, 'cycle_wave',
                                     return_value={'status': 'MOCK_ONLY'}) as cycles, \
                        patch.object(a.subprocess, 'run', side_effect=convert):
                    gates = dict(markers=markers, native_architecture=native, cycle_wave=cycles)
                    if failure:
                        gates[failure].side_effect = ValueError('injected ' + failure)
                        with self.assertRaisesRegex(ValueError, 'injected ' + failure):
                            a.audit(run)
                        self.assertFalse((run / 'qbs-canonical-audit/receipt.json').exists())
                    else:
                        result = a.audit(run)
                        self.assertEqual(result['stdout']['checks'], 160)
                        self.assertFalse(result['coverage_admitted'])
                        self.assertFalse(result['image_provenance_verified'])
                        self.assertFalse(result['simulator_process_exit_verified'])
                        for gate in gates.values():
                            gate.assert_called_once()
                        self.assertEqual(cycles.call_args.args[1], 1234)
                        receipt = json.loads((run / 'qbs-canonical-audit/receipt.json').read_text())
                        self.assertEqual(receipt, result)


if __name__ == '__main__':
    unittest.main()
