import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent


def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class SuccessorTests(unittest.TestCase):
    def test_frozen_protocol_package(self):
        successor,old=load('precheck_v2'),load('precheck')
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w') as tar:
            item=tarfile.TarInfo('verification/ara_verify/__init__.py')
            body=b'# synthetic test package\n'
            item.size=len(body)
            tar.addfile(item,io.BytesIO(body))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            old.OUT=root
            image=root/'image'
            image.mkdir()
            (image/'source-pins.json').write_text('{}')
            elf=root/'program.elf'
            elf.write_bytes(b'not executed')
            pins=root/'program-pins.json'
            pins.write_text(json.dumps({str(elf):old.sha(elf)}))
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps(dict(scope='host test',cases=[dict(id='case',
                elf=str(elf),elf_sha256=old.sha(elf),source_pins=str(pins),checker=['/bin/false'],
                timeout_seconds=1)])))
            output=root/'power_precheck_20261117_test_v2'
            with mock.patch.object(successor,'helper',return_value=old), \
                 mock.patch.object(successor.subprocess,'check_output',return_value=data.getvalue()):
                successor.prepare(output,image,manifest,4)
            plan=json.loads((output/'plan.json').read_text())
            self.assertTrue((Path(plan['protocol_pythonpath'])/'ara_verify/__init__.py').is_file())
            old.verify(json.loads((output/'source-pins.json').read_text()))
            self.assertFalse((output/'attempt.json').exists())

    def test_frozen_execution_required(self):
        with self.assertRaisesRegex(ValueError,'Frozen'):
            load('precheck_v2').execute(Path('/tmp/not-a-worker'))

    def test_reconstruction_label_not_silently_renamed(self):
        states=load('precheck_v2').ALLOWED
        self.assertIn('RECONSTRUCTED_BASELINE_RTL_BUILT_NOT_EXECUTED',states)
        self.assertNotIn('PASS',states)


if __name__=='__main__':
    unittest.main()
