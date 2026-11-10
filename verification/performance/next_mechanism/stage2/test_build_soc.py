import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('stage2_build_soc', Path(__file__).with_name('build_soc.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class TestStage2Sources(unittest.TestCase):
    def test_borrower_inserted_before_vmfpu_once(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            borrow = source / build.BORROW
            borrow.parent.mkdir(parents=True)
            borrow.write_text('module borrower; endmodule\n')
            marker = str(source / 'hardware/src/lane/vmfpu.sv')
            text = marker + '\n'
            updated = build.insert_borrow(text, source)
            self.assertEqual(updated.splitlines(), [str(borrow), marker])
            for invalid in (updated, text * 2, ''):
                with self.assertRaises(ValueError):
                    build.insert_borrow(invalid, source)

    def test_missing_revision_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            with self.assertRaises(ValueError):
                build.insert_borrow(str(source / 'hardware/src/lane/vmfpu.sv') + '\n', source)


if __name__ == '__main__':
    unittest.main()
