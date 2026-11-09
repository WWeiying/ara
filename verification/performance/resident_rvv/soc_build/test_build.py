#!/usr/bin/env python3
"""Synthetic host tests. No live-overlay read, real prepare, systemd or EDA launch."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build


DEFINES = ('+define+NR_LANES=4', '+define+VLEN=1024', '+define+ARA_QBS_ENABLE=1',
           '+define+ARA_AKV_ENABLE=1', '+define+ARA_AKV_V2_ENABLE=1',
           '+define+SIM_L2_SIZE_BYTES=16777216', '+define+FOR_VERIFY', '+define+TARGET_VERILATOR')
COMMAND = ['/tool/vcs', '-full64', '-sverilog', '-ntb_opts', 'uvm-1.2', '-top', 'ara_tb',
           '-timescale=1ns/100fs', '+define+ARA_SHARED_SIMD_MUL',
           '+define+ARA_VERIFY_UVM_CVXIF', '+define+ARA_FAIL_FAST_ASSERTS', '+define+ARA_NO_FSDB']


def fixture(root):
    root.mkdir()
    for relative in (*build.OVERLAY, *build.METADATA):
        path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('module fixture; endmodule\n' if path.suffix == '.sv' else 'metadata\n')
    header = root/'hardware/include/common/header.svh'
    header.parent.mkdir()
    header.write_text('// reviewed header\n')
    local = root/'hardware/src/adjacent.svh'
    local.write_text('// adjacent frozen header\n')
    (root/'hardware/src/ara.sv').write_text('`include "adjacent.svh"\nmodule ara; endmodule\n')
    text = '\n'.join((*DEFINES, '+incdir+'+str(root/'hardware/include'),
                     *[str(root/p) for p in build.OVERLAY]))+'\n'
    return text


class BuildTests(unittest.TestCase):
    def test_no_snapshot_without_parent_ready(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(build, 'baseline') as baseline:
            out = Path(tmp)/'must_not_exist'
            with self.assertRaisesRegex(ValueError, 'parent-ready'):
                build.prepare(out)
            baseline.assert_not_called()
            self.assertFalse(out.exists())

    def test_no_compile_without_parent_review(self):
        with patch.object(build, 'compile_process') as compile_process:
            with self.assertRaisesRegex(ValueError, 'parent review'):
                build.build(Path('/unused'), False, 'unreviewed')
            compile_process.assert_not_called()

    def test_exact_owned_overlay_and_exclusions(self):
        self.assertEqual(len(build.OVERLAY), 13)
        self.assertEqual(len(build.NEW_RTL), 6)
        self.assertEqual(len(set(build.OVERLAY+build.NEW_RTL)), 19)
        self.assertFalse(any('/deps/' in p or '/tb/' in p or p.startswith(('software/', 'apps/'))
                             for p in build.OVERLAY+build.NEW_RTL))
        self.assertIn('hardware/src/lane/vector_fus_stage.sv', build.OVERLAY)
        self.assertIn('hardware/src/lane/operand_requester.sv', build.OVERLAY)
        self.assertIn('hardware/src/vlsu/akv/akv_resident_pv_control.sv', build.NEW_RTL)

    def test_rewrite_preserves_baseline_order_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, new = Path(tmp)/'old', Path(tmp)/'new'
            text = fixture(root)
            duplicate = str(root/'hardware/src/ara.sv')
            # Duplicating an overlay itself must be rejected, not silently deduped.
            with self.assertRaises(ValueError):
                build.rewrite_filelist(text+duplicate+'\n', root, new)
            extra = root/'hardware/deps/fpu_div_sqrt_mvp/rtl.sv'
            extra.parent.mkdir(parents=True)
            extra.write_text('module frozen_fork; endmodule\n')
            text += str(extra)+'\n'+str(extra)+'\n'
            result = build.rewrite_filelist(text, root, new)
            self.assertEqual(result.splitlines().count(str(new/extra.relative_to(root))), 2)
            self.assertNotIn(str(root), result)
            self.assertEqual(result.splitlines().count(build.PV_DEFINE), 1)
            self.assertIn('+define+TARGET_VERILATOR', result)
            anchor = result.splitlines().index(str(new/'hardware/src/vlsu/akv/akv_engine.sv'))
            self.assertEqual(result.splitlines()[anchor-6:anchor], [str(new/p) for p in build.NEW_RTL])

    def test_missing_overlay_or_unexpected_new_module_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'source'
            text = fixture(root)
            for bad in (text.replace(str(root/build.OVERLAY[0]), ''), text+str(root/build.NEW_RTL[0])+'\n'):
                with self.assertRaises(ValueError):
                    build.rewrite_filelist(bad, root, Path(tmp)/'other')

    def test_filelist_rejects_paths_and_flags_outside_contract(self):
        root = Path('/closed/source')
        for bad in ('/other/file.sv', '-f nested.f', 'relative.sv', '+libext+.v',
                    '+incdir+/other/include', '/closed/source/../escape.sv',
                    '+define+NR_LANES=4\n+define+NR_LANES=8'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build.entries(bad, root)

    def test_configuration_and_no_run_flags(self):
        _, _, defines = build.entries('\n'.join(DEFINES), Path('/unused'))
        build.configuration(defines, COMMAND, False)
        active = dict(defines, ARA_AKV_RESIDENT_PV_ENABLE='1')
        build.configuration(active, COMMAND, True)
        for key, value in (('NR_LANES', '8'), ('VLEN', '2048'), ('SIM_L2_SIZE_BYTES', '2097152'),
                           ('ARA_AKV_ENABLE', '0'), ('IDEAL_DISPATCHER', '0'), ('PITON_ARIANE', '1'),
                           ('ARA_SHARED_FMA', '0'), ('SYNTHESIS', '1')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                build.configuration(dict(defines, **{key: value}), COMMAND, False)
        for flag in ('-R', '-cm', '+PRELOAD=firmware.elf', '+define+ARA_SHARED_FMA', '+define+IDEAL_DISPATCHER', '+define+PITON_ARIANE'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                build.configuration(defines, COMMAND+[flag], False)
        with self.assertRaises(ValueError):
            build.configuration(defines, [x for x in COMMAND if x != '+define+ARA_SHARED_SIMD_MUL'], False)

    def test_map_admitted_command_only(self):
        out = Path('/private/output')
        command = COMMAND+['-f', str(build.BASE/'sources.f'), str(build.BASE/'elfloader.o'),
            str(build.FROZEN/'verification/uvm/test.sv'), str(build.BASE/'boundary_monitor.sv'), '-l', 'comp.vcs.log']
        mapped = build.map_command(command, out)
        self.assertIn(str(out/'sources.f'), mapped)
        self.assertIn(str(out/'inputs/elfloader.o'), mapped)
        self.assertIn(str(out/'source/verification/uvm/test.sv'), mapped)
        self.assertIn(str(out/'inputs/boundary_monitor.sv'), mapped)
        self.assertEqual(mapped[:len(COMMAND)], COMMAND)
        self.assertFalse(any(arg.startswith(str(build.BASE)) for arg in mapped))

    def test_complete_closure_adjacent_headers_and_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'source'
            text = fixture(root)
            graph = build.closure(text, root, [])
            self.assertIn(str(root/'hardware/src/adjacent.svh'), graph['files'])
            self.assertIn(str(root/'hardware/include/common/header.svh'), graph['files'])
            build.verify_closure(graph, text, root, [])
            (root/'hardware/include/unexpected.txt').write_text('new input')
            with self.assertRaisesRegex(ValueError, 'inventory drift'):
                build.verify_closure(graph, text, root, [])

    def test_unknown_or_macro_header_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'source'
            text = fixture(root)
            source = root/'hardware/src/ara.sv'
            for bad in ('`include "untracked.svh"', '`include "../outside.svh"', '`include HEADER_MACRO'):
                source.write_text(bad)
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    build.closure(text, root, [])
            source.write_text('`include "uvm_macros.svh"')
            self.assertEqual(build.closure(text, root, [])['tool_includes'], ['uvm_macros.svh'])
            piton = root/'hardware/deps/cva6/core/include/ariane_pkg.sv'
            piton.parent.mkdir(parents=True)
            piton.write_text('`ifdef PITON_ARIANE\n`include "l15.tmp.h"\n`endif\n')
            text += str(piton)+'\n'
            self.assertEqual(build.closure(text, root, [])['inactive_includes'],
                [dict(source=str(piton), header='l15.tmp.h', guard='PITON_ARIANE')])
            for bad in ('`include "l15.tmp.h"', '`ifdef PITON_ARIANE\n`else\n`include "l15.tmp.h"\n`endif'):
                piton.write_text(bad)
                with self.assertRaises(ValueError):
                    build.closure(text, root, [])

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'source'
            text = fixture(root)
            outside = Path(tmp)/'outside.svh'
            outside.write_text('// outside')
            (root/'hardware/include/escape.svh').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'Escaping'):
                build.closure(text, root, [])

    def test_copy_pin_identity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = Path(tmp)/'input', Path(tmp)/'snapshot'
            source.write_text('accepted')
            pins = {}
            digest = build.sha(source)
            build.copy_pin(source, dest, pins, digest)
            build.verify(pins)
            with self.assertRaises(ValueError):
                build.copy_pin(source, dest, pins, digest)
            source.write_text('drift')
            with self.assertRaisesRegex(ValueError, 'identity drift'):
                build.verify(pins)

    def test_direct_systemd_worker_not_short_launcher(self):
        unit = 'resident-pv-soc-build-example.service'
        build.direct_owner('/user.slice/app.slice/'+unit, unit, 123, 123)
        with self.assertRaises(ValueError):
            build.direct_owner('/other.service', unit, 123, 123)
        with self.assertRaises(ValueError):
            build.direct_owner('/user.slice/'+unit, unit, 122, 123)

    def test_service_command_binds_review_and_separate_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            build.save(out/'source-pins.json', {})
            digest = build.sha(out/'source-pins.json')
            build.save(out/'prepared.json', dict(state='PREPARED_NOT_BUILT', source_pins_sha256=digest))
            command = build.service_command(out)
            self.assertIn('--property=StandardOutput=append:'+str(out/'service.stdout.log'), command)
            self.assertIn('--property=StandardError=append:'+str(out/'service.stderr.log'), command)
            self.assertIn(str(out/'inputs/build.py'), command)
            self.assertIn('--parent-reviewed', command)
            self.assertEqual(command[-1], digest)
            (out/'source-pins.json').write_text('{"tampered":true}')
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                build.service_command(out)

    def test_closed_artifact_allowlist_excludes_all_live_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'inputs').mkdir()
            files = ('service.stdout.log', 'service.stderr.log', 'status.json', 'compile.log', 'inputs/build.py')
            pins = {}
            for name in files:
                path = out/name
                path.write_text('data')
                pins[str(path)] = build.sha(path)
            self.assertEqual(set(build.artifact_pins(out, pins)),
                             {str(out/'compile.log'), str(out/'inputs/build.py')})

    def test_standard_manifest_schema_and_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'source'
            text = fixture(root)
            filelist = Path(tmp)/'sources.f'
            filelist.write_text(text)
            graph = build.closure(text, root, [])
            pins = dict(graph['files'], **{str(filelist): build.sha(filelist)})
            actual = build.source_manifest(text, root, filelist, [], pins)
            expected = {filelist, *(root/p for p in build.OVERLAY), *(root/p for p in build.METADATA),
                        root/'hardware/include/common/header.svh'}
            self.assertEqual(actual['files'], [dict(path=str(p.resolve()), sha256=build.sha(p)) for p in sorted(expected)])
            self.assertEqual(actual['filelist'], str(filelist))
            self.assertEqual(actual['repo_root'], str(root))
            self.assertEqual(actual['extra_sources'], [])
            self.assertEqual(actual['schema_version'], 1)

    def test_overlay_capability_and_bender_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'hardware/include').mkdir(parents=True)
            (root/'hardware/include/ara_pkg.sv').write_text("localparam bit EnableSharedFma = 1'b0;")
            akv = root/'hardware/include/akv_pkg.sv'
            good = """`ifdef ARA_AKV_RESIDENT_PV_ENABLE
localparam bit AkvResidentPvSupported = 1'b0;
function automatic logic [63:0] akv_resident_pv_capability_word(input logic [63:0] i, input bit e);
  return '0;
endfunction
"""
            bender = '\n'.join(build.NEW_RTL)
            akv.write_text(good)
            build.overlay_invariants(root, bender)
            for bad in (good.replace("return '0;", "return '1;"),
                        good.replace("Supported = 1'b0", "Supported = 1'b1"),
                        "function automatic logic old(); return '0; endfunction\n"+good.replace("return '0;", "return '1;")):
                akv.write_text(bad)
                with self.assertRaises(ValueError):
                    build.overlay_invariants(root, bender)
            akv.write_text(good)
            with self.assertRaises(ValueError):
                build.overlay_invariants(root, bender+'\n'+build.NEW_RTL[0])

    def test_image_contract_compatible_but_not_baseline_identity(self):
        self.assertEqual(build.IMAGE_CONTRACT, dict(NrLane=4, VLEN=1024, AXI=128,
            L2sim_bytes=16777216, shared_integer_multiply=True, EnableSharedFma=0))
        self.assertEqual(build.CONFIG['akv_resident_pv_enabled'], 1)
        self.assertEqual(build.CONFIG['akv_resident_pv_capability'], 0)
        self.assertNotEqual(build.CONFIG, build.BASE_CONFIG)
        for name in ('nr_lanes', 'vlen', 'sim_l2_bytes', 'shared_simd_multiplier', 'shared_fma', 'ideal_dispatcher'):
            self.assertEqual(build.CONFIG[name], build.BASE_CONFIG[name])


if __name__ == '__main__':
    unittest.main()
