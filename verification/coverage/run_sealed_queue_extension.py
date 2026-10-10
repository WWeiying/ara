#!/usr/bin/env python3
"""Checked queue extension with exact replay of its sealed Spike preflight.

Keep prior checkers and preflight artifacts immutable. Bind manifest contents,
not only the JSON manifest files, into the normal frozen runner plan.
"""
from pathlib import Path

import coverage_evidence as evidence
import run_checked_extension as checked

SCRIPT = Path(__file__).resolve()
ROOT = evidence.full.ROOT
NAME = 'rvv:vgap38_i8_f16_lane3'
PREFLIGHT = ROOT / 'verification/out/gap38-i8-f16-preflight-20261004-03'
DRAFT = PREFLIGHT / 'selection.checked-draft.json'
ORIGINAL_PRECHECK = evidence.precheck
require = evidence.require


def require_exact_replay(result, files, saved):
    require(saved.get('status') == 'PASS' and saved.get('read_only_validation') is True,
            'sealed preflight is not a checked PASS')
    require(result == saved.get('result'), 'preflight result differs from sealed evidence')
    require(files and files == saved.get('checked_files'),
            'preflight file set or hashes differ from sealed evidence')


def sealed_precheck(item, proof):
    if item.get('name') != NAME:
        return ORIGINAL_PRECHECK(item, proof)
    # Verify the seal before using any nested manifests as expected values.
    seals = proof.read(PREFLIGHT / 'draft.sha256.json')
    require(set(seals) == {str(DRAFT), str(PREFLIGHT / 'checked-precheck.json'),
                           str(PREFLIGHT / 'artifact_hashes.json')}, 'wrong preflight seal set')
    proof.hashes(seals)
    saved = proof.read(PREFLIGHT / 'checked-precheck.json')
    draft = proof.read(DRAFT)
    require(len(draft['cases']) == 1 and draft['cases'][0]['name'] == NAME,
            'wrong sealed candidate set')
    original = draft['cases'][0]
    require(item['timeout_s'] == original['timeout_s'] == 300 and
            item['targets'] == original['targets'] and
            item['binary'] == original['binary'], 'candidate scope, ELF or budget changed')

    # Reproduce exactly the builder's evidence construction, before appending
    # the new composition and adapter files required by this batch.
    replay = evidence.Evidence()
    replay.pin(DRAFT)
    for name in ('tool_hashes.json', 'link-inputs.json', 'protected-inputs.json',
                 'artifact_hashes.json'):
        path = PREFLIGHT / name
        contents = evidence.full.read(path)
        replay.hashes(contents)
    result = ORIGINAL_PRECHECK(original, replay)
    require_exact_replay(result, replay.files, saved)
    current = ORIGINAL_PRECHECK(item, proof)
    require(current == result, 'selected precheck differs from sealed Spike result')

    # These entries become ordinary plan.files pins, checked again at launch,
    # execution and aggregation by the unchanged runner.
    proof.hashes(saved['checked_files'])
    for path in (SCRIPT, Path(checked.__file__), Path(evidence.__file__)):
        proof.pin(path)
    return current


def main():
    checked.SCRIPT = SCRIPT
    evidence.precheck = sealed_precheck
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
