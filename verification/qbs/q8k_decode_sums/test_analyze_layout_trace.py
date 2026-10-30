from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analyze_layout_trace import SITES
from analyze_trace import analyze


class LayoutTraceTest(unittest.TestCase):
    def test_exact_candidate_mapping(self):
        rows = ['cycle,event,arch_seq,vid,insn,vl,eew,be']
        seq = 0
        for insn, (_, count) in SITES.items():
            for _ in range(count):
                seq += 1
                for delta, event in enumerate(('alloc', 'write', 'done')):
                    rows.append(f'{seq * 4 + delta},{event},{seq},0,{insn},16,1,03')
        result = analyze(('\n'.join(rows) + '\n').encode(), SITES)
        for name, count in SITES.values():
            self.assertEqual(result[name]['architectural_count'], count)
            self.assertEqual(result[name]['backend_uops'], count)
            self.assertEqual(result[name]['enabled_write_bytes'], 2 * count)
        # An older candidate's opcode must not silently satisfy the new mapping.
        wrong = '\n'.join(rows).replace('c6118157', 'c61100d7').encode()
        with self.assertRaises(ValueError):
            analyze(wrong, SITES)

    def test_reject_wrong_elf_without_creating_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elf = root / 'wrong.elf'
            elf.write_bytes(b'not the reviewed ELF')
            output = root / 'report'
            run = subprocess.run([
                sys.executable, str(Path(__file__).with_name('analyze_layout_trace.py')),
                '--elf', str(elf), '--trace', str(root / 'missing.csv'),
                '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertIn('ELF differs', run.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
