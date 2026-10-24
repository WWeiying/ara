#!/usr/bin/env python3
"""Recheck terminal multioutput QK with the downstream's full numerical gate."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/akv/paired_heads'))
import attention_run as s
from run_attention import checked_prerequisite
from batch_spec import expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(strict=True), args.output.resolve()
    s.require(not out.is_relative_to(run), 'Use independent fresh audit output')
    out.mkdir(parents=True, exist_ok=False)
    try:
        original = s.hashes([run/'status.json', run/'result.json'])
        image, pins = checked_prerequisite(run)
        result = s.read_json(run/'result.json')
        s.require(result['expected'] == expected() and result['hardware_host_exact'] is True and
                  len(result['hardware_records']) == 40 and len(result['score_rows']) == 40 and
                  len(result['query_exports']) == 24, 'Incomplete accepted scope')
        s.require(s.hashes(map(Path, original)) == original, 'Original report changed during audit')
        s.merge_pins(pins, s.hashes([Path(__file__), HERE/'run_attention.py', HERE/'batch_spec.py']))
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json', pins)
        checked = dict(result)
        checked.update(state='INDEPENDENT_BATCH_QK_ACCEPTED', run=str(run),
            source_pins_sha256=s.digest(out/'source-pins.json'), independent_protocol_checked=True,
            current_inputs_match=True, original_report_sha256=original,
            source_image_inventory_sha256=image, full_rvv_matrix_equality='NOT_MEASURED',
            whole_attention_accepted=False, deployment_approved=False, performance_measured=False)
        s.atomic_json(out/'result.json', checked)
        print('INDEPENDENT_BATCH_QK_ACCEPTED commands=40 outputs=3336 queries=24')
    except BaseException as exc:
        s.atomic_json(out/'result.json', dict(state='FAIL', error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
