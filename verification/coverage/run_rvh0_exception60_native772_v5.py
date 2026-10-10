"""Run the source-bound semantic V5 check with frozen authorization gates."""
import argparse
from pathlib import Path
from types import FunctionType

import run_rvh0_exception60_native772_v2 as predecessor
import rvh0_exception60_native772_v5 as qualification


namespace = dict(vars(predecessor), qualification=qualification)
worker = FunctionType(predecessor.worker.__code__, namespace)
namespace['worker'] = worker
run = FunctionType(predecessor.run.__code__, namespace)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    parser.add_argument('--parent-reviewed-seal', required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.seal, args.parent_reviewed_seal)
