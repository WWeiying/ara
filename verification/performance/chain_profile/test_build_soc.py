import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('chain_build_soc', Path(__file__).with_name('build_soc.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class TestFrozenGraph(unittest.TestCase):
    def test_freeze_and_configuration(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'src.sv').write_text('module test; endmodule\n')
            text = '\n'.join(('+define+SIM_L2_SIZE_BYTES=2097152', '+define+NR_LANES=4',
                '+define+VLEN=1024', '+define+ARA_QBS_ENABLE=1', '+define+ARA_AKV_ENABLE=1',
                '+define+ARA_AKV_V2_ENABLE=1', '+define+FOR_VERIFY',
                '+incdir+/old/source', '/old/source/src.sv')) + '\n'
            frozen = build.freeze_filelist(text, Path('/old/source'), root)
            self.assertIn('+define+SIM_L2_SIZE_BYTES=16777216', frozen)
            self.assertNotIn('/old/source', frozen)
            for changed in (text.replace('NR_LANES=4', 'NR_LANES=8'),
                            text.replace('2097152', '4194304'),
                            text + '/outside/source.sv\n',
                            text + '+define+IDEAL_DISPATCHER\n'):
                with self.assertRaises(ValueError):
                    build.freeze_filelist(changed, Path('/old/source'), root)


if __name__ == '__main__':
    unittest.main()
