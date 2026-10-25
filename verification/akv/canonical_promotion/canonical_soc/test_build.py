"""Host-only policy tests. No make, Bender, compiler or simulator invocation."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build as b


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.host-test-', dir=b.HERE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.root.mkdir()

    def put(self, relative, text='source'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def promotion(self):
        rows = []
        for i in range(19):
            path = self.put('promoted/' + str(i), 'after' + str(i))
            rows.append(dict(target=path.relative_to(self.root).as_posix(), after_sha256=b.digest(path)))
        tool = self.put('hardware/bender', 'already installed tool')
        tool.chmod(0o700)
        plan = self.put('plan.json', json.dumps(dict(files=rows, target_count=19)))
        return plan, dict(ROOT=self.root, PLAN_SHA=b.digest(plan), LOCKED={'hardware/bender': b.digest(tool)})

    def test_real_unpromoted_tree_refuses_before_tools_or_process(self):
        args = argparse.Namespace(timeout=7200, output=self.root / 'not-created', execute=True)
        with patch.object(b, 'tool_paths', side_effect=AssertionError('must not discover tools')), \
             patch.object(b.subprocess, 'Popen', side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError, 'promotion incomplete'):
                b.run(args)
        self.assertFalse(args.output.exists())

    def test_all_nineteen_after_hashes_required(self):
        plan, constants = self.promotion()
        with patch.multiple(b, **constants):
            self.assertEqual(len(b.guard(self.root, plan)['files']), 19)
            (self.root / 'promoted/18').write_text('before')
            with self.assertRaisesRegex(ValueError, 'promotion incomplete'):
                b.guard(self.root, plan)

    def test_wrong_plan_hash(self):
        plan, constants = self.promotion()
        with patch.multiple(b, **constants):
            plan.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'plan identity'):
                b.guard(self.root, plan)

    def test_missing_or_nonexecutable_bender_rejected(self):
        plan, constants = self.promotion()
        with patch.multiple(b, **constants):
            (self.root / 'hardware/bender').chmod(0o600)
            with self.assertRaisesRegex(ValueError, 'no download'):
                b.guard(self.root, plan)
            (self.root / 'hardware/bender').unlink()
            with self.assertRaisesRegex(ValueError, 'Locked input'):
                b.guard(self.root, plan)

    def test_symlink_promoted_source_rejected(self):
        plan, constants = self.promotion()
        path = self.root / 'promoted/0'
        other = self.put('alias', path.read_text())
        path.unlink(); path.symlink_to(other)
        with patch.multiple(b, **constants), self.assertRaisesRegex(ValueError, 'promotion incomplete'):
            b.guard(self.root, plan)

    def test_no_snapshot_root(self):
        plan, constants = self.promotion()
        with patch.multiple(b, **constants), self.assertRaisesRegex(ValueError, 'actual canonical'):
            b.guard(self.root / 'snapshot', plan)

    def test_exact_make_compile_flags_and_absolute_outputs(self):
        output = Path(self.temp.name) / 'new-output'
        command = b.make_command(output, {'make': Path('/usr/bin/make'), 'g++': Path('/usr/bin/g++')}, self.root)
        self.assertEqual(command.count('compile'), 1)
        self.assertEqual(command[command.index('-o') + 1], str(self.root / 'hardware/bender'))
        for key, value in b.FLAGS.items(): self.assertEqual(command.count(key + '=' + value), 1)
        self.assertIn('buildpath=' + str(output / 'hardware-build'), command)
        self.assertIn('sim_dir=' + str(output / 'sim'), command)
        self.assertEqual(sum(arg.startswith('verify_extra_sources=') for arg in command), 1)
        self.assertTrue(all(str(path) in command[-1] for path in b.UVM))
        self.assertFalse(set(command) & {'sim', 'dc', 'verilate', 'curl'})

    def test_reused_or_input_output_rejected(self):
        tools = {'make': Path('/usr/bin/make'), 'g++': Path('/usr/bin/g++')}
        for output in (self.root, self.root / 'hardware/build_new', self.root / 'software/new'):
            with self.assertRaisesRegex(ValueError, 'fresh independent'):
                b.make_command(output, tools, self.root)

    def graph(self):
        names = list(b.INSERTIONS)
        names += ['hardware/src/vlsu/qbs/qbs_engine.sv', 'hardware/src/vlsu/akv/akv_engine.sv',
                  'hardware/tb/repeated_a.sv', 'hardware/tb/repeated_b.sv',
                  'hardware/tb/repeated_a.sv', 'hardware/tb/repeated_b.sv']
        original = '+define+ARA_QBS_ENABLE=1\n' + '\n'.join(str(self.root / name) for name in names)
        expected = b.expected_graph(original, self.root)
        for path in expected:
            if not path.startswith('+'):
                self.put(Path(path).relative_to(self.root), 'module x; reader_req_o reader_rsp_i endmodule')
        repeats = {name: b.digest(self.root / name) for name in ('hardware/tb/repeated_a.sv', 'hardware/tb/repeated_b.sv')}
        return expected, repeats

    def test_graph_order_exact_and_two_inherited_repeats(self):
        expected, repeats = self.graph()
        b.check_graph('\n'.join(expected), expected, repeats, self.root)
        for actual in (expected[::-1], expected + [expected[-1]], expected[1:]):
            with self.assertRaisesRegex(ValueError, 'graph/order'):
                b.check_graph('\n'.join(actual), expected, repeats, self.root)

    def test_private_reader_and_duplicate_modules_reject(self):
        expected, repeats = self.graph()
        self.put('hardware/src/vlsu/qbs/qbs_engine.sv', 'reader_req_o reader_rsp_i qbs_read_engine #() x();')
        with self.assertRaisesRegex(ValueError, 'Private'):
            b.check_graph('\n'.join(expected), expected, repeats, self.root)
        expected.append(str(self.root / 'hardware/src/vlsu/qbs/qbs_engine.sv'))
        with self.assertRaisesRegex(ValueError, 'duplicate source'):
            b.check_graph('\n'.join(expected), expected, repeats, self.root)

    def test_wrong_repeated_source_bytes_reject(self):
        expected, repeats = self.graph()
        self.put('hardware/tb/repeated_a.sv', 'changed')
        with self.assertRaisesRegex(ValueError, 'duplicate source changed'):
            b.check_graph('\n'.join(expected), expected, repeats, self.root)

    def test_absolute_vcs_argv_has_real_uvm_and_assertions(self):
        output = self.root / 'output'
        argv = b.expected_vcs(output, Path('/tool/bin/vcs'))
        for flag in ('+define+ARA_VERIFY_UVM_CVXIF', '+define+ARA_FAIL_FAST_ASSERTS',
                     '+define+ARA_NO_FSDB', '+lint=PCWM', '-timescale=1ns/100fs'):
            self.assertEqual(argv.count(flag), 1)
        self.assertEqual(argv[argv.index('-top') + 1], 'ara_tb')
        self.assertTrue(all(str(path) in argv for path in b.UVM))
        self.assertFalse(any('snapshot' in arg or 'VERILATOR' in arg for arg in argv))

    def test_original_config_and_mutations(self):
        old = b.ROOT / 'verification/out/qbacc-soc-20261023-02/build/sim/simulator.conf'
        path = self.put('simulator.conf', old.read_text())
        self.assertEqual(b.check_config(path)['sim_l2_bytes'], '16777216')
        for text in (old.read_text() + 'qbs=1\n', old.read_text().replace('vlen=1024', 'vlen=128'),
                     old.read_text().replace('qbs_vrf_continuation=1', 'qbs_vrf_continuation=0')):
            path.write_text(text)
            with self.assertRaises(ValueError): b.check_config(path)

    def test_pin_drift_and_timeout_bound(self):
        path = self.put('input', 'before')
        pins = {str(path): b.digest(path)}
        path.write_text('after')
        with self.assertRaisesRegex(ValueError, 'Input drift'): b.verify(pins)
        for timeout in (0, 7201, True):
            with self.assertRaisesRegex(ValueError, 'Compile bound'):
                b.run(argparse.Namespace(timeout=timeout))


if __name__ == '__main__':
    unittest.main()
