#!/usr/bin/env python3
"""Gap55 successor with the exact original AKV seal enforced at admission."""
from pathlib import Path

import run_gap55_checked_batch as previous

SCRIPT = Path(__file__).resolve()
PREVIOUS = Path(previous.__file__).resolve()
CATALOG = (
    ('app:qbs_gap51_payload_matrix', False, 'run_gap51_payload_checked_extension'),
    ('app:akv_gap54_skew_context', False, 'run_gap54_akv_sealed_extension'),
)


def bind_parent(validate, original_bind):
    validate = original_bind(validate)

    def checked(selection):
        inputs = previous.previous.evidence.Evidence()
        inputs.pin(PREVIOUS)
        proof, rows, cases = validate(selection)
        proof.hashes(inputs.files)
        return proof, rows, cases

    return checked


def main():
    original_bind = previous.bind_previous
    previous.SCRIPT = SCRIPT
    previous.CATALOG = CATALOG
    previous.bind_previous = lambda validate: bind_parent(validate, original_bind)
    return previous.main()


if __name__ == '__main__':
    raise SystemExit(main())
