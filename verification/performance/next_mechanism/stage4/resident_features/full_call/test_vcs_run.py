#!/usr/bin/env python3
"""Host-only mutations; synthetic receipts are never RTL/numerical evidence."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('stage4_features_vcs_test', HERE/'vcs_run.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


def software():
    return dict(schema='stage4-features-full-call-v1', state='BUILT_NOT_EXECUTED', kind='perf',
        scope='synthetic runner contract only', post_pins_match=True,
        elf='/frozen/attention_features.elf', elf_sha256='a'*64, source_pins_sha256='b'*64,
        checker_dependencies={'check.py': 'c'*64, 'fixture.py': 'd'*64},
        expected_work=dict(calls=4, output_values=1024, legacy_commands=482,
            legacy_per_call=[237, 4, 4, 237], resident_commands=12,
            actual_entries={k: 2*r.perf_entries(False)[k]+2*r.perf_entries(True)[k] for k in r.ENTRY_NAMES}))


def sdk_proof(sw):
    w = sw['expected_work']
    return dict(state='SDK_FEATURES_CHECKED', scope=sw['scope'], protocol_checked=False,
        post_image_checked=False, performance_acceptance=False, whole_model=False,
        numerical=dict(calls=w['calls'], output_values=w['output_values'], bitexact=True,
            fflags_checked=True, vcsr_vstart_checked=True, fcsr=[3]*w['calls'],
            non_rne_pair_checked=sw['kind'] == 'functional',
            timing=dict(full_call_cycles=[100]*w['calls'], issue_cycles=[90]*w['calls'],
                final_drain_cycles=[10]*w['calls'], strong_baseline_mean=100, resident_mean=100, full_call_speedup=1)),
        legacy_work=dict(commands=w['legacy_commands'], per_call=list(w['legacy_per_call'])),
        resident_work=[{} for _ in range(w['resident_commands'])],
        vector_work=dict(resident_commands=w['resident_commands']),
        actual_entries=dict(calls=w['calls'], per_call=[r.perf_entries(on) for on in (False, True, True, False)],
                            rotation_branch_body_checked=True))


def fake_build(root):
    (root/'inputs/support').mkdir(parents=True)
    (root/'attention_features.elf').write_bytes(b'Host identity only, not an executable')
    (root/'inputs/fixture.py').write_text('SYNTHETIC = True\n')
    (root/'inputs/support/contract.py').write_text('SYNTHETIC = True\n')
    (root/'inputs/check.py').write_text(
        'import json\nimport importlib.util\nfrom pathlib import Path\n'
        's=importlib.util.spec_from_file_location("test_fixture",Path(__file__).parent/"fixture.py")\n'
        'f=importlib.util.module_from_spec(s);s.loader.exec_module(f)\n'
        'def build_receipt(path): return json.loads((Path(path)/"build.json").read_text())\n')
    sw = software()
    sw['elf'] = str(root/'attention_features.elf'); sw['elf_sha256'] = r.b.sha(sw['elf'])
    sw['checker_dependencies'] = {name: r.b.sha(root/'inputs'/name) for name in
                                   ('check.py', 'fixture.py', 'support/contract.py')}
    pins = r.b.files(root/'inputs')
    r.b.save(root/'source-pins.json', pins)
    sw['source_pins_sha256'] = r.b.sha(root/'source-pins.json')
    sw['artifacts'] = pins | {sw['elf']: sw['elf_sha256']}
    r.b.save(root/'build.json', sw)
    return sw, r.b.sha(root/'build.json')


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = r.b.read(r.SOC/'build.json')
        cls.sw = software()

    def test_actual_accepted_soc_identity_no_compile(self):
        self.assertEqual(r.b.sha(r.SOC/'build.json'), r.SOC_SHA)
        soc, pins = r.b.checked_build(r.SOC)
        self.assertEqual(soc['configuration'], r.b.CONFIG)
        self.assertEqual(soc['image_contract'], r.b.IMAGE_CONTRACT)
        self.assertEqual(soc['cpu_overlay'], r.b.CPU_OVERLAY)
        self.assertEqual(soc['configuration']['resident_capability'], 0)
        self.assertFalse(any(Path(p).is_relative_to(r.ROOT/'hardware/src') for p in pins))

    def test_build_identity_and_checker_closure_before_import(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(r, 'software_path', side_effect=Path):
            root = Path(temp); sw, review = fake_build(root)
            self.assertEqual(r.software_receipt(root, review)[0], sw)
            self.assertEqual(r.checker(root, review).build_receipt(root), sw)
            for bad in ('', 'wrong', '0'*64):
                with patch.object(r, 'load') as load, self.assertRaises(ValueError):
                    r.checker(root, bad)
                load.assert_not_called()
            for relative in ('source-pins.json', 'attention_features.elf', 'inputs/fixture.py',
                             'inputs/check.py', 'inputs/support/contract.py'):
                p = root/relative; saved = p.read_bytes(); p.write_bytes(saved+b'\nchanged\n')
                with patch.object(r, 'load') as load, self.assertRaises(ValueError):
                    r.checker(root, review)
                load.assert_not_called(); p.write_bytes(saved)

    def test_frozen_checker_copy_and_cached_module_isolation(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(r, 'software_path', side_effect=Path):
            root = Path(temp)/'build'; root.mkdir(); sw, review = fake_build(root)
            local = Path(temp)/'copy'; shutil.copytree(root/'inputs', local)
            poison = {name: types.ModuleType(name) for name in ('check', 'fixture', 'build_soc')}
            before = list(sys.path)
            with patch.dict(sys.modules, poison):
                c = r.checker(root, review, local)
                self.assertEqual(Path(c.__file__), local/'check.py')
                for name, value in poison.items(): self.assertIs(sys.modules[name], value)
            self.assertEqual(sys.path, before)
            (local/'support/contract.py').write_text('raise RuntimeError("never imported")\n')
            with patch.object(r, 'load') as load, self.assertRaises(ValueError):
                r.checker(root, review, local)
            load.assert_not_called()

    def test_missing_dependency_pin_and_artifact_conflict_rejected(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(r, 'software_path', side_effect=Path):
            root = Path(temp); sw, _ = fake_build(root)
            path = str(root/'inputs/support/contract.py')
            pins = r.b.read(root/'source-pins.json'); pins.pop(path)
            (root/'source-pins.json').unlink(); r.b.save(root/'source-pins.json', pins)
            sw['source_pins_sha256'] = r.b.sha(root/'source-pins.json')
            sw['artifacts'].pop(path)
            (root/'build.json').unlink(); r.b.save(root/'build.json', sw)
            with self.assertRaisesRegex(ValueError, 'Unpinned checker'): r.software_receipt(root, r.b.sha(root/'build.json'))
            sw['artifacts'][str(root/'inputs/check.py')] = '0'*64
            (root/'build.json').unlink(); r.b.save(root/'build.json', sw)
            with self.assertRaisesRegex(ValueError, 'Conflicting pin'): r.software_receipt(root, r.b.sha(root/'build.json'))

    def test_checker_dependency_paths_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); sw, _ = fake_build(root)
            for name in ('../outside', '/absolute', './check.py', 'support//contract.py', ''):
                altered = copy.deepcopy(sw); altered['checker_dependencies'][name] = 'a'*64
                with self.subTest(name=name), self.assertRaises(ValueError): r.checker_files(altered, root/'inputs')
            altered = copy.deepcopy(sw); altered['checker_dependencies'].pop('fixture.py')
            with self.assertRaises(ValueError): r.checker_files(altered, root/'inputs')
            p = root/'inputs/support/contract.py'; saved = p.read_bytes(); p.unlink()
            outside = root/'external.py'; outside.write_bytes(saved); p.symlink_to(outside)
            with self.assertRaises(ValueError): r.checker_files(sw, root/'inputs')

    def test_perf_work_is_exact_not_a_receipt_selected_weaker_baseline(self):
        self.assertIn('akv_experimental_resident_pv_prepare', r.ENTRY_NAMES)
        self.assertNotIn('resident_pv_prepare', r.ENTRY_NAMES)
        r.checked_work(self.sw)
        for key, value in (('calls', 3), ('output_values', 256), ('legacy_commands', 481),
                           ('legacy_per_call', [237, 4, 237, 4]), ('resident_commands', 11)):
            altered = copy.deepcopy(self.sw); altered['expected_work'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): r.checked_work(altered)
        for name in (r.ENTRY, 'akv_decode_execute'):
            altered = copy.deepcopy(self.sw); altered['expected_work']['actual_entries'][name] -= 1
            with self.assertRaises(ValueError): r.checked_work(altered)
        for key, value in (('schema', 'stage3'), ('state', 'FAIL'), ('kind', 'smoke'), ('post_pins_match', False)):
            altered = dict(self.sw, **{key: value})
            with self.assertRaises(ValueError): r.checked_work(altered)
        for key in ('calls', 'output_values', 'legacy_commands', 'resident_commands'):
            altered = copy.deepcopy(self.sw); altered['kind'] = 'functional'; altered['expected_work'][key] = True
            with self.assertRaises(ValueError): r.checked_work(altered)

    def test_functional_counts_are_explicit_and_consistent_not_perf_denominators(self):
        sw = software(); sw['kind'] = 'functional'
        sw['expected_work'].update(calls=2, output_values=128, legacy_commands=12,
                                  legacy_per_call=[6, 6], resident_commands=4)
        rows = [r.perf_entries(False), r.perf_entries(True)]
        sw['expected_work']['actual_entries'] = {k: sum(row[k] for row in rows) for k in r.ENTRY_NAMES}
        proof = sdk_proof(sw); proof['actual_entries']['per_call'] = rows
        r.checked_work(sw); r.checked_sdk(proof, sw)
        sw['expected_work']['legacy_per_call'] = [6]
        with self.assertRaises(ValueError): r.checked_work(sw)

    def test_exact_recipes_no_fallback_or_protocol_exception_switch(self):
        out = Path('/tmp/recipe-only'); software_dir = Path('/frozen/build'); python = '/usr/bin/python3.9'
        commands = r.recipes(out, self.soc, self.sw, software_dir, python)
        self.assertEqual(commands['image_contract'], ['/usr/bin/bash', str(out/'inputs/image-check.sh'),
            str(Path(self.soc['simv']).parent), self.sw['elf'], 'akv_v2'])
        self.assertEqual(commands['simulation'][:6], [self.soc['simv'], '-no_save', '-l',
            str(out/'work/run.vcs.log'), '+PRELOAD='+self.sw['elf'], '+TESTCASE=stage4_features_full_call'])
        for arg in (*r.REQUIRED_PLUSARGS, '+NO_FSDB', '+NO_INSTR_TRACE',
                    '+COMMIT_TRACE='+str(out/'work/commit.csv'), '+VECTOR_TRACE='+str(out/'work/vector_trace.csv')):
            self.assertEqual(commands['simulation'].count(arg), 1)
        self.assertEqual(commands['sdk'], [python, '-B', str(out/'inputs/checker/check.py'),
            '--build', str(software_dir), '--log', str(out/'work/run.vcs.log'),
            '--vector', str(out/'work/vector_trace.csv'), '--commit', str(out/'work/commit.csv')])
        for flag in ('--require-events', '--require-backend', '--require-axi', '--require-axi-write'):
            self.assertIn(flag, commands['protocol'])
        self.assertFalse(any('allow' in x or 'ignore' in x for x in commands['protocol']))
        self.assertFalse(any(x == '+FSDB' or 'QBS_PERF' in x for x in commands['simulation']))

    def test_only_accepted_image_and_direct_signoff_paths(self):
        with patch.object(r.b, 'checked_build') as build:
            with self.assertRaisesRegex(ValueError, 'Only accepted Stage3 BUILD02'):
                r.collect(r.OUT/'stage3_soc_other', r.OUT/'stage4_features_full_call_build_test', 'a'*64)
            build.assert_not_called()
        for bad in (r.OUT/'stage3_attention_sdk_vcs_other', Path('/tmp/stage4_resident_features_vcs_x')):
            with self.assertRaises(ValueError): r.output_path(bad)
        for bad in (r.OUT/'stage4_projection_chain_build_other', Path('/tmp/stage4_features_full_call_build_x')):
            with self.assertRaises(ValueError): r.software_path(bad)

    def test_snapshot_closure_excludes_unowned_files_and_live_hardware(self):
        layout = r.source_layout(r.SOC, Path('/frozen'), self.sw)
        expected = set(r.OWN) | {'build_soc.py', *r.b.HELPERS, 'image-check.sh'} | {
            'checker/'+name for name in self.sw['checker_dependencies']}
        self.assertEqual({name for name in layout if not name.startswith('verification/')}, expected)
        for name in ('README.md', 'build.py', 'main.c', 'test_full_call.py'):
            self.assertNotIn(name, layout)
        self.assertEqual(r.b.sha(layout['build_soc.py']), r.BUILDER_SHA)
        self.assertEqual(r.b.sha(layout['image-check.sh']), r.IMAGE_CHECK_SHA)

    def test_environment_allowlist_no_cwd_library_or_caller_override(self):
        source = dict(VCS_HOME='/vcs', VCS_ARCH_OVERRIDE='linux', SNPSLMD_LICENSE_FILE='port@host',
            HOME='/home/test', LD_LIBRARY_PATH=':/one:/one::/two:', SECRET='never forwarded',
            LLAMA_ATTN_SIM_L2_BYTES='1', PYTHONPATH='/live/checker')
        with patch.object(r.b, 'read', return_value={'environment': source}):
            env = r.environment(r.SOC, Path('/tmp/features'))
        self.assertNotIn('SECRET', env); self.assertNotIn('LLAMA_ATTN_SIM_L2_BYTES', env)
        self.assertEqual(env['LD_LIBRARY_PATH'], '/vcs/linux64/lib:/one:/two')
        self.assertEqual(env['PYTHONPATH'], '/tmp/features/inputs/verification')
        self.assertEqual(env['READELF'], '/usr/bin/readelf')
        for key in ('VCS_HOME', 'SNPSLMD_LICENSE_FILE', 'HOME'):
            altered = dict(source); altered[key] = ''
            with patch.object(r.b, 'read', return_value={'environment': altered}), self.assertRaises(ValueError):
                r.environment(r.SOC, Path('/tmp/features'))
        source['HOME'] = '/home/test\nwrong'
        with patch.object(r.b, 'read', return_value={'environment': source}), self.assertRaises(ValueError):
            r.environment(r.SOC, Path('/tmp/features'))

    def test_fixed_bounds_and_no_automatic_service_launch(self):
        self.assertEqual((r.SIM_SECONDS, r.CHECK_SECONDS, r.PROTOCOL_SECONDS, r.SERVICE_SECONDS),
                         (5400, 300, 900, 7200))
        self.assertLessEqual(sum(seconds for _, _, seconds in r.STEPS), r.SERVICE_SECONDS)
        self.assertEqual(r.OWN, ('vcs_run.py', 'test_vcs_run.py'))
        source = (HERE/'vcs_run.py').read_text()
        for unwanted in ('subprocess.Popen', 'sys.path.insert', 'import check', 'start_new_session'):
            self.assertNotIn(unwanted, source)

    def test_loader_evidence_required_and_libraries_pinned(self):
        library = Path('/usr/bin/python3').resolve()
        self.assertEqual(r.runtime_libraries('libtest => '+str(library)+' (0x123)\n'),
                         {str(library): r.b.sha(library)})
        for invalid in ('', 'libtest => not found\n', '/no/such/library (0x1)\n'):
            with self.assertRaises((ValueError, FileNotFoundError)): r.runtime_libraries(invalid)

    def test_direct_service_review_and_single_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); (out/'work').mkdir(); (out/'source-pins.json').write_text('{}')
            review = r.b.sha(out/'source-pins.json')
            s = dict(python='/usr/bin/python3.9', environment={'LC_ALL': 'C'})
            with patch.object(r, 'verify_prepared', return_value=(s,)):
                argv = r.service_command(out, review)
                self.assertEqual(argv[0], '/usr/bin/systemd-run')
                self.assertIn('--property=KillMode=control-group', argv)
                self.assertIn('--property=RuntimeMaxSec=7200', argv)
                self.assertIn('--property=StandardOutput=append:'+str(out/'service.stdout.log'), argv)
                self.assertIn(str(out/'inputs/vcs_run.py'), argv)
                self.assertIn('--parent-reviewed', argv)
                self.assertEqual(argv[-2:], ['--review-sha256', review])
                self.assertFalse(any(x in argv for x in ('nohup', 'bash', 'sh', '&')))
                with self.assertRaises(ValueError): r.service_command(out, 'wrong')
                for name in ('attempt.json', 'owner.json', 'result.json', 'work/stale'):
                    p = out/name; p.write_text('{}')
                    with self.assertRaises(ValueError): r.service_command(out, review)
                    p.unlink()

    def test_live_worker_and_unreviewed_run_rejected_before_claim(self):
        out = r.OUT/'stage4_resident_features_vcs_unit_only'
        with patch.object(r.b, 'claim_attempt') as claim:
            for reviewed in (False, True):
                with self.assertRaisesRegex(ValueError, 'Parent-reviewed frozen worker'):
                    r.run(out, 'not-a-review', reviewed)
            claim.assert_not_called()

    def test_sdk_result_mutations_never_weaken_entries_work_or_scope(self):
        proof = sdk_proof(self.sw); r.checked_sdk(proof, self.sw)
        for path, value in ((('state',), 'PASS'), (('scope',), 'wrong'), (('protocol_checked',), True),
            (('post_image_checked',), True), (('performance_acceptance',), True),
            (('whole_model',), True), (('numerical', 'fflags_checked'), False),
            (('numerical', 'vcsr_vstart_checked'), False), (('numerical', 'fcsr'), []),
            (('numerical', 'calls'), 3), (('numerical', 'output_values'), 256), (('numerical', 'bitexact'), False),
            (('legacy_work', 'commands'), 481), (('legacy_work', 'per_call'), [237, 4, 237, 4]),
            (('resident_work',), [{}]*11), (('vector_work', 'resident_commands'), 11),
            (('actual_entries', 'calls'), 3), (('actual_entries', 'rotation_branch_body_checked'), False),
            (('actual_entries', 'per_call'), []),
            (('numerical', 'timing', 'full_call_cycles'), [90]*4),
            (('numerical', 'timing', 'final_drain_cycles'), [0]*4),
            (('numerical', 'timing', 'full_call_speedup'), 2)):
            altered = copy.deepcopy(proof); node = altered
            for key in path[:-1]: node = node[key]
            node[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError): r.checked_sdk(altered, self.sw)
        for key in proof:
            altered = copy.deepcopy(proof); altered.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError): r.checked_sdk(altered, self.sw)
        for name in r.ENTRY_NAMES:
            altered = copy.deepcopy(proof); altered['actual_entries']['per_call'][0][name] += 1
            with self.assertRaises(ValueError): r.checked_sdk(altered, self.sw)
        altered = copy.deepcopy(proof)
        altered['actual_entries']['per_call'] = [r.perf_entries(on) for on in (False, True, False, True)]
        with self.assertRaisesRegex(ValueError, 'ABBA'): r.checked_sdk(altered, self.sw)

    def test_protocol_binds_image_elf_logs_and_requires_zero_exceptions(self):
        with tempfile.TemporaryDirectory() as temp:
            log, vector = Path(temp)/'log', Path(temp)/'vector'
            log.write_text('identity fixture only\n'); vector.write_text('identity fixture only\n')
            proof = dict(status='PASS', issues=[], elf_sha256=self.sw['elf_sha256'],
                simv_sha256=r.b.sha(self.soc['simv']),
                sim_image_sha256={p: h for p, h in self.soc['image_pins'].items()
                                  if p == self.soc['simv'] or p.endswith('.so')},
                log_sha256=r.b.sha(log), vector_trace_sha256=r.b.sha(vector),
                contract_counts=dict(exceptions=0, protocol_errors=0, outstanding=0))
            r.checked_protocol(proof, self.soc, self.sw, log, vector)
            for key, value in (('status', 'FAIL'), ('issues', ['failure']), ('elf_sha256', 'bad'),
                ('simv_sha256', 'bad'), ('sim_image_sha256', {}), ('log_sha256', 'bad'),
                ('vector_trace_sha256', 'bad'), ('contract_counts', {})):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    r.checked_protocol(dict(proof, **{key: value}), self.soc, self.sw, log, vector)
            for key in proof['contract_counts']:
                for value in (1, None, False):
                    altered = copy.deepcopy(proof); altered['contract_counts'][key] = value
                    with self.assertRaises(ValueError): r.checked_protocol(altered, self.soc, self.sw, log, vector)

    def test_executed_argv_cwd_timeouts_review_and_direct_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); (out/'work').mkdir(); (out/'source-pins.json').write_text('{}')
            s = dict(commands={key: [key, '+exact-input'] for key, _, _ in r.STEPS})
            owner = dict(unit=r.service_unit(out), cgroup='/user.slice/'+r.service_unit(out), main_pid=42, owner_pid=42)
            r.b.save(out/'owner.json', owner)
            attempt = dict(review_sha256=r.b.sha(out/'source-pins.json'), **owner)
            r.b.save(out/'attempt.json', attempt)
            originals = {}
            for command, name, seconds in r.STEPS:
                p = out/'work'/(name+'.command.json')
                originals[p] = dict(argv=s['commands'][command], cwd=str(out/'work'), timeout_seconds=seconds)
                r.b.save(p, originals[p])
            r.execution_receipts(out, s)
            for p, original in originals.items():
                for key, value in (('argv', ['wrong-input']), ('cwd', '/wrong'), ('timeout_seconds', 1)):
                    p.unlink(); r.b.save(p, dict(original, **{key: value}))
                    with self.assertRaises(ValueError): r.execution_receipts(out, s)
                p.unlink()
                with self.assertRaises(FileNotFoundError): r.execution_receipts(out, s)
                r.b.save(p, original)
            for key, value in (('unit', 'wrong.service'), ('cgroup', '/other.service'), ('main_pid', 99), ('owner_pid', 1)):
                altered = dict(owner, **{key: value})
                (out/'owner.json').unlink(); r.b.save(out/'owner.json', altered)
                (out/'attempt.json').unlink(); r.b.save(out/'attempt.json', dict(attempt, **altered))
                with self.subTest(key=key), self.assertRaises(ValueError): r.execution_receipts(out, s)
            (out/'owner.json').unlink(); r.b.save(out/'owner.json', owner)
            (out/'attempt.json').unlink(); r.b.save(out/'attempt.json', dict(attempt, review_sha256='wrong'))
            with self.assertRaises(ValueError): r.execution_receipts(out, s)

    def test_unique_image_evidence_and_success_marker(self):
        valid = 'sim_akv_enabled=1\nsim_akv_v2_enabled=1\nsim_l2_bytes=16777216\n'
        r.checked_image_log(valid)
        for bad in (valid+valid, valid.replace('v2_enabled=1', 'v2_enabled=0'), valid.replace('16777216', '2097152')):
            with self.assertRaises(ValueError): r.checked_image_log(bad)
        valid = 'Core Test *** SUCCESS ***\n'; r.successful_log(valid)
        for bad in ('', valid+valid, valid+'Fatal: broken\n', valid+'FAILED\n'):
            with self.assertRaises(ValueError): r.successful_log(bad)

    def test_pin_merges_do_not_overwrite_disagreement(self):
        pins = {'same': 'digest'}; r.merge(pins, {'same': 'digest', 'another': 'value'})
        self.assertEqual(pins, {'same': 'digest', 'another': 'value'})
        with self.assertRaises(ValueError): r.merge(pins, {'same': 'changed'})


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--receipt-dir', type=Path)
    args, remaining = parser.parse_known_args()
    if args.receipt_dir is None:
        unittest.main(argv=[sys.argv[0], *remaining]); return 0
    out = r.b.output_path(args.receipt_dir, 'stage4_features_full_call_runner_host_')
    out.mkdir()
    pins = {str(HERE/name): r.b.sha(HERE/name) for name in r.OWN}
    pins[str(r.builder)] = r.BUILDER_SHA
    r.b.save(out/'source-pins.json', pins)
    r.b.save(out/'command.json', dict(argv=sys.argv, cwd=str(Path.cwd()), host_only=True))
    start = time.monotonic()
    with (out/'tests.log').open('x') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(RunnerTests))
    r.b.verify(pins)
    report = dict(state='HOST_RUNNER_PASS' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        elapsed_seconds=time.monotonic()-start, source_pins_sha256=r.b.sha(out/'source-pins.json'),
        simulation_started=False, firmware_built=False, numerical_claim=False,
        artifacts=r.b.files(out))
    r.b.save(out/'result.json', report)
    print(json.dumps(report, indent=2))
    return int(not result.wasSuccessful())


if __name__ == '__main__': raise SystemExit(main())
