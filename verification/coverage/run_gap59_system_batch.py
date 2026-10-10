#!/usr/bin/env python3
"""Admit the reviewed Sv39 successor on a completed, compatible corpus."""
from pathlib import Path

import run_gap48_checked_batch as previous

SCRIPT = Path(__file__).resolve()
PREVIOUS = Path(previous.__file__).resolve()
CATALOG = (
    ('rvv:sv39_gap52_superpage_sfence_pmp0', False,
     'run_gap52_system_checked_extension'),
)


def bind_previous(validate):
    def checked(selection):
        inputs = previous.evidence.Evidence()
        inputs.pin(PREVIOUS)
        proof, rows, cases = validate(selection)
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
