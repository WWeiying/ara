#!/usr/bin/env python3
"""Persist bounded host tests and immutable source identities; never execute RTL."""
import argparse
import io
import json
from pathlib import Path
import re
import unittest

from contract import HERE, OUT, require, save, sha, verify
import test_real
import test_evidence


def main():
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT.resolve() and
            re.fullmatch(r'operator_attention_real_prepare_20261115_[A-Za-z0-9_.-]+',out.name)
            and not out.exists(), 'Fresh owned output required')
    require(sha(HERE/'ancestor/evidence_generators.py') ==
            '9defc50a8fe72d803f2b6c993d97497b2e5ef98744809bf0b237b5e1c9db7c60',
            'Sealed synthetic evidence generator snapshot drift')
    out.mkdir()
    pins = {str(path):sha(path) for path in HERE.rglob('*') if path.is_file() and
            path.suffix in ('.py','.c','.S','.json','.md') and '__pycache__' not in path.parts}
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c)
                              for c in (test_real.RealTests,test_evidence.EvidenceTests)])
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    log = out/'host-tests.log';log.write_text(stream.getvalue())
    verify(pins)
    save(out/'source-pins.json',pins)
    report = dict(state='HOST_TEST_PASS_NOT_RTL' if result.wasSuccessful() else 'FAIL',
        tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        skipped=len(result.skipped),rtl_executed=False,target_executed=False,
        hardware_cycles_measured=False,synthetic_records_not_acceptance=True,
        source_pins_sha256=sha(out/'source-pins.json'),post_pins_match=True,
        log_sha256=sha(log),scope='Real captured dataset/oracle gates and synthetic checker mutations only')
    save(out/'result.json',report)
    print(stream.getvalue(),flush=True)
    print(json.dumps(report),flush=True)
    return not result.wasSuccessful()


if __name__ == '__main__': raise SystemExit(main())
