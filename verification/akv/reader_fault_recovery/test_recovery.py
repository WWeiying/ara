"""Synthetic recovery identity and orchestration tests; never launches EDA."""
import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reader_fault_recovery_owned_tests', HERE/'run.py')
r = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = r
spec.loader.exec_module(r)
c = r.c


def status(build):
    return dict(state='FAIL', error=r.ORIGINAL_ERROR, variant='baseline', build=str(build),
                child_pid=None, running_exit_code=0, manifest_before_exit_code=0,
                image_contract_exit_code=0, simulator_pid=123)


def parsed():
    return dict(state='LOG_AND_WAVE_CHECKED_NOT_OVERALL_ACCEPTANCE',
                log=dict(commands=71, trap_tval=0x80002e80,
                         records=[dict(seq=i, busy_cycles=10) for i in range(71)]), wave={})


class RecoveryTests(unittest.TestCase):
    def baseline_fixture(self, p):
        build, baseline, source = p/'build', p/'old', p/'source.sv'
        build.mkdir(); baseline.mkdir(); work = baseline/'baseline'; work.mkdir()
        source.write_text('pinned RTL fixture')
        build_pins = c.s.hashes([source])
        c.save(baseline/'source-pins.json', build_pins)
        for name in ('status.json', 'result.json'): c.save(baseline/name, status(build))
        for name in r.RAW_NAMES: (work/name).write_text('raw '+name)
        report = dict(images=dict(baseline=dict(simv=str(build/'baseline/simv'))),
                      elf=str(build/'program.elf'), weights=dict(address=0x80002e80))
        recipe = dict(script=str(p/'probe.tcl'), vlsu=str(source))
        prepared = dict(recipes=dict(baseline=recipe))
        argv = r.original.simulation_command(Path(report['images']['baseline']['simv']), Path(report['elf']),
                    0x80002e80, Path(recipe['script']), work/'run.vcs.log', work/'vector_trace.csv')
        commands = {
            'console':(argv, 900),
            'manifest-before':([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                                build/'baseline/vcs_source_manifest.json', '--check'], 300),
            'image-contract':(['bash', r.ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                               build/'baseline', Path(report['elf'])], 180)}
        for stem, (command, timeout) in commands.items():
            c.save(work/(stem+'.command.json'), dict(argv=list(map(str, command)), cwd=str(work), timeout_seconds=timeout))
            c.save(work/(stem+'.exit.json'), dict(error=None, exit_code=0))
        return baseline, build, report, prepared, build_pins

    def test_baseline_inputs_current_build_and_closed_raw_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.baseline_fixture(Path(directory)); baseline, build, report, prepared, pins = values
            with patch.object(r, 'BASELINE', baseline), patch.object(r, 'BUILD', build), \
                 patch.object(r.adapter, 'check_log', return_value={'commands':71}) as semantic:
                allpins, evidence, argv, _ = r.baseline_inputs(*values)
                self.assertEqual(list(map(str, semantic.call_args.args[-1])), argv)
                self.assertTrue(all(str(baseline/'baseline'/n) in evidence for n in r.RAW_NAMES))
                c.s.verify_pins(allpins)
                for name in ('run.vcs.log', 'vector_trace.csv', 'reader.fsdb', 'console.command.json'):
                    path = baseline/'baseline'/name; before = path.read_bytes(); path.write_bytes(before+b'drift')
                    with self.subTest(name=name), self.assertRaises((ValueError, RuntimeError)):
                        c.s.verify_pins(evidence)
                    path.write_bytes(before)
                wrongpins = {key:'0'*64 for key in pins}
                with self.assertRaises((ValueError, RuntimeError)):
                    r.baseline_inputs(baseline, build, report, prepared, wrongpins)
                source = Path(next(iter(pins))); source.write_text('source changed')
                with self.assertRaises((ValueError, RuntimeError)): r.baseline_inputs(*values)

    def test_previous_candidate_and_missing_baseline_artifact_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.baseline_fixture(Path(directory)); baseline, build = values[:2]
            with patch.object(r, 'BASELINE', baseline), patch.object(r, 'BUILD', build), \
                 patch.object(r.adapter, 'check_log', return_value={'commands':71}):
                (baseline/'candidate').mkdir()
                with self.assertRaises((ValueError, RuntimeError)): r.baseline_inputs(*values)
                (baseline/'candidate').rmdir(); (baseline/'baseline/reader.fsdb').unlink()
                with self.assertRaises((ValueError, RuntimeError)): r.baseline_inputs(*values)

    def test_exact_terminal_failure_only(self):
        good = status(Path('/build'))
        r.failed_terminal(good, good.copy(), Path('/build'))
        for key, value in (('state', 'PASS'), ('error', 'different failure'), ('variant', 'candidate'),
                           ('build', '/other'), ('child_pid', 100), ('running_exit_code', 1),
                           ('manifest_before_exit_code', 1), ('image_contract_exit_code', 1),
                           ('simulator_pid', None)):
            bad = dict(good, **{key:value})
            with self.subTest(key=key), self.assertRaises((ValueError, RuntimeError)):
                r.failed_terminal(bad, bad.copy(), Path('/build'))
        with self.assertRaises((ValueError, RuntimeError)):
            r.failed_terminal(good, dict(good, error='changed result'), Path('/build'))

    def test_command_exit_cwd_timeout_and_args(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory); argv = ['/reviewed/simv', '+READER_FAULT_TARGET=80002e80']
            good = dict(argv=argv, cwd=str(work), timeout_seconds=900)
            c.save(work/'console.command.json', good)
            c.save(work/'console.exit.json', dict(error=None, exit_code=0))
            r.exact_command(work, 'console', argv, 900)
            for changed in (dict(argv=argv+['+extra']), dict(cwd='/elsewhere'), dict(timeout_seconds=901)):
                c.save(work/'console.command.json', {**good, **changed})
                with self.assertRaises((ValueError, RuntimeError)): r.exact_command(work, 'console', argv, 900)
            c.save(work/'console.command.json', good)
            for receipt in (dict(error=None, exit_code=1), dict(error='interrupted', exit_code=0)):
                c.save(work/'console.exit.json', receipt)
                with self.assertRaises((ValueError, RuntimeError)): r.exact_command(work, 'console', argv, 900)

    def test_approved_preflight_binds_raw_pins_and_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory); raw = p/'raw.log'; raw.write_text('original bytes')
            pins = c.s.hashes([raw]); config = dict(candidate_timeout_seconds=900)
            c.save(p/'source-pins.json', pins); c.save(p/'baseline-input-seal.json', dict(original_clean_pass=False))
            c.save(p/'status.json', dict(state=r.PREFLIGHT_STATE, child_pid=None))
            receipt = dict(state=r.PREFLIGHT_STATE, execution='NO_EDA_INVOKED', configuration=config,
                source_pins_sha256=c.digest(p/'source-pins.json'),
                baseline_input_seal_sha256=c.digest(p/'baseline-input-seal.json'))
            c.save(p/'preflight.json', receipt); sha = c.digest(p/'preflight.json')
            self.assertEqual(len(r.check_approval(p, sha, config, pins)), 4)
            for badsha, badconfig, badpins in ((sha, dict(candidate_timeout_seconds=899), pins),
                                              ('0'*64, config, pins), (sha, config, {})):
                with self.assertRaises((ValueError, RuntimeError)): r.check_approval(p, badsha, badconfig, badpins)
            raw.write_text('changed bytes')
            with self.assertRaises((ValueError, RuntimeError)): r.check_approval(p, sha, config, pins)
            raw.write_text('original bytes'); c.save(p/'baseline-input-seal.json', {})
            with self.assertRaises((ValueError, RuntimeError)): r.check_approval(p, sha, config, pins)

    def test_baseline_failure_prevents_candidate(self):
        candidate = Mock(return_value=parsed())
        with self.assertRaises(ValueError):
            r.baseline_then_candidate(Mock(side_effect=ValueError('UVM or wave failed')), candidate)
        candidate.assert_not_called()
        bad = parsed(); bad['state'] = 'LOG_CHECKED_NOT_OVERALL_ACCEPTANCE'
        with self.assertRaises((ValueError, RuntimeError)):
            r.baseline_then_candidate(lambda:bad, candidate)
        candidate.assert_not_called()

    def test_one_candidate_and_no_hidden_command_regression(self):
        order = []
        def baseline(): order.append('baseline_audit'); return parsed()
        def candidate(): order.append('candidate_run_and_audit'); return parsed()
        result, _ = r.baseline_then_candidate(baseline, candidate)
        self.assertEqual(order, ['baseline_audit', 'candidate_run_and_audit'])
        self.assertEqual(result['state'], 'PASS')
        changed = parsed(); changed['log']['records'][0]['busy_cycles'] += 1
        changed['log']['records'][1]['busy_cycles'] -= 1
        result, _ = r.baseline_then_candidate(baseline, lambda:changed)
        self.assertEqual(result['state'], 'REGRESSION')
        self.assertEqual(len(result['differences']), 2)

    def test_unfiltered_protocol_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory); log, trace = p/'raw.log', p/'raw.csv'
            log.write_text('Command: original header\nraw content\n'); trace.write_text('raw trace')
            proof = dict(log_sha256=c.digest(log), vector_trace_sha256=c.digest(trace),
                contract_event_count=1, uvm_backend_event_count=1,
                axi_read_counts=dict(completed=1), axi_write_counts=dict(matched=1))
            c.save(p/'uvm.json', proof)
            with patch.object(c.s, 'check_result') as checked:
                r.verify_protocol(p/'uvm.json', log, trace, 'elf', {'image':'pin'})
                checked.assert_called_once_with(p/'uvm.json', 'elf', {'image':'pin'})
                for delta in (dict(log_sha256='0'*64), dict(vector_trace_sha256='0'*64),
                              dict(axi_write_counts={}), dict(contract_event_count=0)):
                    c.save(p/'uvm.json', {**proof, **delta})
                    with self.assertRaises((ValueError, RuntimeError)):
                        r.verify_protocol(p/'uvm.json', log, trace, 'elf', {})

    def test_baseline_audit_uses_original_raw_and_new_export_only(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory); baseline, build, report, prepared, _ = self.baseline_fixture(p)
            raw, work = baseline/'baseline', p/'baseline-audit'; work.mkdir()
            capture = p/'capture.json'; c.save(capture, dict(signals=[dict(alias='x')]))
            prepared['recipes']['baseline']['capture'] = str(capture)
            report['images']['baseline']['pins'] = {}; report['elf_sha256'] = 'a'*64
            commands = []
            class Owner:
                state = {}
                def execute(self, argv, log, timeout, phase):
                    commands.append((list(map(str, argv)), log, timeout, phase))
                    if phase == 'EXTRACTING':
                        (work/'cycles').mkdir()
                        c.save(work/'cycles/metadata.json', dict(edge='negedge', cycle_count=11,
                            present_signals=['x'], missing_signals=[]))
            argv = c.s.read_json(raw/'console.command.json')['argv']
            identity = Mock()
            with patch.object(r.adapter, 'check_log', return_value={'commands':71}), \
                 patch.object(r.adapter, 'check_log_and_cycles', return_value=parsed()) as wave, \
                 patch.object(r, 'verify_protocol') as protocol:
                result = r.audit_variant(Owner(), 'baseline', raw, work, argv, report, prepared, p/'fsdbreport', identity)
            self.assertEqual(result, parsed())
            self.assertEqual([x[3] for x in commands], ['UVM_CHECK', 'EXTRACTING', 'MANIFEST_AFTER'])
            uvm, export = commands[0][0], commands[1][0]
            self.assertEqual(uvm[uvm.index('--log')+1], str(raw/'run.vcs.log'))
            self.assertEqual(uvm[uvm.index('--vector-trace')+1], str(raw/'vector_trace.csv'))
            self.assertEqual(export[export.index('--fsdb')+1], str(raw/'reader.fsdb'))
            self.assertEqual(export[export.index('--output')+1], str(work/'cycles'))
            self.assertEqual(wave.call_args.args[2], work/'cycles/cycles.csv')
            self.assertEqual(protocol.call_args.args[1:3], (raw/'run.vcs.log', raw/'vector_trace.csv'))
            self.assertEqual(identity.call_count, 2)

    def test_preflight_cannot_execute_any_process(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory); build, baseline = p/'build', p/'old'
            build.mkdir(); baseline.mkdir()
            args = argparse.Namespace(build=build, expected_build_sha256=r.BUILD_SHA, baseline=baseline,
                output=p/'new', timeout=900, fsdbreport=p/'fsdbreport', preflight_only=True,
                approved_preflight=None, expected_preflight_sha256=None)
            with patch.object(r, 'BUILD', build), patch.object(r, 'BASELINE', baseline), \
                 patch.object(r, 'own_pins', return_value={}), \
                 patch.object(c, 'checked_build', return_value=({'images':{}}, {}, {})), \
                 patch.object(r, 'baseline_inputs', return_value=({}, {}, [], {'commands':71})), \
                 patch.object(c.hand, 'exporter_files', return_value=[]), \
                 patch.object(c.Execution, 'execute', side_effect=AssertionError('No EDA in preflight')) as execute:
                r.run(args)
                execute.assert_not_called()
            receipt = c.s.read_json(args.output/'preflight.json')
            self.assertEqual(receipt['state'], r.PREFLIGHT_STATE)
            self.assertFalse(receipt['baseline_protocol_and_wave_accepted'])
            self.assertEqual(c.s.read_json(args.output/'status.json')['candidate_simulations_launched'], 0)


if __name__ == '__main__': unittest.main()
