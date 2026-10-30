"""Host generation and make -n tests; never execute a compiler or simulator."""
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import generate_standalone as gen
import standalone_makefiles as proposal

ROOT = Path(__file__).resolve().parents[3]


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def original(self, kind):
        return (ROOT / f'verification/{kind}/Makefile').read_text()

    def rendered(self, kind):
        return proposal.render(self.original(kind), kind)

    def test_exact_inverse_and_original_targets(self):
        for kind in ('qbs', 'akv'):
            before, after = self.original(kind), self.rendered(kind)
            targets = lambda text: re.findall(r'^([^\s#=][^\n=]*?):(?!=)', text, re.M)
            self.assertEqual(targets(before), targets(after))
            for old, new in reversed(proposal.edits(kind)):
                after = after.replace(new, old, 1)
            self.assertEqual(after, before)

    def test_drift_and_double_application_rejected(self):
        for kind in ('qbs', 'akv'):
            with self.assertRaises(ValueError):
                proposal.render(self.rendered(kind), kind)
            anchor = proposal.edits(kind)[0][0]
            with self.assertRaises(ValueError):
                proposal.render(self.original(kind).replace(anchor, ''), kind)

    def test_original_run_recipes_vectors_and_markers_unchanged(self):
        cases = {'qbs': ('rtl-engine-check', 'rtl-context-macro-check', 'rtl-tile-context-macro-check', 'rtl-read-check'),
                 'akv': ('rtl-check', 'rtl-macro-check', 'synth-preflight', 'context-synth', 'engine-synth')}
        for kind, targets in cases.items():
            for name in targets:
                pattern = '^' + re.escape(name) + r':[^\n]*\n(?:\t[^\n]*\n)*'
                self.assertEqual(re.search(pattern, self.original(kind), re.M)[0],
                                 re.search(pattern, self.rendered(kind), re.M)[0])
        self.assertIn('+QBS_COMMAND_VECTOR_FILE=$(RTL_COMMAND_VECTOR_FILE)', self.rendered('qbs'))

    def dry(self, kind, target):
        makefile = self.out / (kind + '.mk')
        makefile.write_text(self.rendered(kind))
        source = self.out / 'extra.sv'
        source.write_text('// Not executed: host command-routing fixture\n')
        filelist = self.out / 'sources.f'
        filelist.write_text('// Not compiled\n')
        args = ['make', '-n', '--no-print-directory', '-C', str(ROOT / ('verification/' + kind)),
                '-f', str(makefile), target, 'RTL_EXTRA_SOURCES=' + str(source),
                'RTL_EXTRA_DEFINES=+define+EXTRA_SENTINEL=1', 'RTL_ENGINE_DEFINES=+define+ENGINE_SENTINEL=1',
                'RTL_MACRO_VCS_FLAGS=+nospecify +notimingcheck', 'RTL_RUN_TIMEOUT=123',
                'RTL_ENGINE_BUILD=' + str(self.out / 'qbs_build'), 'BUILD=' + str(self.out / 'akv_build'),
                'MACRO_BUILD=' + str(self.out / 'macro_build'), 'SYNTH_WRAPPER_BUILD=' + str(self.out / 'synth_build'),
                'FILELIST=' + str(filelist), 'MACRO_FILELIST=' + str(filelist)]
        if kind == 'qbs':
            # The unpromoted tree intentionally lacks the future shared source.
            # Test command routing with a host-only existing source, not fake RTL execution.
            args += ['RTL_SOURCES=' + str(source)]
        completed = subprocess.run(args, text=True, capture_output=True, timeout=20, check=True)
        return completed.stdout.replace('\\\n', ' ')

    def test_qbs_dry_flags_wrapper_and_vectors(self):
        text = self.dry('qbs', 'rtl-engine-check')
        self.assertIn('--kind qbs', text)
        self.assertIn('+define+ENGINE_SENTINEL=1', text)
        self.assertIn('/standalone/composed_engine.sv', text)
        self.assertIn('/standalone/original_suite.sv', text)
        compile_line = next(line for line in text.splitlines() if ' && vcs ' in line)
        self.assertNotIn('qbs_engine_tb.sv', compile_line)
        self.assertIn('-top qbs_engine_tb', compile_line)
        self.assertIn('timeout --foreground 123', text)
        self.assertIn('+QBS_COMMAND_VECTOR_FILE=', text)
        self.assertIn('extra.sv', compile_line)

    def test_akv_generic_macro_wrapper_flag_consistency(self):
        for target in ('rtl-check', 'rtl-macro-check', 'synth-wrapper-compile'):
            text = self.dry('akv', target)
            compile_line = next(line for line in text.splitlines() if ' && vcs ' in line)
            self.assertIn('+define+EXTRA_SENTINEL=1', compile_line)
            self.assertIn('extra.sv', compile_line)
            self.assertIn('+define+ARA_AKV_ENABLE=1', compile_line)
            self.assertIn('+define+ARA_AKV_V2_ENABLE=1', compile_line)
            if target != 'rtl-check':
                self.assertIn('+define+TARGET_SRAM_MC', compile_line)
                self.assertIn('+nospecify +notimingcheck', compile_line)
                self.assertEqual(compile_line.count('qbs_context_sram_macro_model.sv'), 1)
            if target != 'synth-wrapper-compile':
                self.assertIn('/standalone/composed_engine.sv', compile_line)
                self.assertIn('/standalone/original_suite.sv', compile_line)
                self.assertNotIn('akv_engine_tb.sv', compile_line)
                self.assertIn('-top akv_engine_tb', compile_line)
            else:
                self.assertIn('-top akv_engine_synth_wrapper', compile_line)
                self.assertNotIn('composed_engine.sv', compile_line)

    def test_macro_model_has_all_required_depths_once(self):
        text = (ROOT / 'verification/qbs/qbs_context_sram_macro_model.sv').read_text()
        for depth in (64, 76, 96, 128):
            self.assertEqual(len(re.findall(r'\bmodule\s+TS1N28HPCPUHDSVTB' + str(depth) + r'X256M1SWBSO\b', text)), 1)
        qbs = self.rendered('qbs')
        self.assertLess(qbs.index('qbs/qbs_read_engine.sv'), qbs.index('vlsu/qbs_akv_shared_reader.sv'))
        self.assertIn('+incdir+$(ROOT)/hardware/include', qbs)

    def fake_root(self):
        root = self.out / 'tree'
        for kind in ('qbs', 'akv'):
            path = root / f'hardware/src/vlsu/{kind}/{kind}_engine.sv'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'module {kind}_engine #(parameter type reader_req_t=logic, parameter type reader_rsp_t=logic) '
                            '(output reader_req_t reader_req_o, input reader_rsp_t reader_rsp_i);\n' +
                            ('akv_unified_context i_unified_context ();\n' if kind == 'akv' else '') + 'endmodule\n')
        for name in ('hardware/src/vlsu/qbs/qbs_read_engine.sv', 'hardware/src/vlsu/qbs_akv_shared_reader.sv',
                     'hardware/include/shared_reader_types.svh', 'hardware/src/vlsu/akv/akv_unified_context.sv',
                     'hardware/src/vlsu/akv/akv_q_store.sv', 'hardware/src/vlsu/akv/akv_legacy_repacker.sv',
                     'hardware/src/vlsu/akv/akv_v2_context.sv'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('// Host placeholder; never compiled\n')
        return root

    def test_generated_original_tb_inverse_and_accepted_wrapper(self):
        root = self.fake_root()
        for kind in ('qbs', 'akv'):
            bench = ROOT / f'verification/{kind}/{kind}_engine_tb.sv'
            output = self.out / kind
            report = gen.generate(root, kind, bench, output)
            self.assertEqual(report['state'], 'COMPOSITION_GENERATED_NOT_COMPILED')
            adapted = (output / 'original_suite.sv').read_text()
            restored = adapted.replace('dut.i_engine.', 'dut.').replace(
                f'  {kind}_engine_composed #(\n', f'  {kind}_engine #(\n', 1)
            self.assertEqual(restored, bench.read_text())
            entry, _ = gen.composer.contract(kind)
            self.assertEqual(gen.sha(output / 'composed_engine.sv'), entry['origin_wrapper_sha256'])
            self.assertIn('owner_q ? observed_read_range_count_o : i_shared_reader.reader_rsp.range_count',
                          (output / 'composed_engine.sv').read_text())
            self.assertEqual(gen.generate(root, kind, bench, output), report)

    def test_reject_old_engine_mutated_tb_and_output_overlap(self):
        root = self.fake_root()
        bench = ROOT / 'verification/qbs/qbs_engine_tb.sv'
        with self.assertRaises(ValueError):
            gen.generate(ROOT, 'qbs', bench, self.out / 'old')
        changed = self.out / 'changed.sv'
        changed.write_text(bench.read_text().replace('$fatal', '$display', 1))
        with self.assertRaises(ValueError):
            gen.generate(root, 'qbs', changed, self.out / 'changed_out')
        with self.assertRaises(ValueError):
            gen.generate(root, 'qbs', bench, root)
        engine = root / 'hardware/src/vlsu/qbs/qbs_engine.sv'
        engine.write_text(engine.read_text() + '\nqbs_read_engine #() private_reader ();\n')
        with self.assertRaises(ValueError):
            gen.generate(root, 'qbs', bench, self.out / 'private')
        self.assertFalse((self.out / 'private').exists())

    def test_proposal_inputs_unchanged_and_patch_scope(self):
        before = {kind: self.original(kind) for kind in ('qbs', 'akv')}
        output = self.out / 'proposal'
        report = proposal.prepare(ROOT, output)
        text = (output / 'standalone_makefiles.patch').read_text()
        self.assertEqual(re.findall(r'^\+\+\+ (.*)$', text, re.M),
                         ['b/verification/qbs/Makefile', 'b/verification/akv/Makefile'])
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), report['patch_sha256'])
        for kind in before:
            self.assertEqual(before[kind], self.original(kind))
        self.assertFalse(report['compiler_invoked'])


if __name__ == '__main__':
    unittest.main()
