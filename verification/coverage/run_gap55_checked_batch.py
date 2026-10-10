#!/usr/bin/env python3
"""Admit new payload and AKV tests without changing the sealed gap48 runner."""
from pathlib import Path

import run_gap48_checked_batch as previous

SCRIPT = Path(__file__).resolve()
PREVIOUS = Path(previous.__file__).resolve()
CATALOG = (
    ('app:qbs_gap51_payload_matrix', False, 'run_gap51_payload_checked_extension'),
    ('app:akv_gap54_skew_context', False, 'run_gap54_akv_checked_extension'),
)


def bind_previous(validate):
    def checked(selection):
        inputs = previous.evidence.Evidence()
        inputs.pin(PREVIOUS)
        proof, rows, cases = validate(selection)
        # Bind the reused admission implementation as well as this entry point.
        proof.hashes(inputs.files)
        return proof, rows, cases

    return checked


def main():
    previous.SCRIPT = SCRIPT
    previous.CATALOG = CATALOG
    install_previous = previous.install

    def install(modules):
        install_previous(modules)
        previous.evidence.validate = bind_previous(previous.evidence.validate)

    previous.install = install
    return previous.main()


if __name__ == '__main__':
    raise SystemExit(main())
