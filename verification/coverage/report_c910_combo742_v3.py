"""Procedure-scope-only successor to the frozen combined742 launcher."""
import argparse
import importlib.util
from pathlib import Path
from types import FunctionType

HERE = Path(__file__).resolve().parent
PINS = {
    str(HERE / 'report_c910_combo742_v2.py'):
    'c9768c65217980d5dc1fb0addd8c06969869cec2d1e1effd143352fdbdddf664',
    str(HERE / 'test_report_c910_combo742_v2.py'):
    '1dbbc17d627b7189b597e26f73d96b5b7e8252218819dbfe6840c58e06e32708',
    str(HERE / 'qualify_dwc_points742.tcl'):
    'cfbda9055688a5aa084784078e9e4b816239addeffd0ab5f51bcfb9986405d95',
}
spec = importlib.util.spec_from_file_location('combo742_private_v3', HERE / 'report_c910_combo742_v2.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
life = prior.life
life.check(PINS)
prior.prior.TCL = Path(__file__).resolve().with_suffix('.tcl')
original_verify = prior.prior.verify


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    prior.prior.require(c['output'] == str(out) and
                        c['successor_entry'] == str(Path(__file__).resolve()), 'Wrong bound report output/entry')
    original_verify(out, seal)


prior.prior.verify = verify


def prepare(out, dwc_out):
    save = prior.prior.life.save
    pins = dict(PINS)
    for path in (Path(__file__).resolve(), HERE / 'test_report_c910_combo742_v3.py'):
        pins[str(path)] = life.digest(path)

    def bound_save(path, data):
        if path == out / 'config.json':
            data = dict(data, pins=life.merge_pins(data['pins'], pins),
                        successor_entry=str(Path(__file__).resolve()),
                        primitive_loading='GLOBAL_PROCEDURE_ONLY_NO_STANDALONE_NO_FX_OVERWRITE')
        save(path, data)

    prior.prior.life.save = bound_save
    try:
        return prior.prepare(out, dwc_out)
    finally:
        prior.prior.life.save = save


def run(out, seal):
    namespace = dict(prior.run.__globals__, __file__=__file__)
    FunctionType(prior.run.__code__, namespace)(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--dwc-output', type=Path)
    a = p.parse_args()
    if a.mode == 'prepare':
        prior.prior.require(a.dwc_output, 'Qualified DWC required')
        prepare(a.output.absolute(), a.dwc_output.absolute())
    else:
        prior.prior.require(a.seal, 'Exact seal required')
        (run if a.mode == 'run' else prior.prior.verify)(a.output.absolute(), a.seal)
