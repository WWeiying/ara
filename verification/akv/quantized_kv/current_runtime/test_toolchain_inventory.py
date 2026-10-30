import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('quantkv_inventory_test_subject', HERE / 'toolchain_inventory.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def dry_run(frontend='cc1plus', temporary='ccABC'):
    return f'''Toolchain wrapper executing:
    '/sdk/bin/g++.br_real'
    '--sysroot'
    '/sdk/sysroot'
COLLECT_GCC=/sdk/bin/g++.br_real
 /sdk/libexec/{frontend} -o /tmp/{temporary}.s /dev/null
 /sdk/bin/as -o /tmp/{temporary}.o /tmp/{temporary}.s
 /sdk/libexec/collect2 -static -o /dev/null -plugin /sdk/libexec/plugin.so /sdk/sysroot/crt1.o /sdk/lib/crti.o /sdk/lib/crtbeginT.o /tmp/{temporary}.o -lstdc++ -lm -ldl -lgcc -lgcc_eh -lpthread -lc /sdk/lib/crtend.o /sdk/lib/crtn.o
'''


class InventoryTests(unittest.TestCase):
    def test_plan_preserves_selection_normalizes_only_temporaries(self):
        a = tool.parse_plan(dry_run(), 'cc1plus')
        b = tool.parse_plan(dry_run(temporary='ccXYZ123'), 'cc1plus')
        self.assertEqual(a, b)
        self.assertEqual(a['real_driver'], '/sdk/bin/g++.br_real')
        self.assertEqual(len(a['startup']), 5)
        self.assertEqual(a['extras'], ['/sdk/libexec/plugin.so'])
        self.assertNotEqual(a['commands'][1][-1], a['commands'][1][-2])

    def test_wrong_wrapper_real(self):
        with self.assertRaisesRegex(ValueError, 'Wrapper did not'):
            tool.parse_plan(dry_run().replace("'/sdk/bin/g++.br_real'", "'/sdk/bin/cache'"), 'cc1plus')

    def test_extra_command(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected compiler'):
            tool.parse_plan(dry_run() + ' /sdk/bin/evil --run\n', 'cc1plus')

    def test_duplicate_real_driver(self):
        with self.assertRaisesRegex(ValueError, 'Missing/duplicate'):
            tool.parse_plan(dry_run() + 'COLLECT_GCC=/elsewhere/g++\n', 'cc1plus')

    def test_nonstatic_or_wrong_startup(self):
        for text in (dry_run().replace('-static', '-shared'), dry_run().replace('crtbeginT.o', 'crtbeginS.o')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                tool.parse_plan(text, 'cc1plus')

    def test_missing_library_or_frontend(self):
        for text in (dry_run().replace('-lstdc++ ', ''), dry_run().replace('-lc ', ''),
                     dry_run().replace('/cc1plus ', '/cc1 ')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                tool.parse_plan(text, 'cc1plus')

    def test_unresolved_gnu_answers(self):
        for answer in ('ld', '', '/sdk/ld\n/sdk/other'):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                tool.absolute_answer(answer)

    def test_file_content_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'compiler'
            p.write_bytes(b'old')
            pins = {str(p): tool.identity(p)}
            tool.verify_files(pins)
            p.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                tool.verify_files(pins)

    def test_directory_and_file_aliases_same_bytes_retarget_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'sdk').mkdir()
            (root / 'alias').symlink_to('sdk', target_is_directory=True)
            for name in ('real1', 'real2'):
                (root / 'sdk' / name).write_bytes(b'same')
            wrapper = root / 'sdk/wrapper'
            wrapper.symlink_to('real1')
            driver = root / 'alias/wrapper'
            before = tool.identity(driver)
            self.assertEqual(len(before['symlinks']), 2)
            wrapper.unlink()
            wrapper.symlink_to('real2')
            with self.assertRaises(ValueError):
                tool.verify_files({str(driver): before})

    def test_symlink_cycle_and_mode_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cycle'
            p.symlink_to('cycle')
            with self.assertRaisesRegex(ValueError, 'cycle/depth'):
                tool.identity(p)
            p.unlink()
            p.write_bytes(b'compiler')
            p.chmod(0o755)
            before = tool.identity(p)
            p.chmod(0o644)
            with self.assertRaises(ValueError):
                tool.verify_files({str(p): before})

    def fixture(self, root):
        f = root / 'fake-tool'
        f.write_bytes(b'fixture, not a compiler')
        return dict(schema='quantkv_gnu_toolchain_inventory_v1', flags=tool.FLAGS, environment=tool.ENV,
                    drivers={k: dict(invoked=str(f)) for k in ('gcc', 'gxx')}, files={str(f): tool.identity(f)})

    def test_capture_and_verify_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = self.fixture(root)
            with patch.object(tool, 'discover', return_value=(inventory, [])):
                first = tool.run(root / 'before')
                after = tool.run(root / 'after', inventory=root / 'before/inventory.json')
            self.assertEqual(first['state'], 'PASS')
            self.assertEqual(after['state'], 'PASS')
            self.assertFalse(after['qemu_abi_proof'])
            self.assertFalse(after['compilation_or_link_execution'])
            self.assertEqual(after['previous_inventory_sha256'], first['inventory_sha256'])

    def test_requery_change_fails_not_relabels_old_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = self.fixture(root)
            with patch.object(tool, 'discover', return_value=(original, [])):
                tool.run(root / 'before')
            before = (root / 'before/inventory.json').read_bytes()
            changed = copy.deepcopy(original)
            changed['drivers']['gcc']['version'] = 'unexpected'
            with patch.object(tool, 'discover', return_value=(changed, [])), self.assertRaisesRegex(ValueError, 'selection/specs/files'):
                tool.run(root / 'after', inventory=root / 'before/inventory.json')
            self.assertEqual(json.loads((root / 'after/result.json').read_text())['state'], 'FAIL')
            self.assertEqual((root / 'before/inventory.json').read_bytes(), before)

    def test_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, 'fresh'):
            tool.run(Path(tmp))


if __name__ == '__main__':
    unittest.main()
