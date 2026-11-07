#!/usr/bin/env python3
"""Separate compile audit for the first driver's post-publication print error.

Never changes the failed worker's files or claims that it passed. Only the
exact pinned driver/error below is eligible; no RTL or image drift is admitted.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from build_soc import ROOT, HERE, OUT, digest, require, save, verify

DRIVER_COMMIT = '640862d2d'
DRIVER_PATH = 'verification/performance/chain_profile/build_soc.py'
ERROR = 'TypeError("__init__() got an unexpected keyword argument \'flush\'")'


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    original, out = a.original.resolve(strict=True), a.output.resolve()
    require(not out.exists() and out.is_relative_to(OUT.resolve()), 'Fresh separate admission required')
    status = json.loads((original / 'status.json').read_text())
    require(status.get('state') == 'FAIL' and status.get('error') == ERROR,
            'Not the reviewed terminal-print-only failure')
    report = json.loads((original / 'build.json').read_text())
    require(report.get('state') == 'CURRENT_AREA_SOC_BUILT_NOT_EXECUTED'
            and report.get('post_pins_match') is True and report.get('execution') == 'NOT_RUN',
            'Compiler never published a checked artifact')
    pinfile = original / 'source-pins.json'
    require(digest(pinfile) == report['source_pins_sha256'], 'Original inventory changed')
    pins = json.loads(pinfile.read_text())
    driver = subprocess.check_output(['git', '-C', str(ROOT), 'show', DRIVER_COMMIT + ':' + DRIVER_PATH])
    import hashlib
    expected = hashlib.sha256(driver).hexdigest()
    require(pins.get(str(HERE / 'build_soc.py')) == expected, 'Unknown original driver')
    require(b"save(out / 'build.json', result)" in driver and
            b"print(json.dumps(dict(state=result['state'], output=str(out)), flush=True))" in driver,
            'Publication/error ordering is not the reviewed driver')
    # Recover the exact prior driver from Git, never waive its source identity.
    del pins[str(HERE / 'build_soc.py')]
    verify(pins)
    verify(report['image_pins'])
    require('CPU time:' in (original / 'compile.log').read_text() and
            Path(report['simv']).is_file(), 'No completed compiler/image')
    out.mkdir(parents=True)
    archived_driver = out / 'original-build-driver.py'
    archived_driver.write_bytes(driver)
    require(digest(archived_driver) == expected, 'Driver reconstruction mismatch')
    pins[str(archived_driver)] = expected
    for f in (Path(__file__), original / 'build.json', pinfile, original / 'status.json',
              original / 'compile.log', original / 'compile.command.json'):
        pins[str(f)] = digest(f)
    save(out / 'source-pins.json', pins)
    report.update(state='CURRENT_AREA_SOC_COMPILE_AUDITED_NOT_EXECUTED',
                  original_worker_state='FAIL', original_worker=str(original),
                  admitted_driver_error=ERROR, original_worker_relabelled=False,
                  driver_pin_archive=dict(original=str(HERE / 'build_soc.py'), archive=str(archived_driver),
                                          sha256=expected, commit=DRIVER_COMMIT),
                  source_pins_sha256=digest(out / 'source-pins.json'))
    save(out / 'build.json', report)
    save(out / 'status.json', dict(state=report['state'], original_worker_state='FAIL',
                                   note='Independent compile audit only; no simulator execution accepted'))
    print(json.dumps(dict(state=report['state'], output=str(out))))


if __name__ == '__main__':
    main()
