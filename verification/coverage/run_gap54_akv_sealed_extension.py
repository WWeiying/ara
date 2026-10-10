#!/usr/bin/env python3
"""Supplement the immutable gap54 adapter with its original seal contract."""
from pathlib import Path

import coverage_evidence as evidence
import run_gap54_akv_checked_extension as original

SCRIPT = Path(__file__).resolve()
require = evidence.require
_HOOKS = None


def sealed_precheck(item, proof, delegate):
    require(item.get('name') == original.admission.TEST, 'not the reviewed gap54 case')
    root = Path(item['precheck']['record']).resolve(strict=True).parent
    require(root.parent == evidence.full.ROOT / 'verification/out' and
            root.name.startswith('gap54-akv-preflight-'), 'foreign gap54 preflight')
    inputs = evidence.Evidence()
    selection = inputs.read(root / 'selection.json')
    require(selection['cases'] == [item], 'original sealed selection differs')
    binding = selection['sealed_precheck']
    seal_path = root / 'sealed-precheck.json'
    require(binding['path'] == str(seal_path), 'foreign seal path')
    inputs.hashes({str(seal_path): binding['sha256']})
    seal = inputs.read(seal_path)
    require(seal.get('status') == 'PASS' and seal.get('vcs_launched') is False,
            'seal is not an approved software precheck')
    draft_path = root / 'draft.json'
    require(seal['draft'] == str(draft_path), 'foreign original draft')
    inputs.hashes({str(draft_path): seal['draft_sha256']})
    draft = inputs.read(draft_path)
    require(draft['cases'] == [item] and
            selection == dict(draft, sealed_precheck=binding), 'sealed draft/selection differs')
    require(seal['case_sha256'] == original.admission.oracle.canonical(item),
            'sealed complete case hash differs')
    replay = evidence.Evidence()
    result = delegate(item, replay)
    require(result == seal['result'] == binding['result'], 'sealed precheck result differs')
    require(replay.files == seal['checked_files'], 'sealed checked file set differs')
    inputs.hashes(replay.files)
    for module in (original, original.admission, original.admission.oracle):
        inputs.pin(Path(module.__file__).resolve())
    inputs.pin(SCRIPT)
    proof.hashes(inputs.files)
    return result


def install_hooks():
    global _HOOKS
    if _HOOKS is not None:
        return _HOOKS
    original.install_hooks()
    prior = evidence.precheck

    def precheck(item, proof):
        if item.get('name') == original.admission.TEST:
            return sealed_precheck(item, proof, prior)
        return prior(item, proof)

    precheck.delegate = prior
    evidence.precheck = precheck
    _HOOKS = {'name': original.admission.NAME, 'precheck': precheck}
    return _HOOKS


def main():
    original.checked.SCRIPT = SCRIPT
    install_hooks()
    return original.checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
