"""Host Tcl mocks and prospective Python only; no EDA or real DB inspection."""
import importlib.util
from pathlib import Path
import sys
import subprocess
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import render

# Re-run the frozen semantic suites against v2 rendered sources, not v1 output.
spec = importlib.util.spec_from_file_location('physical_v2_inherited_tests', render.V1 / 'test_compat.py')
prior = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prior
with patch.dict(sys.modules, {'render': render}), patch.object(render, 'HERE', render.V1):
    spec.loader.exec_module(prior)
LegacyCollectorTests = prior.LegacyCollectorTests
LegacyPreflightTests = prior.LegacyPreflightTests
OrganizationTests = prior.OrganizationTests
TclWriterTests = prior.TclWriterTests


class PreflightUnifiedTests(prior.PreflightUnifiedTests):
    def test_selection_missing_sources_order_and_defines(self):
        p = prior.P
        original = self.fixture.filelist.read_text()
        for source in (*p.UNIFIED_AKV_SOURCES, p.AKV_Q_SRAM_BLACKBOX, *p.AKV_V2_SOURCES):
            self.fixture.filelist.write_text(original.replace(source + '\n', ''))
            with self.subTest(source=source), self.assertRaises(p.PreflightError):
                p.audit(self.options)
        self.fixture.filelist.write_text(original)
        for value in (p.SPLIT_AKV_ORGANIZATION, 'unknown'):
            with self.assertRaises(p.PreflightError):
                p.audit(p.Options(**{**vars(self.options), 'akv_storage_organization': value}))
        for late in (*p.UNIFIED_AKV_SOURCES, *p.AKV_V2_SOURCES):
            self.fixture.filelist.write_text(original.replace(late + '\n', '') + late + '\n')
            with self.subTest(late=late), self.assertRaises(p.PreflightError):
                p.audit(self.options)
        self.fixture.filelist.write_text(original.replace('+define+ARA_AKV_V2_ENABLE=1\n', ''))
        with self.assertRaises(p.PreflightError):
            p.audit(self.options)

    def legacy_options(self):
        original = self.fixture.filelist.read_text()
        self.fixture.filelist.write_text(original.replace('+define+ARA_AKV_V2_ENABLE=1\n',
                                                        '+define+ARA_AKV_V2_ENABLE=0\n'))
        return prior.P.Options(**{**vars(self.options), 'require_akv_v2': False})

    def test_legacy_only_unified_accepts_v2_zero_or_absent_without_96(self):
        options = self.legacy_options()
        self.fixture.sram_db.unlink()
        self.assertEqual(prior.P.audit(options)['akv_storage_organization'], render.UNIFIED)
        self.fixture.filelist.write_text(self.fixture.filelist.read_text().replace(
            '+define+ARA_AKV_V2_ENABLE=0\n', ''))
        prior.P.audit(options)

    def test_legacy_only_requires_explicit_akv_and_actual_enable_define(self):
        options = self.legacy_options()
        with self.assertRaises(prior.P.PreflightError):
            prior.P.audit(prior.P.Options(**{**vars(options), 'require_akv': False}))
        self.fixture.filelist.write_text(self.fixture.filelist.read_text().replace(
            '+define+ARA_AKV_ENABLE=1\n', '+define+ARA_AKV_ENABLE=0\n'))
        with self.assertRaises(prior.P.PreflightError):
            prior.P.audit(options)

    def test_legacy_only_requires_all_storage_sources_and_order(self):
        options = self.legacy_options()
        original = self.fixture.filelist.read_text()
        for source in (*prior.P.UNIFIED_AKV_SOURCES, *prior.P.AKV_V2_SOURCES):
            for changed in (original.replace(source + '\n', ''),
                            original.replace(source + '\n', '') + source + '\n'):
                self.fixture.filelist.write_text(changed)
                with self.subTest(source=source), self.assertRaises(prior.P.PreflightError):
                    prior.P.audit(options)

    def test_legacy_only_requires_kv128_blackbox_db_and_setup(self):
        options = self.legacy_options()
        original = self.fixture.filelist.read_text()
        blackbox = 'backend/blackbox/' + prior.P.EXTRA_SRAM_NAMES['akv_v2_sram_db'] + '_tt0p9v25c.v'
        self.assertIn(blackbox + '\n', original)
        self.fixture.filelist.write_text(original.replace(blackbox + '\n', ''))
        with self.assertRaises(prior.P.PreflightError):
            prior.P.audit(options)
        self.fixture.filelist.write_text(original)
        setup = self.fixture.setup.read_text()
        self.fixture.setup.write_text('\n'.join(line for line in setup.splitlines()
                                               if str(options.akv_v2_sram_db) not in line))
        with self.assertRaises(prior.P.PreflightError):
            prior.P.audit(options)
        self.fixture.setup.write_text(setup)
        options.akv_v2_sram_db.unlink()
        with self.assertRaises(prior.P.PreflightError):
            prior.P.audit(options)

    def test_explicit_split_legacy_graph_remains_legal(self):
        self.fixture.write_filelist(akv_v2_define=False)
        options = prior.P.Options(**{**vars(self.fixture.options()), 'require_akv_v2': False,
                                    'akv_storage_organization': render.SPLIT})
        self.assertEqual(prior.P.audit(options)['akv_storage_organization'], render.SPLIT)


class ProposalTests(prior.ProposalTests):
    def test_scope_line_endings_and_native_library_link_text(self):
        for name in render.TARGETS:
            source = render.text(render.ROOT / name)
            changed = render.render(name, source)
            self.assertNotEqual(source, changed)
            if name.endswith('.py'):
                compile(changed, name, 'exec')
            with self.assertRaises(ValueError):
                render.render(name, changed)
            if name == render.GLOBAL:
                self.assertEqual(source.count('\r\n'), changed.count('\r\n'))
            if name == render.GLOBAL:
                self.assertEqual(changed, render.old.render(name, source))
        self.assertIn('$storage_libraries', render.render(render.STANDALONE,
                      render.text(render.ROOT / render.STANDALONE)))


class SelectionTests(unittest.TestCase):
    def standalone(self, selected=None, missing=()):
        interp = tkinter.Tcl()
        interp.eval('unset -nocomplain ::env(AKV_STORAGE_ORGANIZATION)')
        if selected is not None:
            interp.setvar('::env(AKV_STORAGE_ORGANIZATION)', selected)
        source = render.render(render.STANDALONE, render.text(render.ROOT / render.STANDALONE))
        fragment = source[source.index('set std_library '):source.index('set_host_options ')]
        interp.eval('set dc_filelist /fake/list; set wrapper /fake/wrapper; set project_sdc /fake/sdc')
        checked, app = [], {}

        def file_command(operation, path):
            self.assertEqual(operation, 'isfile')
            checked.append(path)
            return int(path not in missing)

        interp.createcommand('file', file_command)
        interp.createcommand('set_app_var', lambda key, value: app.__setitem__(key, value) or '')
        interp.eval(fragment)
        return interp, checked, app

    def test_default_split_no_q64_required_or_linked(self):
        interp, checked, app = self.standalone(missing=(render.library(64),))
        self.assertEqual(interp.getvar('selected_organization'), render.SPLIT)
        self.assertNotIn(render.library(64), checked)
        self.assertNotIn(render.library(64), interp.splitlist(app['link_library']))
        for depth in (96, 128):
            self.assertIn(render.library(depth), checked)
            self.assertIn(render.library(depth), interp.splitlist(app['link_library']))

    def test_unified_no_deleted_96_required_or_linked(self):
        interp, checked, app = self.standalone(render.UNIFIED, (render.library(96),))
        self.assertNotIn(render.library(96), checked)
        self.assertNotIn(render.library(96), interp.splitlist(app['link_library']))
        for depth in (64, 128):
            self.assertIn(render.library(depth), checked)
            self.assertIn(render.library(depth), interp.splitlist(app['link_library']))

    def test_bad_selection_and_missing_selected_library_rejected(self):
        for selection in ('', 'unknown', 'legacy_v1_v2_64x256', render.UNIFIED + ' '):
            with self.subTest(selection=selection), self.assertRaises(tkinter.TclError):
                self.standalone(selection)
        for selection, depths in ((render.SPLIT, (96, 128)), (render.UNIFIED, (64, 128))):
            for depth in depths:
                with self.subTest(selection=selection, depth=depth), self.assertRaises(tkinter.TclError):
                    self.standalone(selection, (render.library(depth),))

    def test_actual_classification_must_match_selected_organization(self):
        partitions = {render.SPLIT: (10, 0, 0, 0, 0, 2, 8),
                      render.UNIFIED: (9, 1, 8, 0, 0, 0, 0),
                      'legacy_v1_v2_64x256': (20, 0, 0, 4, 16, 0, 0)}
        for selected in (render.SPLIT, render.UNIFIED):
            for actual, counts in partitions.items():
                interp, _, _ = self.standalone(selected)
                seq = iter(counts)
                interp.createcommand('get_cells', lambda *args: tuple(str(i) for i in range(next(seq))))
                interp.createcommand('sizeof_collection', lambda x: len(interp.splitlist(x)))
                source = render.render(render.STANDALONE, render.text(render.ROOT / render.STANDALONE))
                block = source[source.index('# Classify actual AKV-owned'):source.index('set macro_area 0.0')]
                if selected == actual:
                    interp.eval(block)
                    self.assertEqual(interp.getvar('organization'), selected)
                else:
                    with self.assertRaises(tkinter.TclError):
                        interp.eval(block)

    def test_collector_ignores_only_exact_inactive_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'selected.tcl'
            std = Path(tmp) / 'tcbn28hpcplus_fixture.db'
            std.write_bytes(b'synthetic')
            for organization, depths in ((render.SPLIT, (96, 128)), (render.UNIFIED, (64, 128))):
                source.write_text(render.selection() + f'set std_library "{std}"\n')
                allowed = {str(std), *(render.library(d) for d in depths)}
                is_file = Path.is_file
                with patch.object(Path, 'is_file', lambda p: str(p) in allowed if str(p).endswith('.db') else is_file(p)):
                    found = prior.C.library_inputs((source,), organization)
                    self.assertEqual(set(map(str, found)), allowed)
                    for absent in tuple(allowed):
                        allowed.remove(absent)
                        with self.assertRaises(prior.C.CollectionError):
                            prior.C.library_inputs((source,), organization)
                        allowed.add(absent)
                    # Unrelated declarations must still be required, never silently filtered.
                    source.write_text(source.read_text() + 'set another "/absent/extra.db"\n')
                    with self.assertRaises(prior.C.CollectionError):
                        prior.C.library_inputs((source,), organization)

    def test_collector_ambiguous_selection_rejected(self):
        for block in (render.selection() * 2,
                      render.selection().replace(render.library(64), '/changed/q.db'),
                      render.MARKER + '\n'):
            with self.assertRaises(prior.C.CollectionError):
                prior.C.selected_standalone_libraries(block, render.UNIFIED)
        for organization in (None, '', 'legacy_v1_v2_64x256', 'unknown'):
            with self.assertRaises(prior.C.CollectionError):
                prior.C.selected_standalone_libraries(render.selection(), organization)


class CallerTests(unittest.TestCase):
    def test_make_recipe_dryrun_no_real_dependencies(self):
        original = render.text(render.ROOT / render.MAKEFILE)
        changed = render.render(render.MAKEFILE, original)
        start = changed.index('dc_akv_storage_organization ?=')
        end = changed.index('\ndc_locked:', start)
        # Only the actual prospective variable and recipe; an inert prerequisite
        # replaces the dependency closure, so no Bender/DC/container can execute.
        fragment = changed[start:end] + '\n.PHONY: dc_flist_locked\ndc_flist_locked:\n'
        for options, expected in ((['akv=1', 'akv_v2=1'], render.UNIFIED),
                (['akv=1', 'akv_v2=1', 'dc_akv_storage_organization=' + render.SPLIT], render.SPLIT),
                (['akv=1', 'akv_v2=0'], render.UNIFIED),
                (['akv=1', 'akv_v2=0', 'dc_akv_storage_organization=' + render.SPLIT], render.SPLIT),
                (['akv=0', 'akv_v2=0'], None)):
            result = subprocess.run(['make', '-rR', '-n', '-f', '-', 'dc_preflight_locked',
                                     'qbs=1', 'mc=1', 'nr_lanes=4', 'vlen=1024', *options],
                                    input=fragment, text=True, capture_output=True, check=True,
                                    env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            output = result.stdout
            self.assertIn('--require-qbs', output)
            self.assertIn('--require-macro-sram', output)
            self.assertIn('--nr-lanes 4 --vlen 1024', output)
            if expected:
                self.assertIn('--akv-storage-organization ' + expected, output)
            else:
                self.assertNotIn('--akv-storage-organization', output)
        self.assertEqual(original[:original.index('dc_preflight_locked:')],
                         changed[:changed.index('# Promoted resource package;')])
        self.assertEqual(original[original.index('\ndc_locked:'):], changed[changed.index('\ndc_locked:'):])

    def test_standalone_both_callers_agree_without_recursive_execution(self):
        source = render.text(render.CALLER_INPUT)
        changed = render.render_caller(source)
        start = changed.index('dc_akv_storage_organization ?=')
        end = changed.index('\ncontext-synth:', start)
        # GNU make executes $(MAKE) recipes even with -n. Replace ONLY that token
        # in this test fragment with a print-only variable, never run recursion.
        fragment = changed[start:end].replace('$(MAKE)', '$(PRINT_ONLY_MAKE)')
        fragment += '\n.PHONY: synth-wrapper-compile\nsynth-wrapper-compile:\n'
        for selection in (render.UNIFIED, render.SPLIT):
            result = subprocess.run(['make', '-rR', '-n', '-f', '-', 'synth-preflight',
                'dc_akv_storage_organization=' + selection, 'PRINT_ONLY_MAKE=make',
                'ROOT=/fake', 'SYNTH_CHECKER=/fake/check.py', 'DC_FILELIST=/fake/list',
                'SYNTH_SDC=/fake/sdc', 'DC_SETUP=/fake/setup'], input=fragment,
                text=True, capture_output=True, check=True,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            self.assertIn('dc_akv_storage_organization=' + selection, result.stdout)
            self.assertIn('--akv-storage-organization ' + selection, result.stdout)
            self.assertIn('--require-akv-v2', result.stdout)
        with self.assertRaises(ValueError):
            render.render_caller(changed)
        self.assertEqual(source[:source.index('synth-preflight:')], changed[:start])
        self.assertEqual(source[source.index('\ncontext-synth:'):], changed[end:])

    def test_fresh_patches_apply_and_inverse_exactly(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / 'proposal'
            receipt = render.prepare(render.ROOT, out)
            fixture = base / 'fixture'
            before = {name: (render.ROOT / name).read_bytes() for name in render.TARGETS}
            before[render.CALLER_TARGET] = render.CALLER_INPUT.read_bytes()
            for name, data in before.items():
                path = fixture / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            for patchname in ('physical_flow.patch', 'standalone_caller.patch'):
                subprocess.run(['git', 'apply', str(out / patchname)], cwd=fixture,
                               check=True, capture_output=True)
            for name in before:
                self.assertEqual((fixture / name).read_bytes(), (out / name).read_bytes())
            info = receipt['standalone_caller']
            self.assertEqual(info['before_sha256'], hashlib.sha256(before[render.CALLER_TARGET]).hexdigest())
            self.assertEqual(info['after_sha256'], hashlib.sha256((fixture / render.CALLER_TARGET).read_bytes()).hexdigest())
            self.assertEqual(receipt['patch_apply_order'][0], str(render.PACKAGE_PATCH))
            for patchname in ('standalone_caller.patch', 'physical_flow.patch'):
                subprocess.run(['git', 'apply', '-R', str(out / patchname)], cwd=fixture,
                               check=True, capture_output=True)
            for name, data in before.items():
                self.assertEqual((fixture / name).read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
