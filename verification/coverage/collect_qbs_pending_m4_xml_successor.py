"""Offline XML-interface successor; frozen failed collector remains untouched."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import collect_qbs_pending_m4_783 as original
import targeted_toggle_evidence_v2 as toggle

OLD_SHA = 'f717edcf5f898d85017f4b0532b13771032119af77b78904f6f638f9af6f3093'
life, require = original.life, original.require


def native_identity(run, sim, args, record, design):
    fn = original.runner.admission.native_identity
    return FunctionType(fn.__code__, dict(fn.__globals__, RUN=run),
                        fn.__name__, fn.__defaults__)(sim, args, record, design)


def raw_gain(run, record):
    require(life.digest(Path(original.__file__)) == OLD_SHA, 'Frozen original collector')
    # The frozen gain body rebinds RUN. Supply actual defining globals, not aliases.
    fn = original.runner.admission.native_identity
    admission = SimpleNamespace(**fn.__globals__)
    admission.native_identity = FunctionType(fn.__code__, dict(fn.__globals__),
                                            fn.__name__, fn.__defaults__)
    runner = SimpleNamespace(**vars(original.runner))
    runner.admission = admission
    return FunctionType(original.raw_gain.__code__,
                        dict(original.raw_gain.__globals__, runner=runner,
                             toggle=toggle))(run, record)


def collect(run, seal, out):
    require(life.digest(Path(original.__file__)) == OLD_SHA, 'Frozen original collector')
    dependencies = [Path(__file__).resolve(),
                    Path(__file__).with_name('test_qbs_pending_m4_xml_successor.py').resolve(),
                    Path(toggle.__file__).resolve()]
    pins = {str(p): life.digest(p) for p in dependencies}
    def save(path, value):
        if path.name == 'qualification.json' and value.get('status') == 'TWO_M4_FUNCTIONAL_NATIVE_CYCLE_AND_RAW_QUALIFIED_NOT_ADMITTED':
            life.check(pins)
            value = dict(value)
            value['input_pins'] = life.merge_pins(value['input_pins'], pins)
            value['offline_successor'] = dict(original_collector_sha256=OLD_SHA,
                repair='XML v2 parser and checked defining globals only',
                diagnostic_baseline=783, latest_formal_population=785,
                next_admission_population=786, admission_rebase_required=True)
        life.save(path, value)
    proxy = SimpleNamespace(**vars(life))
    proxy.save = save
    return FunctionType(original.collect.__code__,
                        dict(original.collect.__globals__, raw_gain=raw_gain,
                             life=proxy))(run, seal, out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--prepared-seal', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(collect(a.run.resolve(), a.prepared_seal, a.output.resolve())))
