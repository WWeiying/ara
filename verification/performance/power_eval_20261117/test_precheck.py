import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE/(name+'.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class PrecheckTests(unittest.TestCase):
    def test_digest_and_drift(self):
        m = module('precheck')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'input'
            p.write_text('first')
            pins = {str(p):m.sha(p)}
            m.verify(pins)
            p.write_text('second')
            with self.assertRaisesRegex(ValueError,'Input drift'):
                m.verify(pins)

    def test_prepare_no_execution(self):
        m = module('precheck')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            m.OUT = root
            image = root/'image'
            image.mkdir()
            (image/'source-pins.json').write_text('{}')
            elf = root/'case.elf'
            elf.write_bytes(b'not-executed')
            pins = root/'case-pins.json'
            pins.write_text(json.dumps({str(elf):m.sha(elf)}))
            case = dict(id='case',elf=str(elf),elf_sha256=m.sha(elf),source_pins=str(pins),
                        checker=['/bin/false'],timeout_seconds=1)
            manifest = root/'manifest.json'
            manifest.write_text(json.dumps(dict(scope='test',cases=[case])))
            output = root/'power_precheck_20261117_test'
            m.prepare(output,image,manifest,4)
            self.assertEqual(json.loads((output/'status.json').read_text())['state'],'PREPARED')
            self.assertFalse((output/'attempt.json').exists())
            with self.assertRaises(ValueError):
                m.prepare(output,image,manifest,4)

    def test_parallel_limit(self):
        m = module('precheck')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            m.OUT = root
            for parallel in (0,5,100):
                with self.assertRaisesRegex(ValueError,'Parallel'):
                    m.prepare(root/'power_precheck_20261117_test',root/'image',root/'manifest',parallel)

    def test_worker_must_be_frozen(self):
        m = module('precheck')
        with self.assertRaisesRegex(ValueError,'Frozen'):
            m.execute(Path('/tmp/not-the-frozen-worker'))


if __name__ == '__main__':
    unittest.main()
