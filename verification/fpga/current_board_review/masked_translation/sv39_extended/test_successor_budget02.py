#!/usr/bin/env python3
"""Host-only budget contract tests; no simulator subprocess is started."""
from pathlib import Path
import tempfile
import sys
sys.dont_write_bytecode = True
import successor_budget02 as b


def main():
    negatives = []
    def reject(name, fn):
        try:
            fn()
        except (ValueError, FileExistsError):
            negatives.append(name)
        else:
            raise AssertionError('Accepted invalid input: ' + name)

    for execute in (False, True):
        cmd = b.command(b.OUT, execute)
        b.validate_command(cmd, b.OUT, execute)
        for flag, value in [('--timeout', '1200'), ('--timeout', '1801'), ('--jobs', '2'),
                            ('--image', '/wrong/image'), ('--programs', '/wrong/programs'),
                            ('--case', 'another'), ('--out', str(b.OLD / 'run'))]:
            wrong = list(cmd)
            wrong[wrong.index(flag)+1] = value
            reject(f'{execute}:{flag}:{value}', lambda: b.validate_command(wrong, b.OUT, execute))
        reject(f'{execute}:duplicate', lambda: b.validate_command(cmd + ['--jobs', '1'], b.OUT, execute))
    contract = dict(inner_timeout_s=1800, outer_timeout_s=2100, jobs=1, output=str(b.OUT),
            elf_sha256='a0219fef355612a36370851a6a4d3011bb30991afbc19459068c3728526ea982',
            image_sha256='384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810')
    b.validate_contract(contract)
    for key, value in [('inner_timeout_s',1200), ('outer_timeout_s',1800), ('jobs',2),
                       ('output',str(b.OLD)), ('elf_sha256','changed'), ('image_sha256','changed')]:
        reject(key, lambda: b.validate_contract({**contract,key:value}))
    reject('unauthorized', lambda: b.worker(False))
    with tempfile.TemporaryDirectory(prefix='budget02-host-') as tmp:
        path = Path(tmp) / 'exclusive.json'
        b.su.save(path, {'owner':1})
        reject('duplicate-owner', lambda: b.su.save(path, {'owner':2}))
        reject('hash-drift', lambda: b.su.verify_pins({str(path):'wrong'}))
    b.su.save(b.TESTS, dict(status='HOST_NEGATIVE_TESTS_PASS_NOT_DUT', rejected=negatives,
            simulator_started=False, pins={str(p):b.su.sha(p) for p in [Path(__file__),Path(b.__file__)]}))
    print('HOST_NEGATIVE_TESTS_PASS_NOT_DUT', len(negatives))


if __name__ == '__main__':
    main()
