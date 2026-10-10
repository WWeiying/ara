#!/usr/bin/env python3
"""Sealed gap65 host-only checked admission. CLI intentionally has no launch mode."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import coverage_evidence as evidence
import run_checked_extension as checked
import gap65_late_fault_checks as checks

ROOT, SCRIPT = evidence.full.ROOT, Path(__file__).resolve()
CASE = 'app:' + checks.NAME
MANIFESTS = ('tool_hashes.json', 'link-inputs.json', 'protected-inputs.json', 'artifact_hashes.json')
require = evidence.require
_HOOKS = None


def precheck(item, proof, delegate):
    require(item.get('name') == CASE and item.get('timeout_s') == 300, 'wrong gap65 case/budget')
    require(item['precheck']['format'] == 'accel-host-v1', 'gap65 host-only precheck required')
    directory = evidence.full.absolute(item['precheck']['record']).resolve(strict=True).parent
    require(directory.parent == ROOT / 'verification/out' and directory.name.startswith('gap65-late-fault-preflight-'),
            'foreign gap65 preflight')
    draft, saved_path, artifact = (directory / n for n in
        ('selection.checked-draft.json', 'checked-precheck.json', 'artifact_hashes.json'))
    seals = proof.read(directory / 'draft.sha256.json')
    require(set(seals) == {str(draft), str(saved_path), str(artifact)}, 'gap65 seal membership')
    proof.hashes(seals)
    require(proof.read(draft)['cases'] == [item], 'changed gap65 selection')
    saved = proof.read(saved_path)
    require(saved['status'] == 'PASS' and saved['scope'] == 'host-reference-only' and
            saved['vcs_launched'] is False and saved['read_only_validation'] is True and
            saved['observer_launch_admitted'] is False, 'wrong gap65 admission scope')
    replay = evidence.Evidence()
    replay.pin(draft)
    for name in MANIFESTS:
        replay.hashes(replay.read(directory / name))
    result = delegate(item, replay)
    require(json.loads(json.dumps(result)) == result and result == saved['result'] and
            replay.files == saved['checked_files'], 'gap65 admission pin/result drift')
    proof.hashes(replay.files)
    budget = proof.read(directory / 'cost-preflight.json')
    require(budget['proposed_timeout_s'] == 300 and budget['conditional_seconds_upper'] <= 300 and
            budget['status'] == 'CONDITIONAL_STATIC_BUDGET', 'unsupported budget')
    proof.hashes(budget['input_hashes'])
    for path in (SCRIPT, Path(checks.__file__), Path(checked.__file__), Path(evidence.__file__)):
        proof.pin(path)
    return result


def install_hooks():
    global _HOOKS
    if _HOOKS is None:
        prior = evidence.precheck

        def wrapped(item, proof):
            return precheck(item, proof, prior) if item.get('name') == CASE else prior(item, proof)

        wrapped.delegate = prior
        evidence.precheck = wrapped
        _HOOKS = {'name': checks.NAME, 'precheck': wrapped}
    return _HOOKS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--precheck-only', action='store_true', required=True)
    args = parser.parse_args()
    proof = evidence.Evidence()
    spec = proof.read(args.selection)
    require(len(spec['cases']) == 1, 'exactly one gap65 case required')
    result = precheck(spec['cases'][0], proof, evidence.precheck)
    print(json.dumps(dict(status='PASS_HOST_ONLY_NO_LAUNCH', result=result,
                         observer_launch_admitted=False, checked_files=len(proof.files))))


if __name__ == '__main__':
    main()
