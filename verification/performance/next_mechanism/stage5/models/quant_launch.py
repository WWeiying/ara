"""Extend the sealed model launcher with source-bound quantized-KV accounting.

No guest input or original receipt is rewritten. Both the original checker and
the additional checker remain pinned in the launch binding.
"""
import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve()
LAUNCH = HERE.with_name('launch_assets.py')
LAUNCH_SHA = '9608b25aebd02f0bb38e6f99e699c5b0ff768c8f2813e3cc96ead2d9e0d30c3f'
CHECK = HERE.with_name('quant_check.py')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False, add_help=False)
    parser.add_argument('--quant-launch-sha256', required=True)
    parser.add_argument('--quant-checker-sha256', required=True)
    args, rest = parser.parse_known_args()
    launcher = load(LAUNCH, 'sealed_observation_launcher')
    launcher.require(launcher.sha(LAUNCH) == LAUNCH_SHA, 'Original launcher drift')
    launcher.require(launcher.sha(HERE) == args.quant_launch_sha256 and
                     launcher.sha(CHECK) == args.quant_checker_sha256,
                     'Unreviewed quantized-KV checker extension')
    launcher.require(rest and rest[0] == 'run', 'Execution extension only')
    original_checked = launcher.checked

    def checked(*values):
        base, pins = original_checked(*values)
        original_load = base.load

        def load_checker(path, name):
            if Path(path) == launcher.CHECK:
                return original_load(CHECK, name)
            return original_load(path, name)

        base.load = load_checker
        base.merge(pins, {str(HERE): args.quant_launch_sha256,
                          str(CHECK): args.quant_checker_sha256})
        return base, pins

    launcher.checked = checked
    sys.argv = [str(LAUNCH), *rest]
    return launcher.main()


if __name__ == '__main__':
    raise SystemExit(main())
