"""Replay the original substantive cast verifier without overwriting its seal."""
import argparse
import importlib.util
from pathlib import Path


def verify(output, seal):
    helper = Path(__file__).with_name('capture_cast168_native_typed.py')
    spec = importlib.util.spec_from_file_location('private_cast168_readonly', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result_path = output / 'capture-result.json'
    expected = module.life.read_bound(result_path, seal)
    module.life.check(expected['pins'])
    writes = []

    def compare(path, value):
        module.require(path == result_path, 'Unexpected verifier output')
        module.require(value == expected, 'Substantive verifier result differs from seal')
        writes.append(path)

    save = module.life.save
    module.life.save = compare
    try:
        module.v2.inspect(output, expected['config_seal'])
    finally:
        module.life.save = save
    module.require(writes == [result_path], 'Verifier did not complete exactly once')
    module.require(module.life.digest(result_path) == seal, 'Sealed result changed')
    return expected['status']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    args = parser.parse_args()
    print(verify(args.output.resolve(), args.seal))
