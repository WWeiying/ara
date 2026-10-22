"""Read-only replay of the complete FMA612 native verifier and sealed snapshot."""
import argparse
import importlib.util
from pathlib import Path
from types import FunctionType, SimpleNamespace


def verify(output, seal):
    helper = Path(__file__).with_name('fma_expanded_native_04.py')
    spec = importlib.util.spec_from_file_location('private_fma612_readonly', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = output / 'capture-result.json'
    expected = module.life.read_bound(path, seal)
    module.life.check(expected['pins'])
    writes = []

    def compare(destination, value):
        module.require(destination == path and value == expected,
                       'Verifier output differs from sealed complete result')
        writes.append(destination)

    def retained_snapshot(source, destination):
        module.require(source == output / 'service.log' and
                       destination == output / 'service-output-before-seal.log',
                       'Unexpected snapshot operation')
        module.require(module.life.digest(destination) == expected['pins'][str(destination)],
                       'Pre-seal stdout snapshot drift')

    namespace = dict(module.verify.__globals__,
                     shutil=SimpleNamespace(copyfile=retained_snapshot))
    replay = FunctionType(module.verify.__code__, namespace)
    save = module.life.save
    module.life.save = compare
    try:
        replay(output, expected['config_seal'])
    finally:
        module.life.save = save
    module.require(writes == [path], 'Substantive verifier did not finish exactly once')
    module.require(module.life.digest(path) == seal, 'Sealed result changed')
    return expected['status']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    args = parser.parse_args()
    print(verify(args.output.resolve(), args.seal))
