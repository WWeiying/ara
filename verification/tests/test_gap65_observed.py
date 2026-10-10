"""No EDA: exact observer parser, documented UCLI command mock, sealed admission."""
from contextlib import ExitStack
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import run_gap65_late_fault_observed as a
from ara_verify.model import TestResult


def samples():
    before = dict(clk=0, rst_n=1, cycle=100, state=3, next_state=10, fault=1,
        m=4, n=5, k_blocks=1, row_base=0, integer_busy=1, compute_active=1,
        issue_active=1, commit=0, vrf_req=0)
    after = dict(before, cycle=101, state=10, next_state=10)
    return [before, after]


def transcript(values=None):
    rows = ['\t'.join(['phase', *a.FIELDS])]
    for phase, sample in zip(('before', 'after'), values or samples()):
        rows.append('\t'.join([phase, *("'d" + str(sample[k]) for k in a.FIELDS)]))
    return '\n'.join([*rows, 'END', ''])


class ObserverTests(unittest.TestCase):
    def test_exact_compute_arc_and_numeric_radix(self):
        self.assertEqual(a.observer_samples(transcript()), samples())
        self.assertEqual(a.observer_samples(transcript().replace("'d", '')), samples())

    def test_load_tile_and_other_arcs_not_target(self):
        for state in (0, 2, 4, 5, 9, 10):
            values = samples(); values[0]['state'] = state
            with self.subTest(state=state), self.assertRaises(ValueError):
                a.observer_samples(transcript(values))

    def test_each_command_commit_reset_and_activity_field(self):
        for index in (0, 1):
            for field in a.FIELDS:
                if index == 1 and field in ('integer_busy', 'compute_active', 'issue_active', 'fault', 'next_state'):
                    continue
                values = samples(); values[index][field] ^= 1
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    a.observer_samples(transcript(values))

    def test_missing_extra_duplicate_unknown_trailing_records(self):
        text = transcript()
        for bad in (text.replace('END\n', ''), text + 'END\n', text + '\n',
                    text.replace('after', 'before'), text.replace("'d3\t", "'bx\t"),
                    text.replace("'d3\t", "QBS_COMPUTE_TILE\t"), text.replace('cycle', 'wrong')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                a.observer_samples(bad)

    def test_tcl_84_surface_and_exact_existing_hierarchy(self):
        text = a.OBSERVER.read_text()
        self.assertFalse(re.search(r'\b(dict|lassign|lmap|apply|try|force|deposit|release|exec)\b|\{\*\}', text))
        rtl = (ROOT / 'hardware/src/vlsu/qbs/qbs_compute_engine.sv').read_text()
        self.assertIn('i_profile_engine_int (', rtl)
        self.assertIn('$ce.i_profile_engine_int.compute_active_q', text)
        self.assertIn('$ce.i_profile_engine_int.issue_active_q', text)

    def mock_tcl(self, missing=False, wrong=False):
        shell = shutil.which('tclsh')
        self.assertIsNotNone(shell, 'local Tcl mock is required, never substitute simv')
        with tempfile.TemporaryDirectory(dir=ROOT / 'verification/out', prefix='gap65-mock-') as directory:
            before, after = samples()
            if wrong: before['state'] = 2
            root = a.checks.TARGET_SCOPE.rsplit('.', 1)[0]
            ce = a.checks.TARGET_SCOPE
            signals = ['ara_tb.clk', 'ara_tb.rst_n', 'ara_tb.wall_cycle',
                *(ce + '.' + s for s in ('state_q', 'state_d', 'fault_i', 'm_q', 'n_q', 'k_blocks_q',
                    'row_base_q', 'integer_busy', 'i_profile_engine_int.compute_active_q',
                    'i_profile_engine_int.issue_active_q')),
                root + '.commit_start_valid', root + '.ldu_result_req_o']
            init = '\n'.join('set mock_values(%s) {%s %s}' % (s, before[f], after[f])
                             for s, f in zip(signals, a.FIELDS))
            program = init + '\n' + r'''
set mock_phase 0
set runs {}
set stops {}
set reads 0
proc stop {args} {
    global stops
    lappend stops $args
    return 7
}
proc run {args} {
    global mock_phase runs
    lappend runs $args
    if {$args eq {1 ns}} {set mock_phase 1}
}
proc get {signal radix value} {
    global mock_phase mock_values reads
    if {$radix ne "-radix" || $value ne "decimal"} {error "wrong get API"}
    incr reads
    return 'd[lindex $mock_values($signal) $mock_phase]
}
proc quit {} {}
'''
            if missing: program += 'unset mock_values(' + ce + '.state_q)\n'
            program += 'source {' + str(a.OBSERVER) + '}\n'
            program += 'puts "MOCK calls=$reads runs=$runs stops=$stops"\n'
            completed = subprocess.run([shell], input=program, text=True, cwd=directory,
                capture_output=True, timeout=10, check=True)
            return Path(directory, 'gap65-observer.tsv').read_text(), completed.stdout

    def test_tcl_mock_exact_two_snapshots_no_polling(self):
        text, log = self.mock_tcl()
        self.assertEqual(a.observer_samples(text), samples())
        self.assertIn('calls=30 runs={100000 ns} {1 ps} {1 ns} {}', log)
        self.assertIn('{-delete 7}', log)
        self.assertIn('-negedge ara_tb.clk -condition', log)

    def test_tcl_mock_missing_signal_and_load_fault_fail_closed(self):
        text, log = self.mock_tcl(missing=True)
        self.assertIn('FAILED: gap65 observer', log)
        with self.assertRaises(ValueError): a.observer_samples(text)
        text, _ = self.mock_tcl(wrong=True)
        with self.assertRaises(ValueError): a.observer_samples(text)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'verification/out', prefix='gap65-admission-mock-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / 'input'; self.input.write_bytes(b'fixed input')
        self.plan = self.root / 'admission.json'
        self.data = dict(status='READY_FOR_REVIEW_NO_RTL_RUN', case=a.CASE, timeout_s=300,
            observer=str(a.OBSERVER), host_preflight=str(a.HOST), simv='mock-simv',
            image={}, design_vdb='mock-vdb', design_files={},
            files={str(self.input): a.sha(self.input)})
        a.save(self.plan, self.data); self.digest = a.sha(self.plan)
        contexts = ExitStack(); self.addCleanup(contexts.close)
        contexts.enter_context(patch.object(a.full.batch, 'simulation_image', return_value={}))
        contexts.enter_context(patch.object(a.full.base, 'inventory', return_value={}))
        self.spawn = contexts.enter_context(patch('subprocess.Popen', side_effect=AssertionError('no child allowed')))
        self.exec = contexts.enter_context(patch.object(os, 'execv', side_effect=AssertionError('no exec allowed')))

    def test_positive_validation_zero_subprocess(self):
        plan, files = a.verify_plan(self.plan, self.digest)
        self.assertEqual(plan, self.data)
        self.assertEqual(len(files), 2)
        self.spawn.assert_not_called(); self.exec.assert_not_called()

    def test_no_baseline_vdb_inventory_in_runtime_validation(self):
        with patch.object(a.full.base, 'inventory', return_value={}) as inventory:
            a.verify_plan(self.plan, self.digest)
        inventory.assert_called_once_with(Path('mock-vdb'))

    def test_original_pin_mutation_zero_subprocess(self):
        stamp = self.input.stat(); self.input.write_bytes(b'other input')
        os.utime(self.input, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        with self.assertRaises(ValueError): a.run(self.plan, self.digest, self.root / 'not-created')
        self.assertFalse((self.root / 'not-created').exists())
        self.spawn.assert_not_called(); self.exec.assert_not_called()

    def test_external_digest_not_replaceable_by_manifest_reseal(self):
        self.data['timeout_s'] = 301; a.save(self.plan, self.data)
        a.save(self.root / 'admission.sha256.json', {str(self.plan): a.sha(self.plan)})
        with self.assertRaises(ValueError): a.verify_plan(self.plan, self.digest)
        self.spawn.assert_not_called()

    def test_publication_rechecks_original_admission_and_expected_pin_set(self):
        _, original = a.verify_plan(self.plan, self.digest)
        with patch.object(a, 'verify_plan', return_value=(self.data, dict(original, extra='0' * 64))):
            with self.assertRaisesRegex(ValueError, 'expected pin set'):
                a.revalidate(self.plan, self.digest, original, {})
        self.input.write_bytes(b'mutated after run')
        with self.assertRaises(ValueError): a.revalidate(self.plan, self.digest, original, {})
        self.spawn.assert_not_called(); self.exec.assert_not_called()

    def test_runtime_config_mutation_before_exec(self):
        config = self.root / 'runtime.json'; a.save(config, {'x': 1})
        digest = a.sha(config); a.save(config, {'x': 2})
        with self.assertRaises(ValueError): a.sim_exec(config, digest, [])
        self.exec.assert_not_called()

    def test_exact_command_and_foreign_cwd_or_overrides(self):
        artifact = self.root / 'results/tests' / ('app_' + a.NAME)
        work = artifact / 'work'; work.mkdir(parents=True)
        elf = artifact / 'input.elf'; elf.write_bytes(b'elf')
        plan = dict(self.data, elf_sha256=a.sha(elf))
        args = a.expected_args(self.root)
        with patch.object(a.full.batch, 'check'):
            command = a.simulator_command(plan, self.root, args, work)
            self.assertEqual(command[:5], ['mock-simv', '-ucli', '-do', str(a.OBSERVER), '-no_save'])
            for change in (args + ['-do', 'foreign.tcl'], args + ['+ARA_UVM_RESET_ON_AXI=read'],
                           args + ['-cm_dir', '/tmp/foreign.vdb'], args[:-1]):
                with self.assertRaises(ValueError): a.simulator_command(plan, self.root, change, work)
            with self.assertRaises(ValueError): a.simulator_command(plan, self.root, args, self.root)
            (work / 'gap65-observer.tsv').write_text('old')
            with self.assertRaises(ValueError): a.simulator_command(plan, self.root, args, work)
        self.exec.assert_not_called()

    def mock_run(self, mutate=False):
        simdir = self.root / 'sim'; simdir.mkdir()
        (simdir / 'simulator.conf').write_text('mock config')
        elf = self.root / 'source.elf'; elf.write_bytes(b'mock ELF, never executed')
        self.data.update(simv=str(simdir / 'simv'), elf=str(elf), elf_sha256=a.sha(elf),
                         baseline=str(a.checks.BASE), target=a.checks.TARGET)
        a.save(self.plan, self.data); self.digest = a.sha(self.plan)
        output = ROOT / 'verification/out' / ('gap65-late-fault-runtime-' + self.root.name)
        self.addCleanup(lambda: shutil.rmtree(output) if output.exists() else None)
        self.mock_output = output
        artifact = output / 'results/tests' / ('app_' + a.NAME)
        command = []

        def fake_test(runner, test, wrapper):
            work = artifact / 'work'; work.mkdir(parents=True)
            (artifact / 'input.elf').write_bytes(test.binary.read_bytes())
            command.extend(a.simulator_command(self.data, output, a.expected_args(output), work))
            a.save(work / 'coverage.command.json', dict(command=command, cwd=str(work)))
            log = ('GAP65 traps=1 cause=5 tval=c0000000 pc=800016c8 '
                   'fault_vrf=128 recovery_vrf=128 numerical=16 errors=0\n'
                   'PASSED: qbs_gap65_late_fault checks=49 errors=0\n')
            (artifact / 'console.log').write_text(log)
            (work / 'run.vcs.log').write_text(log)
            (work / 'gap65-observer.tsv').write_text(transcript())
            if mutate: self.input.write_bytes(b'mutated inside runner hook')
            return TestResult(a.CASE, 'app', 'PASS', 0, 0.0, '', artifact)

        def fake_xml(path):
            root = ET.Element('root')
            ET.SubElement(root, 'srctest', cmdline=a.shlex.join(command))
            return root

        audit = dict(status='PASS', errors=[], case_count=1, passed_cases=1, failed_cases=0,
            cases=[dict(status='PASS', name=a.CASE, errors=[], artifact_dir=str(artifact))],
            policy=dict(require_complete=True, require_trace=True))
        raw = {a.checks.TARGET_SCOPE: dict(checksum='2676500856', width=43, bits=hex(1 << (42 - 15)))}
        with patch.object(a.RegressionRunner, '_run_test', fake_test), \
             patch.object(a, 'audit_run', return_value=audit), \
             patch.object(a.full.batch, 'valid_vdb', return_value={}), \
             patch.object(a.full.batch, 'xml_root', side_effect=fake_xml), \
             patch.object(a.bitmaps, 'read_metric', return_value=raw):
            return a.run(self.plan, self.digest, output)

    def test_full_runtime_control_flow_mock_no_simulator(self):
        self.assertEqual(self.mock_run(), 0)
        result = a.read(self.mock_output / 'result.json')
        self.assertEqual(result['samples'], samples())
        self.spawn.assert_not_called(); self.exec.assert_not_called()

    def test_post_runner_mutation_blocks_publication_zero_subprocess(self):
        with self.assertRaises(ValueError): self.mock_run(mutate=True)
        self.assertFalse((self.mock_output / 'result.json').exists())
        self.assertEqual(a.read(self.mock_output / 'rejected.json')['status'], 'REJECTED')
        self.spawn.assert_not_called(); self.exec.assert_not_called()


if __name__ == '__main__':
    unittest.main()
