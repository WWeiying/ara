"""Exact wire/net native-type successor; reviewed C910 scope is unchanged."""
import importlib.util
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PINS = {
    str(HERE / 'c910_srt_datapath_native_v3.py'):
    '0dfb80d99c22ca116dcff79e25d3d1b2c4bc47478a31e718c88ed3b6276947a3',
    str(HERE / 'c910_srt_datapath_native_v3.tcl'):
    '2892f8cd0d9c45a4228a005ca6dca8332867f76fa9bef9eb59750660569b4ca6',
    str(HERE / 'test_c910_srt_datapath_native_v3.py'):
    '48cc5d762f18609282b57c5af85d0140e9ac92ed722ff7515ba1012f109549cf',
}
spec = importlib.util.spec_from_file_location('c910_native_private_v4',
                                             HERE / 'c910_srt_datapath_native_v3.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
base = prior.base
base.life.check(PINS)
prior.dependencies.update(PINS)
original_parse = base.parse_el


def parse_el(text, config):
    expected = {i['scope']: {s['name']: s for s in i['signals']}
                for i in config['instances']}
    scope = None
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('CHECKSUM:'):
            scope = None
        elif stripped.startswith('INSTANCE:'):
            scope = stripped.split(':', 1)[1].strip()
        elif stripped.startswith('Toggle '):
            match = re.fullmatch(r'Toggle (\w+) "net (\w+)\[(\d+):(\d+)\]"', stripped)
            if match:
                name, signature, left, right = match.groups()
                signal = expected.get(scope, {}).get(name)
                base.require(signal is not None and signal['source_type'] == 'wire' and
                             name == signature and (int(left), int(right)) ==
                             (signal['left'], signal['right']), 'Unbound native net declaration')
                line = stripped.replace('"net ', '"wire ', 1)
        lines.append(line)
    # Only the measured Verilog wire->net spelling is canonicalized; all
    # scope/checksum/name/bounds/duplicates and exact1264 gates remain intact.
    return original_parse('\n'.join(lines), config)


base.parse_el = parse_el
base.SCRIPT = Path(__file__).resolve()
base.TCL = base.SCRIPT.with_suffix('.tcl')
base.TEST = HERE / 'test_c910_srt_datapath_native_v4.py'

if __name__ == '__main__':
    prior.main()
