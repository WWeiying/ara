"""Isolated native04: sealed03 full inventory with reviewed directional EL parser."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import capture_system_rvfi788_v3 as previous
import system_rvfi_native_el as parser

life, require = previous.life, previous.require
core, mapping = previous.core, previous.mapping
HERE = Path(__file__).resolve().parent
HOOK = previous.HOOK
BINDING, BINDING_SHA = previous.BINDING, previous.BINDING_SHA
ORIGIN = life.OUT / 'system-rvfi788-native-agent-20261007-03'
FIRST_SHA = '6839b7592de2519b81477bfa851f6e4829993c35a4221de36270de3907397c5f'
CONFIG_SHA = 'c610434fd6f2d8d20487c01bd61160487e5260b8b646a861b529f8ae9b2a9480'
records, inventory = parser.records, previous.inventory


def predecessor():
    c = life.read_bound(ORIGIN/'config.json', CONFIG_SHA)
    life.check(c['pins'])
    require(life.digest(ORIGIN/'first.el') == FIRST_SHA, 'Preserved03 native export differs')
    require(len(records((ORIGIN/'first.el').read_text(), c)) == 788, 'Preserved03 exact native parsing differs')
    require(len(inventory(ORIGIN, c, 'before')) == 1206 and
            (ORIGIN/'cleanup-empty.el').read_bytes() == b'', 'Preserved03 before/cleanup differs')
    return c


def prepare(out):
    predecessor()
    deps = [Path(__file__).resolve(), HERE/'test_capture_system_rvfi788_v4.py',
            Path(previous.__file__).resolve(), previous.HOOK,
            Path(parser.__file__).resolve(), HERE/'test_system_rvfi_native_el.py',
            HERE/'test_capture_system_rvfi788_v3.py']
    pins = {str(p): life.digest(p) for p in deps}
    pins = life.merge_pins(pins, {str(ORIGIN/'config.json'): CONFIG_SHA, str(ORIGIN/'first.el'): FIRST_SHA})

    def save(path, value):
        if path == out/'config.json':
            value['pins'].update(life.merge_pins(value['pins'], pins))
            value.update(native_parser='complete_whole_or_both_sole_bit_directions',
                         preserved03_first_sha256=FIRST_SHA, predecessor03_config_sha256=CONFIG_SHA)
            life.check(value['pins'])
        life.save(path, value)

    private = SimpleNamespace(**dict(vars(life), save=save))
    worker = FunctionType(previous.prepare.__code__, dict(previous.prepare.__globals__, life=private, __file__=__file__))
    worker(out)


def verify(out, seal):
    c = life.read_bound(out/'config.json', seal)
    require(c['native_parser'] == 'complete_whole_or_both_sole_bit_directions' and
            c['preserved03_first_sha256'] == FIRST_SHA and c['predecessor03_config_sha256'] == CONFIG_SHA,
            'Reviewed04 parser/provenance differs')
    worker = FunctionType(previous.verify.__code__, dict(previous.verify.__globals__, records=records))
    worker(out, seal)


def run(out, seal):
    worker = FunctionType(core.scalar.launch.run.__code__, dict(core.scalar.launch.run.__globals__, verify=verify))
    worker(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify', 'el', 'inventory'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--file', choices=('first.el', 'second.el'))
    p.add_argument('--stage', choices=('before', 'selected', 'reset', 'reloaded', 'final'))
    a = p.parse_args()
    out = a.output.absolute()
    if a.mode == 'prepare':
        prepare(out)
    elif a.mode in ('el', 'inventory'):
        c = json.loads((out/'config.json').read_bytes())
        life.check(c['pins'])
        if a.mode == 'el':
            require(a.file, 'EL required')
            print('EXACT788 '+str(len(records((out/a.file).read_text(), c))))
        else:
            require(a.stage, 'Stage required')
            print('SEALED_FULL1206 '+str(len(inventory(out, c, a.stage))))
    else:
        require(a.seal, 'Config seal required')
        (run if a.mode == 'run' else verify)(out, a.seal)
