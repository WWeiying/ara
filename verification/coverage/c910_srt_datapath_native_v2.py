"""Namespace-only successor; frozen C9101264 algorithm and scope unchanged."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / 'c910_srt_datapath_native.py'
ORIGINAL_SHA = 'e7d3cf19e46c28cf0a0290e16dafd9dca5eb695172e8249157f86ed992de90a5'
spec = importlib.util.spec_from_file_location('c910_native_private_v2', ORIGINAL)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.require(base.life.digest(ORIGINAL) == ORIGINAL_SHA, 'Frozen predecessor drift')
original_life = base.life
dependencies = {str(ORIGINAL): ORIGINAL_SHA,
                str(HERE / 'c910_srt_datapath_native.tcl'):
                '194889eb9a2a23f99fcb9731f52957e9bb8da7ea13d8c803256766710225bf36',
                str(HERE / 'test_c910_srt_datapath_native.py'):
                'bc72143ff95fd43691229cba1fd1e7a20b1efcce1e0ed6608dab8e78f06a6a1d'}


def merge_pins(left, right):
    return original_life.merge_pins(original_life.merge_pins(left, right), dependencies)


base.life = SimpleNamespace(**vars(original_life))
base.life.merge_pins = merge_pins
base.SCRIPT = Path(__file__).resolve()
base.TCL = base.SCRIPT.with_suffix('.tcl')
base.TEST = base.SCRIPT.with_name('test_c910_srt_datapath_native_v2.py')

if __name__ == '__main__':
    base.main()
