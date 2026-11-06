from pathlib import Path
import tempfile
import unittest

from audit import digest
from build_rms_norm_native import model_agreement,link_archives


class RMSNormBuildTests(unittest.TestCase):
    def test_model_conflicts_reject_even_when_previously_pinned(self):
        model_agreement({'/header.h':'same','/unrelated':'x'},{'/header.h':'same','/unused':'y'})
        with self.assertRaisesRegex(ValueError,'Model dependency conflict'):
            model_agreement({'/header.h':'already-pinned'},{'/header.h':'model-source'})

    def test_actual_runtime_selection_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'libc.a';path.write_bytes(b'sealed-archive')
            extra=Path(tmp)/'libother.a';extra.write_bytes(b'other')
            expected={str(path):digest(path)}
            self.assertEqual(link_archives('LOAD '+str(path)+'\n',expected),[str(path)])
            for text in ('',f'LOAD {extra}\n',f'LOAD {path}\nLOAD {extra}\n'):
                with self.assertRaises(ValueError):link_archives(text,expected)
            path.write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError,'Runtime archive drift'):
                link_archives('LOAD '+str(path)+'\n',expected)


if __name__=='__main__':unittest.main()
