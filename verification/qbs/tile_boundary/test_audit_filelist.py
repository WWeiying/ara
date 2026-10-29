import tempfile
import unittest
from pathlib import Path
from audit_filelist import audit


class FilelistAuditTest(unittest.TestCase):
    def test_reordering_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a', Path(tmp)/'b'
            a.write_text('+define+A=1\n+define+B=2\n/source.sv\n')
            b.write_text('+define+B=2\n+define+A=1\n/source.sv\n')
            self.assertEqual(audit(a, b)['state'], 'ORDER_AUDIT_PASS')
            b.write_text('+define+B=3\n+define+A=1\n/source.sv\n')
            with self.assertRaises(ValueError):
                audit(a, b)

    def test_include_collision_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('one', 'two'):
                (root/name).mkdir()
                (root/name/'header.svh').write_text(name)
            a, b = root/'a', root/'b'
            dirs = [f'+incdir+{root/name}\n' for name in ('one', 'two')]
            a.write_text(''.join(dirs) + '/source.sv\n')
            b.write_text(''.join(reversed(dirs)) + '/source.sv\n')
            self.assertEqual(audit(a, b)['state'], 'ORDER_AUDIT_NEEDS_INCLUDE_REVIEW')
