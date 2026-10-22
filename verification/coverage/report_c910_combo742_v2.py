"""STDOUT-only launcher successor; exact742 native union/hook unchanged."""
import argparse
import importlib.util
from pathlib import Path
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
PINS = {
    str(HERE / 'report_c910_combo742.py'):
    '077fdee26fa41d1e46a256d6d779fa673b50e9a17cde1e4463d6e1ec0e6c2b2f',
    str(HERE / 'report_c910_combo742.tcl'):
    'ab06b4a58879d18d7a6dfc9c686e276a4779da16696929abed1e4a54141b764c',
    str(HERE / 'test_report_c910_combo742.py'):
    '14b55e664bfd46ecc146c1a39ebe5406eeac732f31a6830e9dc88856f5c2d264',
}
spec = importlib.util.spec_from_file_location('combo742_private_v2', HERE / 'report_c910_combo742.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
prior.life.check(PINS)
life = prior.life
prior.life = SimpleNamespace(**vars(life))


def prepare(out, dwc_out):
    save = prior.life.save
    pins = dict(PINS)
    for path in (Path(__file__).resolve(), HERE / 'test_report_c910_combo742_v2.py'):
        pins[str(path)] = life.digest(path)

    def bound_save(path, data):
        if path == out / 'config.json':
            data = dict(data, pins=life.merge_pins(data['pins'], pins),
                        successor_entry=str(Path(__file__).resolve()),
                        predecessor_failure='PRE_DVE_SUBPROCESS_STDOUT_ADAPTER_OMISSION')
        save(path, data)

    prior.life.save = bound_save
    try:
        return prior.prepare(out, dwc_out)
    finally:
        prior.life.save = save


def subprocess_namespace(**kwargs):
    return SimpleNamespace(**{**vars(prior.base.subprocess), **kwargs})


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    prior.require(c['successor_entry'] == str(Path(__file__).resolve()), 'Wrong frozen entry')
    namespace = dict(prior.run.__globals__, SimpleNamespace=subprocess_namespace)
    FunctionType(prior.run.__code__, namespace)(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--dwc-output', type=Path)
    a = p.parse_args()
    if a.mode == 'prepare':
        prior.require(a.dwc_output, 'Qualified DWC03 required for single unified report')
        prepare(a.output.absolute(), a.dwc_output.absolute())
    else:
        prior.require(a.seal, 'Exact seal required')
        (run if a.mode == 'run' else prior.verify)(a.output.absolute(), a.seal)
