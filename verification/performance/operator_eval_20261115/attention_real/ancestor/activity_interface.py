#!/usr/bin/env python3
"""Seal an activity02 runner manifest without changing the original firmware build."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import check
from contract import HERE, OUT, require, save, sha, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    m = check.receipt(args.build)
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT.resolve() and
            re.fullmatch(r'operator_attention_prepare_20261115_[A-Za-z0-9_.-]+',out.name) and not out.exists(),
            'Fresh owned output required')
    pins = json.loads((args.build/'source-pins.json').read_text()) | m['artifacts']
    for p in (args.build/'build.json',HERE/'check_activity.py',Path(__file__).resolve(),HERE/'test_attention.py'):
        pins[str(p.resolve())] = sha(p)
    verify(pins)
    plan = json.loads((args.build/'run-plan.json').read_text())
    for case in plan['cases']:
        case['checker'][2] = str(HERE/'check_activity.py')
        case['source_pins'] = str(out/'source-pins.json')
    out.mkdir()
    save(out/'source-pins.json',pins)
    save(out/'run-plan.json',plan)
    save(out/'interface.json',dict(state='PREPARED_NOT_EXECUTED',firmware_build=str(args.build),
        source_pins_sha256=sha(out/'source-pins.json'),requires_probe='operator_unit_activity activity02',
        numerical_protocol_image_acceptance=False))
    print(json.dumps(dict(state='PREPARED_NOT_EXECUTED',manifest=str(out/'run-plan.json'))))


if __name__ == '__main__':
    main()
