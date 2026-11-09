"""Host-only recipe and identity tests. Never invokes a compiler or simulator."""
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import experiment as e


class RecipeTests(unittest.TestCase):
    def test_smoke_and_abba_entry_only(self):
        out = Path('/tmp/pv-recipe-test')
        smoke, abba = (e.recipes(out, k) for k in e.KINDS)
        self.assertEqual(len(smoke), 7)
        self.assertEqual(smoke[1:], abba[1:])
        for recipe, name in ((smoke, 'smoke.c'), (abba, 'main.c')):
            argv = recipe[0]['argv']
            self.assertEqual(argv[argv.index('-c')+1], str(e.HERE/name))

    def test_strong_control_and_sealed_prepare(self):
        recipe = e.recipes(Path('/tmp/pv-recipe-test'), 'smoke')
        self.assertTrue(set(e.STRONG_FLAGS) <= set(recipe[3]['argv']))
        self.assertIn(str(e.HERE.parent/'pv_prepare/prepare.S'), recipe[2]['argv'])
        self.assertIn(str(e.HERE.parent/'rotation/pv_rotation.S'), recipe[3]['argv'])
        self.assertIn('no-aliases,numeric', recipe[5]['argv'])
        for command in recipe[:4]:
            self.assertTrue({'-fno-fast-math', '-ffp-contract=off', '-mno-relax', '-MD'} <= set(command['argv']))

    def test_exact_fifteen_reused_objects(self):
        out = Path('/tmp/pv-recipe-test')
        link = e.recipes(out, 'smoke')[4]['argv']
        base = json.loads((e.BASE/'build.json').read_text())
        self.assertNotIn(str(e.BASE/'00_main.o'), link)
        self.assertEqual([p for p in link if p.endswith('.o') and Path(p).parent == e.BASE],
                         [p for p in base['objects'] if Path(p).name != '00_main.o'])
        self.assertEqual(sum(p.endswith('.o') for p in link), 19)
        self.assertIn('-Wl,--wrap='+e.SYMBOL, link)

    def test_recipes_do_not_execute(self):
        with patch.object(e.subprocess, 'run', side_effect=AssertionError('Execution forbidden')):
            e.recipes(Path('/tmp/pv-recipe-test'), 'smoke')

    def test_work_counts_and_tail(self):
        self.assertEqual([s['tokens'] for s in e.shapes('smoke')], [64, 64, 9])
        self.assertEqual(e.shapes('abba'), e.shapes('smoke')*2)
        work = e.work_expectation('abba')
        self.assertEqual((work['legacy_akv_perf'], work['resident_pv_perf'],
                          work['vector_akv_allocations'], work['opcode_allocations']), (674, 6, 664, 6))
        self.assertEqual(work['candidate_fma_per_lane_per_call'], 2192)
        self.assertIn('not PV semantic acceptance', work['legacy_classification'])

    def test_inventory_includes_both_other_owners(self):
        self.assertEqual(set(e.OWN), {'experiment.py', 'test_experiment.py', 'README.md',
            'main.c', 'pv.S', 'smoke.c', 'test_wrapper.py', 'check_resident.py', 'test_check_resident.py'})
        e.contract.verify({str(p): h for p, h in e.ANCHORS.items()})

    def test_resident_hook_preserves_partial_scope(self):
        answer = dict(numerical_checked=False, protocol_checked=False)
        checker = SimpleNamespace(check_successful_pv=lambda p, t, s: (
            self.assertEqual((p, t, s), ('vector.csv', 'text', e.shapes('smoke'))) or answer))
        with patch.object(e, 'load', return_value=checker):
            self.assertIs(e.check_resident_work('vector.csv', 'text', 'smoke'), answer)
        self.assertEqual(answer, dict(numerical_checked=False, protocol_checked=False))

    def test_no_run_action_or_implicit_review(self):
        with self.assertRaises(ValueError):
            e.build(Path('/tmp/not-authorized'), 'smoke')
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            e.main(['run', '--kind', 'abba'])

    def test_manifest_is_build_only(self):
        meta = json.loads((e.BASE/'build.json').read_text())
        m = e.fields(Path('/tmp/pv-recipe-test'), 'smoke', meta)
        self.assertFalse(m['target_executed'] or m['rtl_executed'] or m['soc_acceptance'])
        self.assertEqual(m['required_run_plusargs'], ['+RESIDENT_PV_PERF', '+RESIDENT_PV_WATCHDOG'])
        self.assertEqual(m['watchdog_lease_cycles'], 32768)
        self.assertEqual(m['first_execution'], 'smoke_only')
        self.assertFalse(m['automatic_abba'] or m['run_implemented'])


class SocIdentityTests(unittest.TestCase):
    """Exercise real closure/overlay validation with a tiny synthetic predecessor."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.b = e.soc_contract()
        b = self.b
        self.patches = patch.multiple(b, ROOT=root/'live', OUT=root, BASE=root/'base',
            ADMITTED=root/'admitted', FROZEN=root/'base/source')
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.out = root/'build02'

        def write(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        self.write = write
        for relative in (*b.OVERLAY, *b.METADATA, 'hardware/tb/ara_tb.sv', 'include/test.svh'):
            write(b.FROZEN/relative, '// frozen '+relative+'\n')
        filelist = '\n'.join(['+define+'+k+'='+v for k, v in dict(NR_LANES='4', VLEN='1024',
            ARA_QBS_ENABLE='1', ARA_AKV_ENABLE='1', ARA_AKV_V2_ENABLE='1',
            SIM_L2_SIZE_BYTES='16777216', FOR_VERIFY='1').items()]+[
            '+incdir+'+str(b.FROZEN/'include'),
            *[str(b.FROZEN/p) for p in (*b.OVERLAY, 'hardware/tb/ara_tb.sv')]])+'\n'
        write(b.BASE/'sources.f', filelist)
        extra = b.BASE/'boundary_monitor.sv'
        write(extra, '// frozen monitor\n')
        command = ['vcs', '-f', str(b.BASE/'sources.f'), str(extra), '-top', 'ara_tb',
            '+define+ARA_SHARED_SIMD_MUL', '-full64', '-sverilog', '-ntb_opts', 'uvm-1.2',
            '-timescale=1ns/100fs', '+define+ARA_VERIFY_UVM_CVXIF',
            '+define+ARA_FAIL_FAST_ASSERTS', '+define+ARA_NO_FSDB']
        base_graph = b.closure(filelist, b.FROZEN, [extra])
        pins = dict(base_graph['files'])
        base_mock = patch.object(b, 'baseline', return_value=({}, command, base_graph, [extra], dict(pins)))
        base_mock.start()
        self.addCleanup(base_mock.stop)
        shutil.copytree(b.FROZEN, self.out/'source')
        write(self.out/'inputs/boundary_monitor.sv', extra.read_text())
        for relative in (*b.OVERLAY, *b.NEW_RTL):
            content = '// overlay '+relative+'\n'
            if relative == 'hardware/include/ara_pkg.sv':
                content += "localparam bit EnableSharedFma = 1'b0;\n"
            if relative == 'hardware/include/akv_pkg.sv':
                content += ("`ifdef ARA_AKV_RESIDENT_PV_ENABLE\n`endif\n"
                    "localparam bit AkvResidentPvSupported = 1'b0;\n"
                    "function automatic logic [31:0] akv_resident_pv_capability_word();\n"
                    "return '0;\nendfunction\n")
            write(b.ROOT/relative, content)
            write(self.out/'source'/relative, content)
            pins[str(b.ROOT/relative)] = e.sha(b.ROOT/relative)
        write(self.out/'inputs/audit/Bender.yml', '\n'.join(b.NEW_RTL)+'\n')
        write(self.out/'inputs/build.py', e.SOC_HELPER.read_text())
        text = b.rewrite_filelist(filelist, b.FROZEN, self.out/'source')
        write(self.out/'sources.f', text)
        extras = [self.out/'inputs/boundary_monitor.sv']
        graph = b.closure(text, self.out/'source', extras)
        pins.update(graph['files'])
        self.json('closure.json', graph)
        self.json('command.json', b.map_command(command, self.out))
        self.json('selection.json', dict(schema_version=1, configuration=b.CONFIG,
            image_contract=b.IMAGE_CONTRACT, baseline=str(b.BASE), admitted=str(b.ADMITTED),
            parent_review_required=True, timeout_seconds=7200, execution='NOT_RUN',
            snapshot_root=str(self.out/'source'), extras=list(map(str, extras))))
        overlay = [dict(path=p, source=str(b.ROOT/p), sha256=e.sha(self.out/'source'/p),
            baseline_sha256=base_graph['files'].get(str(b.FROZEN/p)),
            kind='replacement' if p in b.OVERLAY else 'new') for p in (*b.OVERLAY, *b.NEW_RTL)]
        self.json('overlay.json', dict(overlay=overlay, bender_audit_only=True,
            live_inputs_excluded=['hardware/tb', 'hardware/deps', 'software', 'apps'],
            baseline_testbench_sha256=base_graph['files'][str(b.FROZEN/'hardware/tb/ara_tb.sv')]))
        write(self.out/'sim/simulator.conf', ''.join(f'{k}={v}\n' for k, v in b.CONFIG.items()))
        pins[str(self.out/'sources.f')] = e.sha(self.out/'sources.f')
        self.json('sim/vcs_source_manifest.json', b.source_manifest(text, self.out/'source',
            self.out/'sources.f', extras, pins))
        for path in self.out.rglob('*'):
            if path.is_file():
                pins[str(path)] = e.sha(path)
        self.json('source-pins.json', pins)
        self.json('prepared.json', dict(state='PREPARED_NOT_BUILT', parent_review_required=True,
            source_pins_sha256=e.sha(self.out/'source-pins.json'), overlay_files=19,
            source_files=len(graph['files']), execution='NOT_RUN', capability=0))
        write(self.out/'sim/simv', 'not an executable simulation\n')
        (self.out/'sim/simv').chmod(0o755)
        write(self.out/'sim/simv.daidir/image.bin', 'synthetic image\n')
        image = {str(p): e.sha(p) for p in (self.out/'sim/simv', self.out/'sim/simv.daidir/image.bin')}
        self.json('image-pins.json', image)
        for name in ('compile.log', 'tests.log', 'sim/comp.vcs.log'):
            write(self.out/name, 'synthetic host fixture only\n')
        self.report = dict(state='RESIDENT_PV_SOC_BUILT_NOT_EXECUTED', execution='NOT_RUN',
            post_pins_match=True, post_image_match=True, performance_measured=False,
            soc_acceptance=False, fpga_acceptance=False, capability_advertised=False,
            experimental_direct_wrapper_only=True, dependencies_from_accepted_snapshot=True,
            baseline=str(b.ADMITTED), configuration=b.CONFIG, image_contract=b.IMAGE_CONTRACT,
            simv=str(self.out/'sim/simv'), image_pins=image,
            source_pins_sha256=e.sha(self.out/'source-pins.json'), artifacts=b.artifact_pins(self.out, pins))
        self.json('build.json', self.report)
        helper_mock = patch.object(e, 'soc_contract', return_value=b)
        helper_mock.start()
        self.addCleanup(helper_mock.stop)

    def json(self, relative, value):
        self.write(self.out/relative, json.dumps(value, indent=2)+'\n')

    def test_complete_successful_identity(self):
        result, pins = e.checked_soc(self.out)
        self.assertEqual(result, self.report)
        self.assertIn(str(self.out/'build.json'), pins)
        self.assertIn(str(self.out/'sim/simv.daidir/image.bin'), pins)

    def test_failure_and_old_receipt_rejected(self):
        for state in ('FAIL', 'CURRENT_AREA_SOC_BUILT_NOT_EXECUTED',
                      'CURRENT_AREA_SOC_COMPILE_AUDITED_NOT_EXECUTED'):
            self.json('build.json', dict(self.report, state=state))
            with self.subTest(state=state), self.assertRaises(ValueError):
                e.checked_soc(self.out)

    def test_capability_and_configuration_rejected(self):
        for changed in (dict(capability_advertised=True),
                        dict(configuration=dict(self.b.CONFIG, shared_fma=1))):
            self.json('build.json', dict(self.report, **changed))
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                e.checked_soc(self.out)

    def test_added_image_member_rejected(self):
        self.write(self.out/'sim/simv.daidir/extra.bin', 'unreviewed\n')
        with self.assertRaisesRegex(ValueError, 'Image inventory'):
            e.checked_soc(self.out)

    def test_include_directory_member_drift_rejected(self):
        self.write(self.out/'source/include/extra.svh', '// unpinned\n')
        with self.assertRaisesRegex(ValueError, 'closure/include inventory'):
            e.checked_soc(self.out)

    def test_stable_artifact_drift_rejected(self):
        self.write(self.out/'compile.log', 'changed\n')
        with self.assertRaisesRegex(ValueError, 'SoC artifacts'):
            e.checked_soc(self.out)

    def test_service_logs_are_not_identity(self):
        self.write(self.out/'service.stdout.log', 'still closing\n')
        self.write(self.out/'status.json', '{}\n')
        e.checked_soc(self.out)


if __name__ == '__main__':
    unittest.main()
