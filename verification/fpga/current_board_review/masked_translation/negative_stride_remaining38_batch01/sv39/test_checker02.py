import ast
import json
import tempfile
import unittest
from pathlib import Path
import checker
import checker02


class StaticOwnership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=checker.HERE/'software01/group00'
        cls.s=json.loads((cls.d/'spike.symbols.json').read_text())
        cls.code=checker.disassemble((cls.d/'spike.dis').read_text())
        cls.cases=[c['parameters'] for c in json.loads((cls.d/'cases.json').read_text())]

    def attempt(self,module,code):
        with tempfile.TemporaryDirectory() as d:
            raw=Path(d)/'synthetic.empty';raw.touch()
            with self.assertRaises(ValueError) as e:
                module.analyze(raw,self.s,code,self.d/'spike.elf',self.cases,8000000)
        return str(e.exception)

    def test_original_false_rejection_preserved(self):
        self.assertEqual(self.attempt(checker,self.code),'Static RVV ownership')

    def test_real_code_passes_static_not_empty_trace(self):
        self.assertEqual(self.attempt(checker02,self.code),'case0 action order []')

    def test_extra_rvv_outside_owner_rejected(self):
        code=dict(self.code);code[0x90000000]=0x30803c57
        self.assertEqual(self.attempt(checker02,code),'Static RVV ownership')

    def test_retry_wrong_encoding_rejected(self):
        code=dict(self.code);code[0x80000ffc]=0x30803c57
        self.assertEqual(self.attempt(checker02,code),'Exact archived wrapper retry vset encoding')

    def test_extra_retry_instruction_rejected(self):
        code=dict(self.code);code[0x80001000]=0x0082f2d7
        self.assertEqual(self.attempt(checker02,code),'Static RVV ownership')

    def test_all_oracle_functions_unchanged(self):
        def funcs(p):
            return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)}
        before=funcs(checker.HERE/'checker.py');after=funcs(checker.HERE/'checker02.py')
        self.assertEqual(set(before),set(after))
        self.assertEqual({k:v for k,v in before.items() if k!='analyze'},{k:v for k,v in after.items() if k!='analyze'})


if __name__=='__main__':unittest.main(verbosity=2)
