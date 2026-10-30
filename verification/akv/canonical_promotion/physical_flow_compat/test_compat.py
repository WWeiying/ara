"""Host-only prospective-source tests. No EDA or actual library reads/measurements."""
import copy
import fnmatch
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import render


def candidate(name, key):
    module = types.ModuleType(key)
    module.__file__ = str(render.ROOT / name)
    sys.modules[key] = module
    exec(compile(render.render(name, render.text(render.ROOT / name)), module.__file__, 'exec'), module.__dict__)
    return module


C = candidate(render.COLLECTOR, 'physical_candidate_collector')
P = candidate(render.PREFLIGHT, 'physical_candidate_preflight')
CASES = json.loads((render.HERE / 'organizations.json').read_text())['cases']


def old_tests(filename, key, module):
    spec = importlib.util.spec_from_file_location(key, render.ROOT / 'hardware/scripts/akv' / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[key] = result
    spec.loader.exec_module(result)
    # Isolated test module only; no on-disk or production-module mutation.
    result.MODULE = module
    return result


OLD_C = old_tests('test_collect_synthesis_results.py', 'physical_old_collect_tests', C)
OLD_P = old_tests('test_synthesis_preflight.py', 'physical_old_preflight_tests', P)
# Execute the unchanged old host suites against the prospective implementation.
LegacyCollectorTests = OLD_C.CollectSynthesisResultsTest
LegacyPreflightTests = OLD_P.SynthesisPreflightTest


class OrganizationTests(unittest.TestCase):
    def test_exact_organizations_raw_and_json(self):
        for row in CASES:
            for values in (row, {k: str(v) for k, v in row.items()}):
                self.assertEqual(C.validate_sram_organization(values, 'physical_sram_capacity_bits'),
                                 (row['akv_sram_organization'], row['akv_q_sram_macro_count']))
        for row in CASES[:2]:
            legacy = {k: v for k, v in row.items() if k not in ('akv_sram_organization', 'akv_q_sram_macro_count')}
            self.assertEqual(C.validate_sram_organization(legacy, 'physical_sram_capacity_bits')[0],
                             row['akv_sram_organization'])

    def test_ambiguous_wrong_counts_capacity_and_types_rejected(self):
        for row in CASES:
            for field in row:
                bad = dict(row)
                bad[field] = 'unknown' if field == 'akv_sram_organization' else row[field] + 1
                with self.subTest(row=row, field=field), self.assertRaises(C.CollectionError):
                    C.validate_sram_organization(bad, 'physical_sram_capacity_bits')
            for field in ('akv_sram_organization', 'akv_q_sram_macro_count'):
                bad = dict(row); del bad[field]
                with self.assertRaises(C.CollectionError):
                    C.validate_sram_organization(bad, 'physical_sram_capacity_bits')
        for value in (True, False, 1.0, '1.0', '+1', ' 1', None):
            with self.subTest(value=value), self.assertRaises(C.CollectionError):
                C.validate_sram_organization({**CASES[2], 'akv_q_sram_macro_count': value}, 'physical_sram_capacity_bits')
        bad = {k: v for k, v in CASES[2].items() if k not in ('akv_sram_organization', 'akv_q_sram_macro_count')}
        with self.assertRaises(C.CollectionError):
            C.validate_sram_organization(bad, 'physical_sram_capacity_bits')
        for label in [r['akv_sram_organization'] for r in CASES[:2]]:
            with self.assertRaises(C.CollectionError):
                C.validate_sram_organization({**CASES[2], 'akv_sram_organization': label}, 'physical_sram_capacity_bits')

    def test_duplicate_discriminator_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.rpt'
            path.write_text('akv_sram_organization=one\nakv_sram_organization=two\n')
            with self.assertRaises(C.CollectionError):
                C.read_key_values(path)

    def test_metric_paths_keep_area_checks_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'SYNTHETIC_area.rpt'
            path.write_text('Total cell area: 1000.0\nMacro/Black Box area: 600.0\n')
            base = dict(clock_period_ns='1.0', clock_uncertainty_ns='.15', design_total_area_um2='1000',
                        design_macro_area_um2='600', design_logic_area_um2='400',
                        worst_setup_slack_ns='-0.1', worst_reg_to_reg_setup_slack_ns='0.02')
            for mode, scope in (('standalone', 'akv_engine_standalone'), ('integrated', 'ara_soc_integrated')):
                for row in CASES:
                    values = {**base, **{k: str(v) for k, v in row.items()}, 'scope': scope}
                    got = C.validate_metrics(mode, values, path)
                    self.assertEqual(got['akv_sram_organization'], row['akv_sram_organization'])
                    self.assertEqual(got['akv_q_sram_macro_count'], row['akv_q_sram_macro_count'])
                    with self.assertRaises(C.CollectionError):
                        C.validate_metrics(mode, {**values, 'design_total_area_um2': '1001'}, path)
                    with self.assertRaises(C.CollectionError):
                        C.validate_metrics(mode, {**values, 'worst_setup_slack_ns': 'nan'}, path)

    def test_unified_library_names_and_summary_revalidation(self):
        fixture = OLD_C.CollectSynthesisResultsTest()
        fixture.setUp()
        try:
            fixture.write_standalone_reports()
            values = C.read_key_values(fixture.summary_rpt)
            values.update({k: str(v) for k, v in CASES[2].items()})
            fixture.summary_rpt.write_text(''.join(f'{k}={v}\n' for k, v in values.items()))
            kv = fixture.root / 'ts1n28hpcpuhdsvtb128x256_fixture.db'
            kv.write_text('SYNTHETIC HOST FIXTURE; NOT A PHYSICAL LIBRARY\n')
            fixture.flow.write_text(f'set std_library {fixture.std_db}\nset q_library {fixture.sram_db}\nset kv_library {kv}\n')
            fixture.mark_fresh(); os.utime(kv, ns=(1_000_000_000, 1_000_000_000))
            with patch.object(C.subprocess, 'check_output', return_value='synthetic-fixture\n'):
                summary = C.collect(fixture.spec())
            C.validate_summary(fixture.output, 'standalone', fixture.root)
            for field, value in (('akv_q_sram_macro_count', 0), ('akv_sram_organization', 'split_v1_96x256_v2_128x256'),
                                 ('akv_sram_capacity_bits', 311296), ('akv_v1_sram_macro_count', 1)):
                bad = copy.deepcopy(summary); bad['metrics'][field] = value
                fixture.output.write_text(json.dumps(bad))
                with self.assertRaises(C.CollectionError):
                    C.validate_summary(fixture.output, 'standalone', fixture.root)
            for dropped in (kv, fixture.sram_db):
                original = fixture.flow.read_text()
                fixture.flow.write_text('\n'.join(line for line in original.splitlines() if str(dropped) not in line))
                with self.assertRaises(C.CollectionError):
                    C.library_inputs((fixture.flow,), CASES[2]['akv_sram_organization'])
                fixture.flow.write_text(original)
        finally:
            fixture.tearDown()


class PreflightUnifiedTests(unittest.TestCase):
    def setUp(self):
        self.fixture = OLD_P.SynthesisPreflightTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.write_filelist()
        q = self.fixture.root / 'Q64_SYNTHETIC.db'
        q.write_text('HOST STUB; NOT A LIBRARY\n')
        self.fixture.setup.write_text(self.fixture.setup.read_text() + f'set q_store_db {q}\n')
        old = self.fixture.filelist.read_text()
        old = old.replace('hardware/src/vlsu/qbs/qbs_read_engine.sv\n',
                          'hardware/src/vlsu/qbs/qbs_read_engine.sv\n' + P.UNIFIED_AKV_SOURCES[0] + '\n')
        old = old.replace('hardware/src/vlsu/akv/akv_engine.sv\n',
                          '\n'.join(P.UNIFIED_AKV_SOURCES[1:]) + '\nhardware/src/vlsu/akv/akv_engine.sv\n')
        old = old.replace(P.AKV_SRAM_BLACKBOX + '\n', P.AKV_Q_SRAM_BLACKBOX + '\n')
        self.fixture.filelist.write_text(old)
        self.options = P.Options(**{**vars(self.fixture.options()), 'akv_q_sram_db': q,
                                    'akv_storage_organization': P.UNIFIED_AKV_ORGANIZATION})

    def test_unified_accepts_q64_without_legacy96_requirement(self):
        self.fixture.sram_db.unlink()
        got = P.audit(self.options)
        self.assertEqual(got['akv_storage_organization'], P.UNIFIED_AKV_ORGANIZATION)

    def test_selection_missing_sources_order_and_defines(self):
        original = self.fixture.filelist.read_text()
        for source in (*P.UNIFIED_AKV_SOURCES, P.AKV_Q_SRAM_BLACKBOX, P.AKV_V2_SOURCES[0]):
            self.fixture.filelist.write_text(original.replace(source + '\n', ''))
            with self.subTest(source=source), self.assertRaises(P.PreflightError):
                P.audit(self.options)
        self.fixture.filelist.write_text(original)
        for key, value in (('akv_storage_organization', P.SPLIT_AKV_ORGANIZATION),
                           ('akv_storage_organization', 'unknown'), ('require_akv_v2', False)):
            with self.assertRaises(P.PreflightError):
                P.audit(P.Options(**{**vars(self.options), key: value}))
        late = P.UNIFIED_AKV_SOURCES[1]
        self.fixture.filelist.write_text(original.replace(late + '\n', '') + late + '\n')
        with self.assertRaises(P.PreflightError):
            P.audit(self.options)
        self.fixture.filelist.write_text(original.replace('+define+ARA_AKV_V2_ENABLE=1\n', ''))
        with self.assertRaises(P.PreflightError):
            P.audit(self.options)

    def test_q64_db_missing_or_unlinked(self):
        old = self.fixture.setup.read_text()
        self.fixture.setup.write_text('\n'.join(x for x in old.splitlines() if str(self.options.akv_q_sram_db) not in x))
        with self.assertRaises(P.PreflightError):
            P.audit(self.options)
        self.fixture.setup.write_text(old)
        self.options.akv_q_sram_db.unlink()
        with self.assertRaises(P.PreflightError):
            P.audit(self.options)

    def test_unused_akv_sources_do_not_change_qbs_only_selection(self):
        self.fixture.write_filelist()
        self.fixture.filelist.write_text(self.fixture.filelist.read_text() + P.UNIFIED_AKV_SOURCES[-1] + '\n')
        options = P.Options(**{**vars(self.fixture.options()), 'require_akv': False, 'require_akv_v2': False})
        P.audit(options)


class TclWriterTests(unittest.TestCase):
    def evaluate(self, cells, integrated):
        import tkinter
        interp = tkinter.Tcl()

        def get_cells(*args):
            expression = args[args.index('-filter') + 1]
            match = re.fullmatch(r'ref_name (==|=~) (\S+) && full_name =~ (\S+)', expression)
            self.assertIsNotNone(match, 'Unsupported mock-filter expression')
            op, ref, path = match.groups()
            return tuple(name for name, actual in cells if fnmatch.fnmatchcase(name, path) and
                         (actual == ref if op == '==' else fnmatch.fnmatchcase(actual, ref)))

        interp.createcommand('get_cells', get_cells)
        interp.createcommand('sizeof_collection', lambda collection: len(interp.splitlist(collection)))
        interp.eval(render.metric_block(integrated))
        prefix = 'akv_' if integrated else ''
        return tuple(str(interp.getvar(prefix + field)) for field in
                     ('organization', 'macro_count', 'v1_macro_count', 'v2_macro_count', 'q_macro_count', 'capacity_bits'))

    def cells(self, row, integrated):
        prefix = ('soc/ara/vlsu/' if integrated else '') + 'i_akv_engine/'
        ref = lambda depth: f'TS1N28HPCPUHDSVTB{depth}X256M1SWBSO'
        if row is CASES[2]:
            result = [(prefix + 'i_unified_context/i_q_store/i_q_sram', ref(64))]
            result += [(prefix + f'i_unified_context/i_kv_store/gen_context_bank[{i}]/i_context_sram', ref(128)) for i in range(8)]
        else:
            depths = (64, 64) if row is CASES[0] else (96, 128)
            result = [(prefix + f'i_context/bank[{i}]/sram', ref(depths[0])) for i in range(row['akv_v1_sram_macro_count'])]
            result += [(prefix + f'i_v2_context/bank[{i}]/sram', ref(depths[1])) for i in range(row['akv_v2_sram_macro_count'])]
        # Same reference outside AKV must not inflate its physical capacity.
        return result + [('soc/cpu/dcache/sram', ref(64)), ('soc/qbs/context/sram', ref(128))]

    def test_actual_tcl_partition_and_outside_scope(self):
        for integrated in (False, True):
            for row in CASES:
                self.assertEqual(self.evaluate(self.cells(row, integrated), integrated), tuple(str(row[k]) for k in
                    ('akv_sram_organization', 'akv_sram_macro_count', 'akv_v1_sram_macro_count',
                     'akv_v2_sram_macro_count', 'akv_q_sram_macro_count', 'physical_sram_capacity_bits')))

    def test_wrong_hierarchy_depth_count_and_mixed_organizations(self):
        import tkinter
        for integrated in (False, True):
            cells = self.cells(CASES[2], integrated)
            bad_sets = [cells[1:], cells + [cells[0]],
                        [(cells[0][0].replace('i_q_store', 'i_context'), cells[0][1]), *cells[1:]],
                        [(cells[0][0], cells[0][1].replace('64X256', '96X256')), *cells[1:]],
                        cells + [(cells[0][0] + '_extra', 'TS1N28HPCPUHDSVTB8X128M1SWBSO')],
                        cells + self.cells(CASES[1], integrated)[:-2]]
            for bad in bad_sets:
                with self.assertRaises(tkinter.TclError):
                    self.evaluate(bad, integrated)
        self.assertEqual(self.evaluate([], True)[0], 'not_instantiated')
        with self.assertRaises(tkinter.TclError):
            self.evaluate([], False)


class ProposalTests(unittest.TestCase):
    def test_scope_line_endings_and_native_library_link_text(self):
        for name in render.TARGETS:
            original = render.text(render.ROOT / name)
            changed = render.render(name, original)
            self.assertNotEqual(original, changed)
            if name.endswith('.py'):
                compile(changed, name, 'exec')
            with self.assertRaises(ValueError):
                render.render(name, changed)
            if name == render.GLOBAL:
                self.assertEqual(original.count('\r\n'), changed.count('\r\n'))
        standalone = render.render(render.STANDALONE, render.text(render.ROOT / render.STANDALONE))
        self.assertIn('$kv_sram_library $q_sram_library $synthetic_library', standalone)
        self.assertNotIn('q_macro_count * 96', standalone)

    def test_fresh_proposal_only_four_files_and_original_hashes(self):
        import hashlib
        before = {name: (render.ROOT / name).read_bytes() for name in render.TARGETS}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'proposal'
            receipt = render.prepare(render.ROOT, out)
            self.assertEqual(set(receipt['after']), set(render.TARGETS))
            patch = (out / 'physical_flow.patch').read_bytes()
            self.assertEqual(hashlib.sha256(patch).hexdigest(), receipt['patch_sha256'])
            for name, data in before.items():
                self.assertEqual((render.ROOT / name).read_bytes(), data)
                self.assertEqual((out / name).read_bytes(), render.render(name, data.decode()).encode())
            self.assertFalse(receipt['compiler_invoked'])
            self.assertFalse(receipt['libraries_measured'])
            self.assertFalse(receipt['ppa_closed'])


if __name__ == '__main__':
    unittest.main()
