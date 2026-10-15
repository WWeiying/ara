#!/usr/bin/env python3
"""Offline negative checks; never rerun Spike, VCS, or edit sealed evidence."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import sv39_adapter as adapter


def corrupt_last_store(text, address):
    matches = list(re.finditer(r'(\bmem 0x0*%x 0x)([0-9a-f]+)' % address, text))
    adapter.require(bool(matches),'No snapshot store at requested byte')
    m = matches[-1]
    value = format(int(m[2],16) ^ 1,'0%dx' % len(m[2]))
    return text[:m.start(2)]+value+text[m.end(2):]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    d, out = adapter.inside(args.reference), adapter.inside(args.out)
    adapter.require(not out.exists(),'Fresh evidence file required')
    s = json.loads((d/'spike/alloff_fault.symbols.json').read_text())
    text = (d/'alloff_fault/spike.trace').read_text()
    trials = (
        ('unexpected_alloff_page_fault',
         'core   0: exception trap_load_page_fault, epc 0x%016x\n' % s['mt_target']+text,
         'Exact exception ledger differs'),
        ('oldvd_last_tail_word_bitflip',corrupt_last_store(text,s['mt_result']+64+128+124),
         'Full memory oracle mismatch'),
        ('neighbor_v25_last_word_bitflip',corrupt_last_store(text,s['mt_result']+64+256+124),
         'Full memory oracle mismatch'))
    results = []
    for name,altered,want in trials:
        try:
            adapter.validate_trace(altered,s,0)
        except ValueError as error:
            adapter.require(want in str(error),'Rejected for unrelated reason: '+str(error))
            results.append(dict(name=name,status='EXPECTED_REJECTION',reason=str(error)))
        else:
            raise AssertionError('Oracle accepted corruption: '+name)
    adapter.save(out,dict(status='OFFLINE_ORACLE_NEGATIVE_CHECKS_PASS',results=results,
                 reference_status_sha256=adapter.sha(d/'status.json'),
                 checker_sha256=adapter.sha(Path(adapter.__file__)),
                 test_sha256=adapter.sha(Path(__file__)),simulators_launched=False))
    print(json.dumps(results,indent=2))


if __name__ == '__main__':
    main()
