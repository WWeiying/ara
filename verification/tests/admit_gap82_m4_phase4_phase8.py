#!/usr/bin/env python3
"""Read-only single-app host preflight, not baseline/aggregate admission."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import build_gap38_i8_f16_lane3 as common
sys.path.insert(0,str(common.ROOT/'verification/coverage'))
import coverage_evidence as evidence


def preflight(directory):
    directory = Path(directory).resolve(strict=True)
    common.require(directory.parent == common.ROOT/'verification/out'
                   and directory.name.startswith('gap82-m4-phase4-phase8-'), 'foreign gap82 preflight')
    seals = common.read(directory/'draft.sha256.json')
    common.require(set(seals) == {str(directory/n) for n in
                   ('selection.checked-draft.json','checked-precheck.json','artifact_hashes.json')},
                   'unexpected preflight seals')
    common.verify(seals)
    proof = evidence.Evidence()
    draft = directory/'selection.checked-draft.json'
    proof.pin(draft)
    for name in ('tool_hashes','link-inputs','protected-inputs','artifact_hashes'):
        proof.hashes(proof.read(directory/(name+'.json')))
    selection = common.read(draft)
    common.require(len(selection['cases']) == 1 and selection['vcs_launched'] is False,
                   'host-only one-case draft required')
    item = selection['cases'][0]
    common.require(item['name'] == 'app:qbs_gap82_m4_phase4_phase8' and item['timeout_s'] == 600,
                   'wrong gap82 identity/budget')
    record = common.read(item['precheck']['record'])
    common.require(record['host_checks'] == 44 and record['dut_checks'] == 41
                   and record['elf_proof']['custom_commands'] == 2
                   and [x['activation_mod16'] for x in record['elf_proof']['sites']] == [4,8],
                   'complete two-command contract differs')
    result = evidence.precheck(item,proof)
    saved = common.read(directory/'checked-precheck.json')
    common.require(saved['status'] == 'PASS' and saved['scope'] == 'host-reference-only'
                   and saved['result'] == result and saved['checked_files'] == proof.files,
                   'host preflight replay differs')
    common.verify(proof.files)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',required=True,type=Path)
    print(preflight(parser.parse_args().preflight))

