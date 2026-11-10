#!/usr/bin/env python3
"""Bounded host recipe/identity checks; no simulator or numerical replay."""
import copy
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sdk_functional_run_test', HERE/'run.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
SOC = r.OUT/'stage3_soc_20261110_02'


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = r.b.read(SOC/'build.json')
        cls.sw = r.checker().build_receipt(r.SOFTWARE)
        cls.old = r.legacy()

    def test_exact_stage3_and_firmware_contract(self):
        soc, sw, pins, _ = r.collect(SOC)
        self.assertEqual(soc['configuration'], r.b.CONFIG)
        self.assertEqual(soc['image_contract'], r.b.IMAGE_CONTRACT)
        self.assertEqual(soc['cpu_overlay'], r.b.CPU_OVERLAY)
        self.assertEqual(sw['elf_sha256'], r.ELF_SHA)
        self.assertEqual(sw['host_tests'], 18)
        helper_paths = {Path(p).name for p in sw['artifacts']
                        if Path(p).parent == r.SOFTWARE/'inputs/fixture'}
        self.assertEqual(helper_paths, {'README.md', 'build.py', 'check.py', 'fixture.py',
                                       'main.c', 'test_sdk.py', 'test_flags_v2.py', 'flags-v2-contract.json'})
        self.assertEqual(pins[str(r.SOFTWARE/'build.json')], r.BUILD_SHA)
        self.assertEqual(pins[str(r.SOFTWARE/'source-pins.json')], r.FW_PINS_SHA)
        self.assertEqual([x['expected_fcsr'] for x in sw['fixture']['results']], [3, 11, 3])
        self.assertEqual(set(sw['fixture']['counter_semantics']), {'PV', 'PV_PREP'})
        self.assertEqual(sw['fixture']['results'][2]['expf_samples'],
                         [dict(input=0, output=0x3f800000, fflags=0)]*6)

    def test_import_isolation_ignores_old_cached_fixture(self):
        poison = types.ModuleType('fixture')
        poison.__file__ = str(r.SHARED/'full_call_sdk/fixture.py')
        before = list(sys.path)
        with patch.dict(sys.modules, {'fixture': poison}):
            c = r.checker()
            self.assertIsNot(c.f, poison)
            self.assertEqual(Path(c.f.__file__), r.SOFTWARE/'inputs/fixture/fixture.py')
            self.assertEqual(r.b.sha(c.f.__file__), r.CHECKER['fixture.py'])
            self.assertIs(sys.modules['fixture'], poison)
        self.assertEqual(sys.path, before)

    def test_frozen_checker_copy_rejects_wrong_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            for name in r.CHECKER:
                shutil.copyfile(r.SOFTWARE/'inputs/fixture'/name, local/name)
            c = r.checker(local)
            self.assertEqual(Path(c.f.__file__), local/'fixture.py')
            (local/'fixture.py').write_text('raise RuntimeError("must not import")\n')
            with self.assertRaisesRegex(ValueError, 'Identity drift'):
                r.checker(local)

    def test_exact_recipes_and_all_trace_inputs(self):
        out = Path('/tmp/sdk-recipe-only')
        python = '/usr/bin/python3.9'
        old = self.old.recipes(out, self.soc, self.sw, python)
        actual = r.recipes(out, self.soc, self.sw, python, self.old)
        self.assertEqual(actual['image_contract'], old['image_contract'])
        self.assertEqual(actual['protocol'], old['protocol'])
        expected = list(old['simulation'])
        expected[expected.index('+TESTCASE=resident_pv_soc_smoke')] = '+TESTCASE=resident_attention_sdk'
        expected.append('+RESIDENT_QK_PERF')
        self.assertEqual(actual['simulation'], expected)
        for arg in ('+NO_FSDB', '+AKV_PERF', '+AKV_SUMMARY', '+RESIDENT_PV_PERF',
                    '+RESIDENT_QK_PERF', '+RESIDENT_PV_WATCHDOG',
                    '+VECTOR_TRACE='+str(out/'work/vector_trace.csv'),
                    '+COMMIT_TRACE='+str(out/'work/commit.csv')):
            self.assertEqual(actual['simulation'].count(arg), 1)
        self.assertFalse(any('FFS' in x or x == '+FSDB' for x in actual['simulation']))
        self.assertEqual(actual['sdk'], [python, '-B', str(out/'inputs/checker/check.py'),
            '--build', str(r.SOFTWARE), '--log', str(out/'work/run.vcs.log'),
            '--vector', str(out/'work/vector_trace.csv'), '--commit', str(out/'work/commit.csv')])
        self.assertEqual((r.SIM_SECONDS, r.SDK_SECONDS, r.PROTOCOL_SECONDS), (5400, 300, 900))
        self.assertGreaterEqual(r.SERVICE_SECONDS, sum(x[2] for x in r.STEPS))

    def test_environment_allowlist_and_no_implicit_cwd_library(self):
        source = dict(VCS_HOME='/vcs', VCS_ARCH_OVERRIDE='linux', SNPSLMD_LICENSE_FILE='port@host',
            HOME='/home/test', LD_LIBRARY_PATH=':/one:/one::/two:', SECRET='not forwarded')
        with patch.object(r.b, 'read', return_value={'environment': source}):
            env = r.environment(SOC, Path('/tmp/sdk'))
        self.assertNotIn('SECRET', env)
        self.assertEqual(env['LD_LIBRARY_PATH'], '/vcs/linux64/lib:/one:/two')
        self.assertEqual(env['PYTHONPATH'], '/tmp/sdk/inputs/verification')
        source['VCS_HOME'] = '/vcs\nwrong'
        with patch.object(r.b, 'read', return_value={'environment': source}), self.assertRaises(ValueError):
            r.environment(SOC, Path('/tmp/sdk'))

    def test_direct_service_review_and_single_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'work').mkdir()
            (out/'source-pins.json').write_text('{}')
            review = r.b.sha(out/'source-pins.json')
            s = dict(python='/usr/bin/python3.9', environment={'LC_ALL': 'C'})
            with patch.object(r, 'verify_prepared', return_value=(s,)):
                command = r.service_command(out, review)
                self.assertEqual(command[0], '/usr/bin/systemd-run')
                self.assertIn('--property=KillMode=control-group', command)
                self.assertIn('--property=RuntimeMaxSec=7200', command)
                self.assertIn(str(out/'inputs/run.py'), command)
                self.assertIn('--parent-reviewed', command)
                self.assertEqual(command[-2:], ['--review-sha256', review])
                self.assertFalse(any(x in command for x in ('nohup', 'bash', 'sh', '&')))
                with self.assertRaises(ValueError): r.service_command(out, 'wrong')
                for name in ('attempt.json', 'owner.json', 'result.json', 'work/stale'):
                    file = out/name
                    file.write_text('{}')
                    with self.assertRaises(ValueError): r.service_command(out, review)
                    file.unlink()

    def test_live_or_unreviewed_worker_is_rejected_before_claim(self):
        out = r.OUT/'stage3_attention_sdk_vcs_unit_only'
        with patch.object(r.b, 'claim_attempt') as claim:
            for reviewed in (False, True):
                with self.assertRaisesRegex(ValueError, 'Parent-reviewed frozen worker'):
                    r.run(out, 'not-a-review', reviewed)
            claim.assert_not_called()
        for bad in (r.OUT/'stage3_attention_vcs_wrong_prefix', Path('/tmp/stage3_attention_sdk_vcs_x')):
            with self.assertRaises(ValueError): r.output_path(bad)

    def test_checker_result_contract_mutations(self):
        result = dict(protocol_checked=False, performance_acceptance=False, scope=self.sw['scope'],
            numerical=dict(calls=3, output_values=1088, bitexact=True, fflags=[3,11,3], performance_baseline=False),
            legacy_work=dict(commands=247, per_call=[237,4,6]), resident_work=[{}]*22, vector_work=[{}]*22,
            actual_entries=dict(akv_decode_execute=6, akv_experimental_attention_execute_v2_native=4))
        r.checked_sdk(result, self.sw)
        for path, value in ((('protocol_checked',), True), (('scope',), 'wrong'),
            (('numerical','bitexact'), False), (('numerical','fflags'), [3,3,3]),
            (('numerical','output_values'), 1024), (('numerical','performance_baseline'), True),
            (('legacy_work','commands'), 246), (('legacy_work','per_call'), [237,4,3]),
            (('resident_work',), [{}]*21), (('vector_work',), [{}]*23),
            (('actual_entries','akv_experimental_attention_execute_v2_native'), 3)):
            altered = copy.deepcopy(result)
            target = altered
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError): r.checked_sdk(altered, self.sw)

    def test_independent_protocol_and_zero_exceptions_required(self):
        old = types.SimpleNamespace(check_protocol=lambda *args: None)
        proof = dict(contract_counts=dict(exceptions=0, protocol_errors=0, outstanding=0))
        r.checked_protocol(proof, {}, {}, Path('log'), Path('vector'), old)
        for key in proof['contract_counts']:
            altered = copy.deepcopy(proof)
            altered['contract_counts'][key] = 1
            with self.assertRaises(ValueError): r.checked_protocol(altered, {}, {}, Path('l'), Path('v'), old)
        with patch.object(old, 'check_protocol', side_effect=ValueError('image/ELF proof mismatch')):
            with self.assertRaisesRegex(ValueError, 'image/ELF proof mismatch'):
                r.checked_protocol(proof, {}, {}, Path('l'), Path('v'), old)

    def test_executed_commands_cwd_timeouts_and_owner_are_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'work').mkdir()
            (out/'source-pins.json').write_text('{}')
            s = dict(commands={key: [key, '+exact-input'] for key, _, _ in r.STEPS})
            owner = dict(unit=r.service_unit(out), cgroup='/user.slice/'+r.service_unit(out),
                         main_pid=42, owner_pid=42)
            r.b.save(out/'owner.json', owner)
            r.b.save(out/'attempt.json', dict(review_sha256=r.b.sha(out/'source-pins.json'), **owner))
            originals = {}
            for command, name, seconds in r.STEPS:
                file = out/'work'/(name+'.command.json')
                originals[file] = dict(argv=s['commands'][command], cwd=str(out/'work'), timeout_seconds=seconds)
                r.b.save(file, originals[file])
            r.execution_receipts(out, s)
            for file, original in originals.items():
                for key, value in (('argv', ['wrong-input']), ('cwd', '/wrong'), ('timeout_seconds', 1)):
                    file.unlink()
                    r.b.save(file, dict(original, **{key: value}))
                    with self.assertRaises(ValueError): r.execution_receipts(out, s)
                file.unlink()
                r.b.save(file, original)
            (out/'owner.json').unlink()
            r.b.save(out/'owner.json', dict(owner, main_pid=99))
            with self.assertRaises(ValueError): r.execution_receipts(out, s)

    def test_real_protocol_receipt_rejects_each_identity_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            log, vector = local/'log', local/'vector'
            log.write_text('receipt-only, not a simulated result\n')
            vector.write_text('receipt-only, not a simulated trace\n')
            proof = dict(status='PASS', issues=[], elf_sha256=self.sw['elf_sha256'],
                simv_sha256=r.b.sha(self.soc['simv']),
                sim_image_sha256={p: h for p, h in self.soc['image_pins'].items()
                                  if p == self.soc['simv'] or p.endswith('.so')},
                log_sha256=r.b.sha(log), vector_trace_sha256=r.b.sha(vector),
                contract_counts=dict(exceptions=0, protocol_errors=0, outstanding=0))
            r.checked_protocol(proof, self.soc, self.sw, log, vector, self.old)
            for key, value in (('status', 'FAIL'), ('issues', ['failure']), ('elf_sha256', 'bad'),
                    ('simv_sha256', 'bad'), ('sim_image_sha256', {}), ('log_sha256', 'bad'),
                    ('vector_trace_sha256', 'bad'), ('contract_counts', {})):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    r.checked_protocol(dict(proof, **{key: value}), self.soc, self.sw, log, vector, self.old)


if __name__ == '__main__':
    unittest.main()
