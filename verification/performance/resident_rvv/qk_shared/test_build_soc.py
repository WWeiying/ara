#!/usr/bin/env python3
import io
import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tested_stage3_builder', Path(__file__).with_name('build_soc.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def archive_bytes(items):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, kind, data in items:
            item = tarfile.TarInfo(name)
            item.type = kind
            if kind == tarfile.SYMTYPE:
                item.linkname = data
                archive.addfile(item)
            else:
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
    return buffer.getvalue()


class FrozenBuild(unittest.TestCase):
    def test_real_template_normalization_preserves_first_and_every_other_line(self):
        base, closure = build.helpers()
        path = build.TEMPLATE/'shared/sources.f'
        build.verify({path: build.ANCHORS[path]})
        original = path.read_text()
        normalized = build.normalize_template(original, closure)
        lines = original.splitlines(keepends=True)
        self.assertEqual(normalized, ''.join(line for n, line in enumerate(lines, 1)
                                            if n not in (980, 981)))
        root = build.TEMPLATE/'shared/source'
        before, includes, defines = closure.entries(original, root)
        after, new_includes, new_defines = closure.entries(normalized, root)
        self.assertEqual((len(before), len(after), len(set(after))), (444, 442, 442))
        self.assertEqual(set(after), set(before))
        self.assertEqual((includes, defines), (new_includes, new_defines))
        for name in build.TEMPLATE_DUPLICATES:
            self.assertEqual(after.count(root/name), 1)
            self.assertLess(normalized.index(str(root/name)),
                            normalized.index(str(root/'hardware/tb/ara_tb.sv')))
        # Exercise the real memory/root rewrite without modifying the template
        # or requiring production/live source inputs.
        rewritten = base.freeze_filelist(normalized, root, root)
        rewritten_sources, _, rewritten_defines = closure.entries(rewritten, root)
        self.assertEqual(rewritten_sources, after)
        self.assertEqual(rewritten_defines['SIM_L2_SIZE_BYTES'], '16777216')
        self.assertEqual(build.sha(path), build.ANCHORS[path])

    def test_normalization_rejects_changed_unknown_and_already_normalized_inputs(self):
        _, closure = build.helpers()
        root = build.TEMPLATE/'shared/source'
        original = (build.TEMPLATE/'shared/sources.f').read_text()
        first = str(root/next(iter(build.TEMPLATE_DUPLICATES)))+'\n'
        unknown = str(root/'hardware/tb/ara_tb.sv')+'\n'
        for bad in (original+first, original+unknown, original.replace(first, '', 1),
                    original+'+define+EXTRA=1\n', build.normalize_template(original, closure)):
            with self.assertRaisesRegex(ValueError, 'normalization input'):
                build.normalize_template(bad, closure)
        # Check the duplicate contract independently of the preimage hash.
        for bad in (original+first, original+unknown, original.replace(first, '', 1)):
            contract = dict(build.FILELIST_NORMALIZATION,
                            input_sha256=build.hashlib.sha256(bad.encode()).hexdigest())
            with patch.object(build, 'FILELIST_NORMALIZATION', contract):
                with self.assertRaisesRegex(ValueError, 'duplicate pattern'):
                    build.normalize_template(bad, closure)

    def test_final_policy_still_rejects_any_duplicate(self):
        _, closure = build.helpers()
        root = build.TEMPLATE/'shared/source'
        normalized = build.normalize_template((build.TEMPLATE/'shared/sources.f').read_text(), closure)
        for name in (*build.TEMPLATE_DUPLICATES, 'hardware/tb/ara_tb.sv'):
            with self.assertRaisesRegex(ValueError, 'Duplicate compiler source'):
                build.policy(root, normalized+str(root/name)+'\n', [], closure)

    def test_filelist_insertion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for anchor, modules in build.MODULES:
                for name in (anchor, *modules):
                    path = root/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
            original = '\n'.join(str(root/anchor) for anchor,_ in build.MODULES)+'\n'
            result = build.insert_modules(original, root)
            self.assertEqual(result.count('+define+ARA_AKV_RESIDENT_QK_ENABLE=1'), 1)
            self.assertNotIn('ARA_QBS_LANE_MUL_ENABLE', result)
            for anchor, modules in build.MODULES:
                for name in modules:
                    self.assertEqual(result.splitlines().count(str(root/name)), 1)
                    self.assertLess(result.index(str(root/name)), result.index(str(root/anchor)))
            for bad in (result, '', original+original,
                        original+'+define+ARA_QBS_LANE_MUL_ENABLE=0\n'):
                with self.assertRaises(ValueError): build.insert_modules(bad, root)

    def test_archive_rejects_escape_and_unexpected_link(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, kind in (('../escape', tarfile.REGTYPE),
                               ('hardware/src/linked.sv', tarfile.SYMTYPE)):
                data = '/tmp/other' if kind == tarfile.SYMTYPE else b''
                with self.assertRaises(ValueError):
                    build.extract_archive(archive_bytes([(name, kind, data)]),
                                          Path(directory), ('hardware/src',))

    def test_archive_rejects_unselected_duplicate_and_stale(self):
        for entries in (
            [('extra', tarfile.REGTYPE, b'x')],
            [('hardware/src/a.sv', tarfile.REGTYPE, b'a')]*2,
        ):
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
                build.extract_archive(archive_bytes(entries), Path(directory), ('hardware/src',))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'obsolete').mkdir()
            (root/'obsolete/deleted.sv').write_text('stale')
            with self.assertRaisesRegex(ValueError, 'Stale'):
                build.extract_archive(archive_bytes([]), root, ('hardware/src',))
            (root/'obsolete/deleted.sv').unlink()
            with self.assertRaisesRegex(ValueError, 'Stale'):
                build.extract_archive(archive_bytes([]), root, ('hardware/src',))

    def test_archive_keeps_only_dependencies_and_new_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dep = root/'hardware/deps/dpi.cc'
            dep.parent.mkdir(parents=True)
            dep.write_text('accepted')
            data = archive_bytes([('hardware/src/new.sv', tarfile.REGTYPE, b'new')])
            build.extract_archive(data, root, ('hardware/src',))
            self.assertEqual(set(build.files(root)), {str(dep), str(root/'hardware/src/new.sv')})

    def test_exact_inventory_detects_extra_missing_changed_and_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root/'a'
            p.write_text('original')
            pins = build.files(root)
            build.exact_files(root, pins)
            (root/'empty-extra').mkdir()
            with self.assertRaises(ValueError): build.exact_files(root, pins)
            (root/'empty-extra').rmdir()
            p.write_text('changed')
            with self.assertRaises(ValueError): build.exact_files(root, pins)
            p.write_text('original')
            (root/'extra').touch()
            with self.assertRaises(ValueError): build.exact_files(root, pins)
            (root/'extra').unlink()
            p.unlink()
            with self.assertRaises(ValueError): build.exact_files(root, pins)
            p.symlink_to('/etc/hosts')
            with self.assertRaises(ValueError): build.files(root)

    def test_accepted_template_and_cpu_gate_are_read_only(self):
        deps = build.template_inputs()
        self.assertGreater(len(deps), 300)
        cpu, report, pins = build.check_cpu_gate()
        self.assertEqual(report['overlay'], build.CPU_OVERLAY)
        self.assertEqual(build.sha(build.TEMPLATE/'shared/source'/build.CPU_OVERLAY['target']),
                         build.CPU_OVERLAY['before_sha256'])
        self.assertTrue(all(not p.startswith(str(build.ROOT/'hardware')) for p in pins))
        self.assertTrue(callable(cpu.apply_to_snapshot))

    def test_template_filelist_anchor_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'sources.f'
            p.write_text('changed')
            with patch.object(build, 'ANCHORS', {p: '0'*64}):
                with self.assertRaisesRegex(ValueError, 'Identity'):
                    build.template_inputs()

    def test_complete_image_and_exact_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root/'simv'
            simv.write_text('executable')
            simv.chmod(0o755)
            daidir = root/'simv.daidir'
            daidir.mkdir()
            with self.assertRaises(ValueError): build.image_inventory(root)
            (daidir/'.daidir_complete').touch()
            (daidir/'design.so').write_text('design')
            pins = build.image_inventory(root)
            (daidir/'extra').touch()
            self.assertNotEqual(build.image_inventory(root), pins)
            (daidir/'extra').unlink()
            (daidir/'design.so').unlink()
            (daidir/'design.so').symlink_to(simv)
            with self.assertRaises(ValueError): build.image_inventory(root)

    def test_direct_owner_rejects_launcher_child_and_wrong_unit(self):
        build.direct_owner('/user/u.service', 'u.service', 42, 42)
        for group, main in (('/user/other.service', 42), ('/user/u.service/child', 42),
                            ('/user/u.service', 43)):
            with self.assertRaises(ValueError):
                build.direct_owner(group, 'u.service', main, 42)

    def test_one_shot_preserves_first_failure_and_rejects_bad_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build.save(root/'source-pins.json', {'a': 'b'})
            review = build.sha(root/'source-pins.json')
            with patch.object(build, 'owner', return_value={'owner_pid': 42}):
                with self.assertRaises(ValueError): build.claim_attempt(root, '0'*64, 'u')
                self.assertFalse((root/'attempt.json').exists())
                build.claim_attempt(root, review, 'u')
                build.save(root/'build.json', {'state': 'FAIL', 'original': True})
                before = build.files(root)
                with self.assertRaises(ValueError): build.claim_attempt(root, review, 'u')
                self.assertEqual(before, build.files(root))

    def test_no_prepare_without_commit_and_parent_gates(self):
        with patch.object(build, 'output_path', side_effect=lambda p: p), \
             patch.object(build.subprocess, 'check_output') as command:
            for revision, ready in (('HEAD', True), ('0'*40, False), ('', True)):
                with self.assertRaises(ValueError):
                    build.prepare(Path('/not-created'), revision, ready)
            command.assert_not_called()

    def test_filelist_and_closure_reject_conflicts_and_include_additions(self):
        _, closure = build.helpers()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                closure.entries('+define+VLEN=1024\n+define+VLEN=512\n', root)
            with self.assertRaises(ValueError):
                closure.entries('/etc/hosts\n', root)
            for name in closure.METADATA:
                p = root/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
            inc = root/'include'
            inc.mkdir()
            (inc/'a.svh').write_text('// a')
            top = root/'top.sv'
            top.write_text(chr(96)+'include "a.svh"\n')
            text = '+incdir+'+str(inc)+'\n'+str(top)+'\n'
            frozen = closure.closure(text, root, [])
            (inc/'extra.svh').touch()
            with self.assertRaises(ValueError): closure.verify_closure(frozen, text, root, [])

    def test_snapshot_membership_is_reconstructed_from_archive_and_accepted_pins(self):
        with tempfile.TemporaryDirectory(dir=build.OUT, prefix='stage3_builder_host_') as directory:
            root = Path(directory)
            template = root/'template'
            template.mkdir()
            target = build.CPU_OVERLAY['target']
            build.save(template/'source-pins.json',
                       {str(template/'shared/source'/target): build.CPU_OVERLAY['before_sha256']})
            data = io.BytesIO()
            revision = '1'*40
            with tarfile.open(fileobj=data, mode='w', format=tarfile.PAX_FORMAT,
                              pax_headers={'comment': revision}) as archive:
                item = tarfile.TarInfo('hardware/src/top.sv')
                item.size = 3
                archive.addfile(item, io.BytesIO(b'top'))
            (root/'source.tar').write_bytes(data.getvalue())
            actual = {str(root/'source'/target): build.CPU_OVERLAY['after_sha256'],
                      str(root/'source/hardware/src/top.sv'): build.hashlib.sha256(b'top').hexdigest()}
            with patch.object(build, 'TEMPLATE', template):
                build.verify_snapshot(root, revision, ('hardware/src',), actual)
                for bad in (dict(actual, extra='stale'), {}, {**actual, str(root/'source'/target): '0'*64}):
                    with self.assertRaises(ValueError):
                        build.verify_snapshot(root, revision, ('hardware/src',), bad)
                with self.assertRaisesRegex(ValueError, 'commit'):
                    build.verify_snapshot(root, '2'*40, ('hardware/src',), actual)

    def test_checked_build_validates_receipt_owner_and_image_members(self):
        with tempfile.TemporaryDirectory(dir=build.OUT, prefix='stage3_builder_host_') as directory:
            root = Path(directory)
            build.save(root/'source-pins.json', {'fixture': 'only'})
            review = build.sha(root/'source-pins.json')
            unit = build.service_unit(root)
            owner = dict(unit=unit, owner_pid=42, main_pid=42, cgroup='/user/'+unit)
            build.save(root/'owner.json', owner)
            build.save(root/'attempt.json', dict(review_sha256=review, **owner))
            image = {'fixture-image': 'only'}
            build.save(root/'image-pins.json', image)
            report = dict(state='STAGE3_SOC_BUILT_NOT_EXECUTED', simv=str(root/'sim/simv'),
                revision='1'*40, configuration=build.CONFIG, image_contract=build.IMAGE_CONTRACT,
                cpu_overlay=build.CPU_OVERLAY, post_pins_match=True, post_image_match=True,
                full_soc_executed=False, performance_measured=False, hardware_acceptance=False,
                automatic_retry=False, source_pins_sha256=review, image_pins=image, artifacts={})
            build.save(root/'build.json', report)
            with patch.object(build, 'verify_prepared', return_value=({'revision': '1'*40}, {})), \
                 patch.object(build, 'image_inventory', return_value=image), \
                 patch.object(build, 'evidence', return_value={}):
                accepted, _ = build.checked_build(root)
                self.assertEqual(accepted, report)
                with patch.object(build, 'image_inventory', return_value={**image, 'extra.so': 'bad'}):
                    with self.assertRaisesRegex(ValueError, 'image'):
                        build.checked_build(root)
                original = build.read
                for field, value in (('cpu_overlay', {}), ('configuration', {}), ('post_pins_match', False)):
                    def changed(path, field=field, value=value):
                        return dict(report, **{field: value}) if path == root/'build.json' else original(path)
                    with patch.object(build, 'read', side_effect=changed):
                        with self.assertRaisesRegex(ValueError, 'receipt'):
                            build.checked_build(root)


if __name__ == '__main__':
    unittest.main()
