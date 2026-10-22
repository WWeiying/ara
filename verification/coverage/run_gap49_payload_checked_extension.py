#!/usr/bin/env python3
"""Compose a sealed gap49 host-reference gate with the unmodified checked runner."""
import json
from pathlib import Path

import coverage_evidence as evidence
import run_checked_extension as checked

ROOT = evidence.full.ROOT
SCRIPT = Path(__file__).resolve()
NAME = 'qbs_gap49_payload_skew'
CASE = 'app:' + NAME
MANIFESTS = ('tool_hashes.json', 'link-inputs.json', 'protected-inputs.json', 'artifact_hashes.json')
require = evidence.require
_HOOKS = None


def precheck(item, proof, delegate):
    require(item.get('name') == CASE and item.get('timeout_s') == 600,
            'wrong gap49 identity or budget')
    schema = item['precheck']
    require(schema['format'] == 'accel-host-v1', 'gap49 is host-reference-only')
    directory = evidence.full.absolute(schema['record']).resolve(strict=True).parent
    require(directory.parent == ROOT / 'verification/out' and directory.name.startswith('gap49-payload-'),
            'foreign gap49 preflight directory')
    draft = directory / 'selection.checked-draft.json'
    saved_path = directory / 'checked-precheck.json'
    artifacts = directory / 'artifact_hashes.json'
    seals = proof.read(directory / 'draft.sha256.json')
    require(set(seals) == {str(draft), str(saved_path), str(artifacts)}, 'wrong gap49 seal set')
    proof.hashes(seals)
    original = proof.read(draft)
    require(original['cases'] == [item], 'gap49 case differs from sealed draft')
    saved = proof.read(saved_path)
    require(saved.get('status') == 'PASS' and saved.get('read_only_validation') is True and
            saved.get('vcs_launched') is False and saved.get('scope') == 'host-reference-only',
            'gap49 is not a sealed host-only precheck')
    replay = evidence.Evidence()
    replay.pin(draft)
    for name in MANIFESTS:
        replay.hashes(replay.read(directory / name))
    result = delegate(item, replay)
    require(json.loads(json.dumps(result)) == result, 'gap49 result is not JSON stable')
    require(result == saved['result'] and replay.files == saved['checked_files'],
            'gap49 sealed replay differs')
    require(result.get('scope') == 'host-reference-only', 'host precheck became an ISA PASS')
    proof.hashes(replay.files)
    for path in (SCRIPT, Path(checked.__file__), Path(evidence.__file__)):
        proof.pin(path)
    return result


def install_hooks():
    """Install once, delegate unrelated cases, and leave the parent's SCRIPT alone."""
    global _HOOKS
    if _HOOKS is not None:
        return _HOOKS
    prior = evidence.precheck

    def wrapped(item, proof):
        if item.get('name') != CASE:
            return prior(item, proof)
        return precheck(item, proof, prior)

    wrapped.delegate = prior
    evidence.precheck = wrapped
    _HOOKS = {'name': NAME, 'precheck': wrapped}
    return _HOOKS


def main():
    # Only the standalone entrypoint chooses its worker entry script.
    checked.SCRIPT = SCRIPT
    install_hooks()
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
