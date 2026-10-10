"""Parent-authorized background execution of the frozen RVH0 native check."""
import argparse
import inspect
from pathlib import Path

import rvh0_exception60_native772_v2 as qualification


def worker():
    host = qualification.host
    source = inspect.getsource(host.run)
    anchor = 'CVA6_PARENT_RVFI457_SEAL=seal'
    qualification.need(source.count(anchor) == 1, 'Exact mature runner environment anchor')
    namespace = dict(vars(host), ENTRY=qualification.ENTRY,
                     contract=qualification.contract, verify=qualification.inspect)
    source = source.replace(anchor, 'RVH0_EXCEPTION60_SEAL=seal')
    exec(compile(source, __file__ + ':frozen-runner-adapter', 'exec'), namespace)
    return namespace['run']


def run(output, seal, parent_reviewed_seal):
    qualification.need(seal == parent_reviewed_seal, 'Parent-reviewed exact configuration required')
    config = qualification.verify_config(output, seal)
    qualification.need(config['output'] == str(output), 'Exact independent output directory')
    qualification.need(not any((output / name).exists() for name in
                              ('execution.json', 'terminal.json', 'launcher.log', 'capture-result.json')),
                       'Fresh execution only; no automatic restart')
    worker()(output, seal)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    parser.add_argument('--parent-reviewed-seal', required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.seal, args.parent_reviewed_seal)
