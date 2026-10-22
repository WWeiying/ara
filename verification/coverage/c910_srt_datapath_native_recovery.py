"""Recover exact1264 roundtrip from actual03 native EL; no GUI signal clicks."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINS = {
    str(HERE / 'c910_srt_datapath_native_v4.py'):
    '764c7920d2961ec07c90c10dc2d786140061ca213aa287a4941672dc2028e547',
    str(HERE / 'c910_srt_datapath_native_v4.tcl'):
    'fb7dea0fca77de3f2c07713dfa19f009c39dbbbce72a5c1723e15b4ae6b793aa',
    str(HERE / 'test_c910_srt_datapath_native_v4.py'):
    '852297a1e1a716fcaa55f6f4da84927d950fe9656f16beac52de8811cc6af511',
}
spec = importlib.util.spec_from_file_location('c910_native_private_recovery',
                                             HERE / 'c910_srt_datapath_native_v4.py')
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
base = parent.base
base.life.check(PINS)
parent.prior.dependencies.update(PINS)
base.SCRIPT = Path(__file__).resolve()
base.TCL = base.SCRIPT.with_suffix('.tcl')
base.TEST = HERE / 'test_c910_srt_datapath_native_recovery.py'
ORIGIN = base.life.OUT / 'c910-srt-native1264-load-agent-20261007-03'
ORIGIN_SEAL = 'dd45bf48c516b7eebe9b63caa5a17a85bd7c8acab4a9b410d355aa7b92c1b49d'


def prepare(out):
    origin = base.life.read_bound(ORIGIN / 'config.json', ORIGIN_SEAL)
    base.life.check(origin['pins'])
    first = parent.parse_el((ORIGIN / 'first.el').read_text(), origin)
    base.require(first == parent.parse_el((ORIGIN / 'candidate.el').read_text(), origin),
                 'Native recovery set differs')
    parent.prior.calibration_kind((ORIGIN / 'calibration.el').read_text(), origin)
    base.require((ORIGIN / 'calibration-reset-empty.el').read_bytes() == b'',
                 'Origin calibration not reset')
    pins = {str(ORIGIN / name): base.life.digest(ORIGIN / name)
            for name in ('config.json', 'first.el', 'candidate.el', 'calibration.el',
                         'calibration-reset-empty.el')}
    save = base.life.save

    def bound_save(path, data):
        if path == out / 'config.json':
            data = dict(data)
            base.require(data['instances'] == origin['instances'], 'Recovery shape differs')
            data['pins'] = base.life.merge_pins(data['pins'], pins)
            data['method'] = 'ACTUAL_NATIVE03_FIRST_RECOVERY_NO_SIGNAL_SELECTION'
            data['native_origin'] = str(ORIGIN)
            data['native_origin_seal'] = ORIGIN_SEAL
        save(path, data)

    base.life.save = bound_save
    try:
        parent.prior.prepare(out)
    finally:
        base.life.save = save
    for name in ('candidate.el', 'calibration.el', 'calibration-reset-empty.el'):
        with (out / name).open('xb') as stream:
            stream.write((ORIGIN / name).read_bytes())


base.prepare = prepare

if __name__ == '__main__':
    base.main()
