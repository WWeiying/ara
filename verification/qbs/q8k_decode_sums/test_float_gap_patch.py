"""Round-trip the distributable patch without touching the runtime checkout."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from compile_float_gap_candidate import SOURCE, ROOT, candidate

PATCH=ROOT/'software/qbs/integrations/llama-float-gap-context.patch'
REL=Path('ggml/src/ggml-cpu/arch/riscv/qbs.cpp')


class PatchTest(unittest.TestCase):
    def test_matches_validated_candidate_and_reverses(self):
        original=SOURCE.read_text()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/REL
            source.parent.mkdir(parents=True)
            source.write_text(original)
            for flags in (['--check'],[]):
                result=subprocess.run(['git','apply',*flags,str(PATCH)],cwd=root,
                                      capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(source.read_text(),candidate(original))
            repeat=subprocess.run(['git','apply','--check',str(PATCH)],cwd=root,
                                  capture_output=True,text=True,timeout=10)
            self.assertNotEqual(repeat.returncode,0)
            result=subprocess.run(['git','apply','--reverse',str(PATCH)],cwd=root,
                                  capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(source.read_text(),original)
        self.assertEqual(SOURCE.read_text(),original)


if __name__=='__main__':unittest.main()
