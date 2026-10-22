"""Successor fixes missing terminal watch; same ELF, image and time budget."""
import argparse
from pathlib import Path
from types import FunctionType
import run_operand_mask_data as previous

OUT = previous.life.OUT / 'operand-mask-data-old-image-parent-20261007-02'


def command(output):
    result = previous.command(output)
    address = previous.ELF.parent / 'preflight.json'
    pre = previous.json.loads(address.read_bytes())
    terminal = pre['symbols']['tohost']
    previous.require(type(terminal) is int and terminal == 0x80001000,
                     'Exact preflight terminal symbol required')
    result.append('+COMMIT_TOHOST=%x' % terminal)
    return result


def namespace():
    return dict(vars(previous), OUT=OUT, command=command,
                __file__=str(Path(__file__).resolve()))


def prepare():
    ns = namespace()
    FunctionType(previous.prepare.__code__, ns)()


def run(seal):
    ns = namespace()
    FunctionType(previous.run.__code__, ns)(seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run'))
    p.add_argument('--seal')
    args = p.parse_args()
    if args.mode == 'prepare':
        prepare()
    else:
        previous.require(args.seal, 'Prepared seal required')
        run(args.seal)
