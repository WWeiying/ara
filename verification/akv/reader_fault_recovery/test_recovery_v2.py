"""Synthetic V2 identity/control checks; no simulation, UVM or export execution."""
import argparse
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reader_fault_recovery_v2_tests', HERE/'run_v2.py')
r = importlib.util.module_from_spec(spec); sys.modules[spec.name] = r; spec.loader.exec_module(r)
c = r.c


class V2Tests(unittest.TestCase):
    def fixture(self, p):
        build, baseline, prior, pre = (p/n for n in ('build', 'run01', 'recovery01', 'preflight01'))
        raw, work = baseline/'baseline', prior/'baseline-audit'
        for path in (build, raw, work, pre): path.mkdir(parents=True)
        for name in ('run.vcs.log', 'vector_trace.csv', 'reader.fsdb', 'console.log'):
            (raw/name).write_text('unfiltered '+name)
        argv = ['/fixture/simv']
        c.save(raw/'console.command.json', dict(argv=argv)); c.save(raw/'console.exit.json', dict(exit_code=0, error=None))
        evidence = c.s.hashes(raw.iterdir())
        c.save(pre/'source-pins.json', evidence)
        c.save(pre/'baseline-input-seal.json', dict(evidence_sha256=evidence))
        c.save(prior/'baseline-input-seal.json', dict(evidence_sha256=evidence))
        c.save(pre/'status.json', dict(state=r.PREFLIGHT_STATE, child_pid=None))
        c.save(pre/'preflight.json', dict(source_pins_sha256=c.digest(pre/'source-pins.json'),
            baseline_input_seal_sha256=c.digest(pre/'baseline-input-seal.json')))
        pins = dict(evidence)
        c.s.merge_pins(pins, c.s.hashes([pre/n for n in
            ('source-pins.json', 'baseline-input-seal.json', 'status.json', 'preflight.json')]))
        c.save(prior/'source-pins.json', pins)
        status = dict(state='FAIL', child_pid=None, error="ValueError('EXTRACTING returned 1')",
            extracting_exit_code=1, uvm_check_exit_code=0, variant='baseline',
            candidate_simulations_launched=0, baseline_simulations_launched=0, baseline_reused=True,
            original_worker_state='FAIL', configuration=dict(build=str(build), build_sha256=r.BUILD_SHA,
                baseline=str(baseline), candidate_timeout_seconds=900, fsdbreport=str(r.EXPORTER)))
        for name in ('status.json', 'result.json'): c.save(prior/name, status)
        simv, elf = build/'baseline/simv', build/'program.elf'
        profile, rtl = p/'original-profile.json', p/'vlsu.sv'
        c.save(profile, {}); rtl.write_text('fixture')
        report = dict(elf=str(elf), elf_sha256='a'*64, weights=dict(address=0x80002e80),
                      images=dict(baseline=dict(simv=str(simv), pins={})))
        prepared = dict(recipes=dict(baseline=dict(capture=str(profile), vlsu=str(rtl))))
        uv = [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
              '--require-axi', '--require-axi-write', '--vector-trace', raw/'vector_trace.csv',
              '--log', raw/'run.vcs.log', '--simv', simv, '--elf', elf, '--output', work/'uvm_result.json']
        ex = [sys.executable, '-B', r.ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py', '--fsdb', raw/'reader.fsdb',
              '--profile', profile, '--begin', '0ns', '--end', '250000ns', '--output', work/'cycles', '--fsdbreport', r.EXPORTER]
        for name, command, timeout, exit_code, error in (
            ('uvm-check', uv, 600, 0, None), ('extract', ex, 300, 1, "ValueError('EXTRACTING returned 1')")):
            c.save(work/(name+'.command.json'), dict(argv=list(map(str, command)), cwd=str(work), timeout_seconds=timeout))
            c.save(work/(name+'.exit.json'), dict(exit_code=exit_code, error=error)); (work/(name+'.log')).write_text('log')
        c.save(work/'uvm_result.json', dict(log_sha256=c.digest(raw/'run.vcs.log'),
            vector_trace_sha256=c.digest(raw/'vector_trace.csv'), contract_event_count=1,
            uvm_backend_event_count=1, axi_read_counts=dict(completed=1), axi_write_counts=dict(matched=1)))
        for name, value in (('BUILD', build), ('BASELINE', baseline), ('RECOVERY01', prior),
                            ('PREFLIGHT01', pre), ('PREFLIGHT01_SHA', c.digest(pre/'preflight.json'))):
            ctx = patch.object(r, name, value); ctx.start(); self.addCleanup(ctx.stop)
        return report, prepared, evidence, raw, work, status

    def test_exact_reused_uvm_and_no_old_source_exemptions(self):
        with tempfile.TemporaryDirectory() as d, patch.object(c.s, 'check_result'):
            report, prepared, evidence, raw, work, _ = self.fixture(Path(d))
            proof, pins, seal = r.checked_baseline_uvm(report, prepared, evidence)
            self.assertEqual(proof, work/'uvm_result.json'); self.assertFalse(seal['previous_clean_pass'])
            c.s.verify_pins(pins)
            (raw/'run.vcs.log').write_text('changed old input')
            with self.assertRaises((ValueError, RuntimeError)): r.checked_baseline_uvm(report, prepared, evidence)

    def test_terminal_command_exit_and_raw_protocol_mutations(self):
        with tempfile.TemporaryDirectory() as d, patch.object(c.s, 'check_result'):
            report, prepared, evidence, _, work, status = self.fixture(Path(d))
            for key, value in (('state', 'PASS'), ('extracting_exit_code', 0), ('uvm_check_exit_code', 1),
                               ('candidate_simulations_launched', 1), ('child_pid', 1)):
                changed = dict(status, **{key:value})
                for n in ('status.json', 'result.json'): c.save(work.parent/n, changed)
                with self.subTest(key=key), self.assertRaises((ValueError, RuntimeError)):
                    r.checked_baseline_uvm(report, prepared, evidence)
            for n in ('status.json', 'result.json'): c.save(work.parent/n, status)
            command = c.s.read_json(work/'uvm-check.command.json')
            bad = copy.deepcopy(command); bad['argv'].remove('--require-axi-write')
            c.save(work/'uvm-check.command.json', bad)
            with self.assertRaises((ValueError, RuntimeError)): r.checked_baseline_uvm(report, prepared, evidence)
            c.save(work/'uvm-check.command.json', command)
            c.save(work/'uvm-check.exit.json', dict(error=None, exit_code=1))
            with self.assertRaises((ValueError, RuntimeError)): r.checked_baseline_uvm(report, prepared, evidence)
            c.save(work/'uvm-check.exit.json', dict(error=None, exit_code=0))
            proof = c.s.read_json(work/'uvm_result.json'); proof['vector_trace_sha256'] = '0'*64
            c.save(work/'uvm_result.json', proof)
            with self.assertRaises((ValueError, RuntimeError)): r.checked_baseline_uvm(report, prepared, evidence)

    def test_profiles_only_change_45_paths_preserving_sources(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); prepared = dict(recipes={})
            for mode in c.MODES:
                source = p/(mode+'.json'); c.save(source, c.prep.wave.profile(mode == 'candidate'))
                prepared['recipes'][mode] = dict(capture=str(source))
            original_pins = c.s.hashes(p.glob('*.json'))
            paths, hashes = r.write_profiles(prepared, p)
            for mode in c.MODES:
                old = c.s.read_json(p/(mode+'.json')); new = c.s.read_json(paths[mode])
                self.assertEqual(sum(a != b for a,b in zip(old['signals'], new['signals'])), 45)
                self.assertEqual(new, r.member_profile.successor(old))
                self.assertEqual(c.digest(paths[mode]), hashes[mode])
            c.s.verify_pins(original_pins)

    def test_baseline_reuses_uvm_exports_new_profile_without_events(self):
        with tempfile.TemporaryDirectory() as d, patch.object(c.s, 'check_result'):
            p = Path(d); report, prepared, _, raw, prior, _ = self.fixture(p)
            work = p/'new-audit'; work.mkdir(); profile = p/'new-profile.json'
            c.save(profile, dict(signals=[dict(alias='x')]))
            calls = []
            class Owner:
                state = {}
                def execute(self, argv, log, timeout, phase):
                    calls.append((list(map(str, argv)), phase))
                    if phase == 'EXTRACTING':
                        (work/'cycles').mkdir()
                        c.save(work/'cycles/metadata.json', dict(edge='negedge', cycle_count=11,
                            missing_signals=[], present_signals=['x']))
            with patch.object(r.adapter, 'check_log'), patch.object(r.adapter, 'check_log_and_cycles', return_value={}):
                r.audit_variant(Owner(), 'baseline', raw, work, ['/fixture/simv'], report, prepared,
                    r.EXPORTER, Mock(), profile, prior/'uvm_result.json')
            self.assertEqual([phase for _,phase in calls], ['EXTRACTING', 'MANIFEST_AFTER'])
            command = calls[0][0]
            self.assertEqual(command[command.index('--profile')+1], str(profile))
            self.assertEqual(command[command.index('--fsdb')+1], str(raw/'reader.fsdb'))
            self.assertIn('--no-events', command)
            self.assertFalse(c.s.read_json(work/'uvm-reuse.json')['rerun'])

    def test_preflight_never_executes_eda(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); build, baseline = p/'build', p/'baseline'; build.mkdir(); baseline.mkdir()
            args = argparse.Namespace(build=build, expected_build_sha256=r.BUILD_SHA, baseline=baseline,
                output=p/'out', timeout=900, fsdbreport=r.EXPORTER, preflight_only=True,
                approved_preflight=None, expected_preflight_sha256=None)
            with patch.object(r, 'BUILD', build), patch.object(r, 'BASELINE', baseline), \
                 patch.object(r, 'own_pins', return_value={}), \
                 patch.object(c, 'checked_build', return_value=({'images':{}}, {}, {})), \
                 patch.object(r, 'baseline_inputs', return_value=({}, {}, [], {'commands':71})), \
                 patch.object(r, 'checked_baseline_uvm', return_value=(p/'uvm.json', {}, {})), \
                 patch.object(r, 'write_profiles', return_value=({}, {})), \
                 patch.object(c.hand, 'exporter_files', return_value=[]), \
                 patch.object(c.Execution, 'execute', side_effect=AssertionError('EDA forbidden')) as execute:
                r.run(args); execute.assert_not_called()
            self.assertTrue(c.s.read_json(args.output/'preflight.json')['baseline_uvm_reused'])

    def test_full_execution_finalizes_paths_and_preserves_regression(self):
        # Exercise the real non-preflight orchestration and final receipt writer.
        # Only external execution, input validation and semantic producers are synthetic.
        for regression in (False, True):
            with self.subTest(regression=regression), tempfile.TemporaryDirectory() as d:
                p = Path(d); build, baseline, approval = p/'build', p/'old', p/'approval'
                for path in (build, baseline, approval): path.mkdir()
                args = argparse.Namespace(build=build, expected_build_sha256=r.BUILD_SHA, baseline=baseline,
                    output=p/'out', timeout=900, fsdbreport=r.EXPORTER, preflight_only=False,
                    approved_preflight=approval, expected_preflight_sha256='a'*64)
                report = dict(images={m:dict(simv=str(build/m/'simv'), pins={}) for m in c.MODES},
                              elf=str(build/'test.elf'), elf_sha256='b'*64, weights=dict(address=0x80002e80))
                prepared = dict(recipes={})
                for mode in c.MODES:
                    capture = p/(mode+'.json'); c.save(capture, c.prep.wave.profile(mode == 'candidate'))
                    prepared['recipes'][mode] = dict(capture=str(capture), script=str(p/(mode+'.tcl')))
                calls, closed = [], []
                def execute(owner, argv, log, timeout, phase):
                    calls.append((phase, list(map(str, argv))))
                    log.write_text('synthetic phase output')
                    c.save(log.with_suffix('.command.json'), dict(argv=list(map(str, argv)),
                                                                cwd=str(log.parent), timeout_seconds=timeout))
                    c.save(log.with_suffix('.exit.json'), dict(error=None, exit_code=0))
                def audit(owner, mode, raw, work, *unused):
                    (work/'cycles').mkdir()
                    for name in ('extract.log', 'checked.json', 'manifest-after.log', 'cycles/cycles.csv',
                                 'cycles/metadata.json', 'cycles/fsdbreport.raw.csv'):
                        (work/name).write_text('synthetic closed evidence')
                    names = ('uvm-reuse.json',) if mode == 'baseline' else (
                        'uvm_result.json', 'uvm-check.log', 'run.vcs.log', 'vector_trace.csv', 'reader.fsdb')
                    for name in names: (work/name).write_text('synthetic closed evidence')
                    rows = [dict(seq=i, busy_cycles=10) for i in range(71)]
                    if regression and mode == 'candidate':
                        rows[0]['busy_cycles'] += 1; rows[1]['busy_cycles'] -= 1
                    return dict(state='LOG_AND_WAVE_CHECKED_NOT_OVERALL_ACCEPTANCE', wave={},
                                log=dict(commands=71, trap_tval=0x80002e80, records=rows))
                real_closed = c.closed_evidence
                def seal(paths):
                    closed.extend(paths)
                    self.assertTrue(all(isinstance(path, Path) for path in paths))
                    return real_closed(paths)
                with patch.object(r, 'BUILD', build), patch.object(r, 'BASELINE', baseline), \
                     patch.object(r, 'own_pins', return_value={}), \
                     patch.object(c, 'checked_build', return_value=(report, prepared, {})), \
                     patch.object(r, 'baseline_inputs', return_value=({}, {}, [], {'commands':71})), \
                     patch.object(r, 'checked_baseline_uvm', return_value=(p/'uvm.json', {}, {'evidence_sha256':{}})), \
                     patch.object(r, 'check_approval', return_value={}), \
                     patch.object(c.hand, 'exporter_files', return_value=[]), \
                     patch.object(c.s, 'image_files', return_value=[]), patch.object(c, 'verify_manifest'), \
                     patch.object(c.Execution, 'execute', new=execute), patch.object(r, 'audit_variant', side_effect=audit), \
                     patch.object(c, 'closed_evidence', side_effect=seal):
                    if regression:
                        with self.assertRaisesRegex((ValueError, RuntimeError), 'Paired regression'): r.run(args)
                    else:
                        r.run(args)
                result = c.s.read_json(args.output/'result.json')
                self.assertEqual(result['state'], 'REGRESSION' if regression else 'PASS')
                self.assertEqual(c.s.read_json(args.output/'status.json')['state'], result['state'])
                self.assertEqual([phase for phase,_ in calls].count('RUNNING'), 1)
                self.assertTrue(all('/candidate/simv' in command[0] for phase,command in calls if phase == 'RUNNING'))
                for mode in c.MODES:
                    profile = args.output/'profiles'/(mode+'.json')
                    self.assertIn(profile, closed)
                    self.assertEqual(result['evidence_sha256'][str(profile)], c.digest(profile))
                    self.assertEqual(result['profiles'][mode]['log']['commands'], 71)
                if regression: self.assertEqual(len(result['differences']), 2)
                c.s.verify_pins(result['evidence_sha256'])


if __name__ == '__main__': unittest.main()
