import json
import contextlib
import io
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import prepare
import run

HERE = Path(__file__).resolve().parent
PREPARED = HERE / 'prepared'


class Ports(unittest.TestCase):
    def test_all_pins_and_adaptations(self):
        data = prepare.check(PREPARED)
        self.assertEqual(len(data['cases']), 12)
        self.assertEqual(sum(c['include_combined'] for c in data['cases']), 6)
        for case in data['cases'][:6]:
            directory = PREPARED / case['id']
            original = directory / 'original'
            for name, digest in case['original_case']['scenario_sources'].items():
                self.assertEqual(prepare.sha(original / name), digest)
            self.assertEqual((directory / 'case.c').read_text(), prepare.adapt(
                (original / 'scenario.c').read_text(), case['id']))

    def test_adapter_fails_closed(self):
        source = (PREPARED / 'wholemove/original/scenario.c').read_text()
        with self.assertRaises(ValueError):
            prepare.adapt(source.replace('syscall3(94,2,0,0)', 'syscall3(94,3,0,0)'), 'test')

    def test_reduction_selected_fixture(self):
        source = (PREPARED / 'reduction_fflags/original/fixtures.h').read_text()
        values = re.findall(r'\{UINT64_C\((0x[0-9a-f]+)\),(\d+)\}', source)
        self.assertEqual(len(values), 6720)
        index = 3360 + 3 * 420 + ((4 * 4 + 3) * 5 + 0) * 3 + 0
        self.assertEqual(tuple(int(s, 0) for s in values[index]), (0x7fc00000, 16))
        # mask 0x24 activates elements 2 and 5, whose signs differ.
        self.assertEqual([i for i in range(8) if (0x24 >> i) & 1], [2, 5])

    def test_maskslide_original_target(self):
        source = (PREPARED / 'maskslide/original/operations.S').read_text()
        body = source.split('op_16:\n')[1].split('.global')[0]
        self.assertIn('csrw vstart,a7\nvslidedown.vi v24,v8,0,v0.t', body)
        self.assertIn('vle16.v v8,(a0)', body)
        self.assertIn('vle16.v v24,(a2)', body)

    def test_m8_retains_zero_vl(self):
        code = (PREPARED / 'm8widen/case.c').read_text()
        self.assertIn('unsigned lengths[]={0};', code)
        self.assertIn('op<1', code)
        asm = (PREPARED / 'm8widen/original/scenario.S').read_text()
        self.assertIn('vfwredosum.vs v24,v8,v16,v0.t', asm)
        self.assertIn('vsetvli t0,a3,e32,m8,tu,mu', asm)

    def test_wholemove_byte_oracle(self):
        # Original mode1 uses architectural e16 despite byte-loaded source EEW.
        start, width, size = 1, 2, 128
        expected = [91 if i < start * width else (i * 37 + 3) & 255 for i in range(size)]
        self.assertEqual(expected[:3], [91, 91, 77])
        self.assertEqual((1 * 37 + 3) & 255, 40)
        asm = (PREPARED / 'wholemove/original/whole.S').read_text()
        self.assertIn('vsetivli zero,7,e16,m2,tu,mu', asm)
        self.assertIn('vmv1r.v v24,v8', asm)

    def test_supplement_is_not_original_identity(self):
        source = (HERE / 'slide1up_prestart.c').read_text()
        self.assertIn('not an original Linux trial', source)
        self.assertIn('source[i] = 1000 + i; result[i] = 91;', source)
        self.assertIn('result[0] != 91 || result[1] != 1000', source)

    def test_exit_encodings_are_backend_specific(self):
        source = (HERE / 'startup.S').read_text().split('replay_exit:\n')[1]
        htif, soc = source.split('#else', 1)
        self.assertIn('slli a0, a0, 1', htif)
        self.assertIn('ori a0, a0, 1', htif)
        self.assertNotIn('slli a0', soc)
        self.assertIn('li t0, 0xd0000000', soc)

    def test_unexpected_trap_fails_not_skips(self):
        source = (HERE / 'startup.S').read_text()
        self.assertIn('csrr a0, mcause', source)
        self.assertIn('csrr a1, mepc', source)
        self.assertIn('csrr a2, mtval', source)
        self.assertIn('call replay_trap\n    li a0, 127', source)

    def test_gather_identities_are_separate(self):
        original = (PREPARED / 'gather_original/original/operations.S').read_text()
        generic = (PREPARED / 'gather_prestart/original/rvv_repro_gather_restart.S').read_text()
        self.assertIn('vrgather.vv v24,v8,v16,v0.t', original)
        self.assertIn('vrgather.vx v24,v8,t3,v0.t', generic)
        data = json.loads((PREPARED / 'provenance.json').read_text())
        selected = {c['id']: c for c in data['cases']}
        for name in ('gather_original', 'gather_prestart'):
            self.assertFalse(selected[name]['include_combined'])
        self.assertFalse(selected['gather_prestart']['original_case']['board_tested'])

    def test_extended_nonzero_width_and_dependency(self):
        source = (HERE / 'extensions.c').read_text()
        self.assertIn('trial < 2 ? 33 : 65', source)
        self.assertIn('mask[0] = mask[4] = 2', source)
        self.assertIn('source[33] = 0xff800000', source)
        self.assertIn('op ? m8widen_op_1 : m8widen_op_0', source)
        asm = (HERE / 'extensions.S').read_text()
        instructions = [line.strip() for line in asm.splitlines()
                        if line.strip() and not line.lstrip().startswith('#')]
        index = instructions.index('vmv2r.v v24,v8')
        self.assertEqual(instructions[index+1], 'vmv2r.v v16,v24')


class Runner(unittest.TestCase):
    def test_bounded_execution_jobs(self):
        argv = ['run', '--image', '/tmp/image', '--programs', '/tmp/programs',
                '--out', '/tmp/results']
        self.assertEqual(run.parse_args(argv).jobs, 4)
        for jobs in range(1, 9):
            self.assertEqual(run.parse_args(argv + ['--jobs', str(jobs)]).jobs, jobs)
        for invalid in ('0', '-1', '9', '100', '1.5', 'auto'):
            with self.subTest(invalid=invalid), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    run.parse_args(argv + ['--jobs', invalid])
                self.assertEqual(error.exception.code, 2)

    def test_clean_environment(self):
        with patch.dict(os.environ, {'MAKEFLAGS': '-e', 'PATH': '/ZCC/bin',
                                     'verify_extra_sources': 'bad.sv', 'HOME': '/home/test'}):
            env = run.environment()
        self.assertEqual(env['HOME'], '/home/test')
        self.assertNotIn('ZCC', env['PATH'])
        self.assertNotIn('MAKEFLAGS', env)
        self.assertNotIn('verify_extra_sources', env)

    def test_snapshot_rejects_writable_and_changed_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'sources'
            source.mkdir()
            file = source / 'example.sv'
            file.write_text('unchanged')
            prepare.save(root / 'snapshot.json', dict(root=str(source), state='SEALED',
                         settings=run.SETTINGS, files={'example.sv': prepare.sha(file)}))
            with self.assertRaisesRegex(ValueError, 'writable'):
                run.sealed(root)
            file.chmod(0o444)
            self.assertEqual(run.sealed(root), source)
            file.chmod(0o644)
            file.write_text('changed')
            file.chmod(0o444)
            with self.assertRaisesRegex(ValueError, 'drift'):
                run.sealed(root)

    def test_custom_extensions_preserved(self):
        for setting in ('qbs=1', 'akv=1', 'akv_v2=1', 'vlen=1024', 'nr_lanes=4'):
            self.assertIn(setting, run.SETTINGS)
        self.assertIn('no_fsdb=1', run.SETTINGS)

    def test_reject_skip_and_missing_counts(self):
        entry = {'pass_markers': ['BOARD_REPLAY_PASS', prepare.ORACLE_MARKERS['m8widen']]}
        self.assertFalse(run.oracle_complete(entry, 'BOARD_REPLAY_PASS'))
        log = '\n'.join(entry['pass_markers'])
        self.assertTrue(run.oracle_complete(entry, log))
        self.assertFalse(run.oracle_complete(entry, log + '\nSKIP'))


if __name__ == '__main__':
    unittest.main()
