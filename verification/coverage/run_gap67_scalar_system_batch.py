#!/usr/bin/env python3
"""Compose the reviewed Zcb-rejection and LR-only tests on one frozen corpus."""
from pathlib import Path
import sys

import run_gap48_checked_batch as previous

SCRIPT = Path(__file__).resolve()
PREVIOUS = Path(previous.__file__).resolve()
ROOT = SCRIPT.parents[2]
ZCB = ROOT / 'verification/out/gap63-zcb-preflight-20261004-01'
CATALOG = (
    ('rvv:scalar_gap63_zcb_reject', False, 'run_gap63_checked_extension'),
    ('rvv:lr_gap64_wd_drain_pmp0', False, 'run_gap64_lr_checked_extension'),
)
ADAPTER_PATHS = {
    'run_gap63_checked_extension': ZCB / 'run_gap63_checked_extension.py',
    'run_gap64_lr_checked_extension': SCRIPT.parent / 'run_gap64_lr_checked_extension.py',
}


def bind_previous(validate):
    def checked(selection):
        inputs = previous.evidence.Evidence()
        inputs.pin(PREVIOUS)
        proof, rows, cases = validate(selection)
        proof.hashes(inputs.files)
        return proof, rows, cases
    return checked


def validate_modules(modules):
    for module in modules:
        expected = ADAPTER_PATHS.get(module.__name__)
        previous.require(expected is not None and Path(module.__file__).resolve() == expected,
                         'unexpected adapter source location')


def main():
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ZCB))
    previous.SCRIPT = SCRIPT
    previous.CATALOG = CATALOG
    install_previous = previous.install

    def install(modules):
        validate_modules(modules)
        install_previous(modules)
        previous.evidence.validate = bind_previous(previous.evidence.validate)

    previous.install = install
    return previous.main()


if __name__ == '__main__':
    raise SystemExit(main())
