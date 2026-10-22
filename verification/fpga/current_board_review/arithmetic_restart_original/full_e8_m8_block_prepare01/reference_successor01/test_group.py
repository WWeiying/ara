import ast
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent

def actual_group(vectors):
    tree=ast.parse((HERE/'reference_check.py').read_text())
    audit=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='audit')
    group=next(n for n in audit.body if isinstance(n,ast.FunctionDef) and n.name=='group')
    def require(ok,why):
        if not ok:raise ValueError(why)
    namespace=dict(vectors=vectors,require=require)
    exec(compile(ast.Module(body=[group],type_ignores=[]),'actual_nested_group','exec'),namespace)
    return namespace['group']

class GroupTests(unittest.TestCase):
    def test_exact_eight_registers(self):
        for first in (8,16,24):
            vectors={i:int.from_bytes(bytes([i])*128,'little') for i in range(first,first+8)}
            self.assertEqual(actual_group(vectors)(first),b''.join(bytes([i])*128 for i in range(first,first+8)))
    def test_high_half_difference_not_discarded(self):
        for first in (8,16,24):
            vectors={i:0 for i in range(first,first+8)}
            for offset in range(4,8):
                vectors[first+offset]=1
                actual=actual_group(vectors)(first)
                self.assertEqual(len(actual),1024)
                self.assertNotEqual(actual,b'\0'*1024)
                self.assertEqual(actual[offset*128],1)
                vectors[first+offset]=0
    def test_missing_high_register_rejected(self):
        for first in (8,16,24):
            for offset in range(4,8):
                vectors={i:0 for i in range(first,first+8) if i!=first+offset}
                with self.assertRaises(ValueError):actual_group(vectors)(first)
    def test_only_intended_observer_delta(self):
        previous=(HERE.parent/'reference_check.py').read_text()
        expected=previous.replace('range(first,first+4)','range(first,first+8)').replace(
            'HERE=Path(__file__).resolve().parent','HERE=Path(__file__).resolve().parent.parent')
        self.assertEqual((HERE/'reference_check.py').read_text().rstrip('\n'),expected.rstrip('\n'))

if __name__=='__main__':unittest.main()
