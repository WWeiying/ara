#!/usr/bin/env python3
"""Sealed gap51 host-only admission adapter for the unchanged checked runner."""
import json
from pathlib import Path

import coverage_evidence as evidence
import run_checked_extension as checked

ROOT = evidence.full.ROOT
SCRIPT = Path(__file__).resolve()
NAME = 'qbs_gap51_payload_matrix'
CASE = 'app:' + NAME
MANIFESTS = ('tool_hashes.json', 'link-inputs.json', 'protected-inputs.json', 'artifact_hashes.json')
require = evidence.require
_HOOKS = None


def precheck(item, proof, delegate):
    require(item.get('name') == CASE and item.get('timeout_s') == 600,
            'wrong gap51 identity or budget')
    schema = item['precheck']
    require(schema['format'] == 'accel-host-v1', 'gap51 is host-reference-only')
    directory = evidence.full.absolute(schema['record']).resolve(strict=True).parent
    require(directory.parent == ROOT / 'verification/out' and directory.name.startswith('gap51-payload-'),
            'foreign gap51 preflight directory')
    draft = directory / 'selection.checked-draft.json'
    saved_path = directory / 'checked-precheck.json'
    artifacts = directory / 'artifact_hashes.json'
    seals = proof.read(directory / 'draft.sha256.json')
    require(set(seals) == {str(draft), str(saved_path), str(artifacts)}, 'wrong gap51 seal set')
    proof.hashes(seals)
    original = proof.read(draft)
    require(original['cases'] == [item], 'gap51 case differs from sealed draft')
    saved = proof.read(saved_path)
    require(saved.get('status') == 'PASS' and saved.get('read_only_validation') is True and
            saved.get('vcs_launched') is False and saved.get('scope') == 'host-reference-only',
            'gap51 is not a sealed host-only precheck')
    replay = evidence.Evidence()
    replay.pin(draft)
    for name in MANIFESTS:
        replay.hashes(replay.read(directory / name))
    result = delegate(item, replay)
    require(json.loads(json.dumps(result)) == result, 'gap51 result is not JSON stable')
    require(result == saved['result'] and replay.files == saved['checked_files'],
            'gap51 sealed replay differs')
    require(result.get('scope') == 'host-reference-only', 'host precheck became an ISA PASS')
    proof.hashes(replay.files)
    for path in (SCRIPT, Path(checked.__file__), Path(evidence.__file__)):
        proof.pin(path)
    return result


def install_hooks():
    """Delegate unrelated cases, install once, and preserve the parent's SCRIPT."""
    global _HOOKS
    if _HOOKS is not None:
        return _HOOKS
    prior = evidence.precheck

    def wrapped(item, proof):
        return precheck(item, proof, prior) if item.get('name') == CASE else prior(item, proof)

    wrapped.delegate = prior
    evidence.precheck = wrapped
    _HOOKS = {'name': NAME, 'precheck': wrapped}
    return _HOOKS


def main():
    checked.SCRIPT = SCRIPT
    install_hooks()
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
