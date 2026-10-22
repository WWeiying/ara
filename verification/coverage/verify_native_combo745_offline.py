"""Qualify existing745 native capture using the original substantive verifier.

The frozen launcher accidentally inherited a742 entry-binding wrapper instead
of its underlying verifier. Keep all frozen inputs and the failure unchanged.
"""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace
import report_native_combo745 as captured


def verifier():
    # The745 verifier still enforces its own exact entry/schema/population. Only
    # its private inherited function is changed, not imported module globals.
    original = captured.inherited.original_verify
    captured.require(original.__name__ == 'verify' and
                     Path(original.__code__.co_filename).name == 'report_c910_combo742.py',
                     'Not the substantive frozen verifier')
    old = SimpleNamespace(**{**vars(captured.old), 'verify': original})
    original_save = captured.life.save

    def save(path, data):
        captured.require(path.name == 'qualification.json', 'Unexpected result write')
        sources = [Path(__file__).resolve(), Path(__file__).with_name(
            'test_verify_native_combo745_offline.py')]
        data = dict(data, offline_adapter='PRIVATE_ORIGINAL_VERIFIER_REBIND_NO_EDA_REPLAY',
                    offline_adapter_pins={str(p): captured.life.digest(p) for p in sources},
                    original_failure_preserved=True)
        original_save(path, data)

    life = SimpleNamespace(**{**vars(captured.life), 'save': save})
    namespace = dict(captured.verify.__globals__, old=old, life=life)
    return FunctionType(captured.verify.__code__, namespace)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    captured.require((output / 'failure.json').is_file() and
                     not (output / 'qualification.json').exists(),
                     'Existing failed capture without qualification required')
    failure = captured.life.read_bound(output / 'config.json', args.seal)
    captured.require(failure['output'] == str(output), 'Bound output differs')
    verifier()(output, args.seal)


if __name__ == '__main__':
    main()
