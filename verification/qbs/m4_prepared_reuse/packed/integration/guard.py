#!/usr/bin/env python3
"""Independent accepted-input audit; never refresh an inherited expected hash."""
import argparse
import json
from pathlib import Path

from stage import ROOT, ACTIVE, atomic_json, digest, hashes
from run_graph import check, linked_providers

ACCEPTED = {
    'm4-packed-canonical-20261027-02/manifest.json':
        'b5c6f487c3ba743e6f5390efdb6a4c5af24681606cedde11ffe9b0594b4c2543',
    'm4-packed-stride-repair-20261027-01/manifest.json':
        '8110224ad10cc00458e337b132ce6a351dc18d7fadc8064c6dec0f897495c6cf',
    'm4-stride-expanded-20261027-01/acceptance-manifest.json':
        '6d7feccad054df2d97c03b2a0bd6c275afd205c6b5528303f89558585674f8d3',
    'm4-prepared-installed-build-20261027-01/manifest.json':
        '7e01c4446b81f73705f61fc4e76977057662bd9f587aa39060d219ba9ed49c84',
}


def merge(target, incoming):
    conflicts = [path for path, value in incoming.items() if path in target and target[path] != value]
    if conflicts:
        raise ValueError('Conflicting expected hashes: ' + repr(conflicts))
    target.update(incoming)


def accepted_inputs():
    pins = {}
    for relative, expected in ACCEPTED.items():
        manifest = ROOT / 'verification/out' / relative
        if digest(manifest) != expected:
            raise ValueError('Accepted inventory identity: ' + str(manifest))
        merge(pins, json.loads(manifest.read_text()))
        merge(pins, {str(manifest): expected})
    if digest(ACTIVE) != '06097034f29a8f21b0b83e877ba9aebecb4e9ea7b4356cefb119bab4449f475d':
        raise ValueError('Active experiment inventory identity')
    merge(pins, json.loads(ACTIVE.read_text()))
    merge(pins, {str(ACTIVE): digest(ACTIVE)})
    return pins


def audit(candidate, graph=None):
    pins = accepted_inputs()
    accepted_count = len(pins)
    staged = json.loads((candidate / 'manifest.json').read_text())
    # Comparing recorded expectations catches even an overwritten preflight pin
    # when the source has since been restored to its accepted bytes.
    merge(pins, staged)
    stage_result = json.loads((candidate / 'result.json').read_text())
    if stage_result['state'] != 'COMPILE_ONLY_PASS':
        raise ValueError('Staged compile did not pass')
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Accepted/staged file drift')
    result = dict(state='PASS', accepted_inputs=accepted_count, staged_inputs=len(staged),
                  inherited_hash_conflicts=0, scope='Independent source-identity audit')
    if graph is not None:
        graphpins = json.loads((graph / 'manifest.json').read_text())
        merge(pins, graphpins)
        raw = (graph / 'qemu.log').read_text()
        measured = check(raw)
        stored = json.loads((graph / 'result.json').read_text())
        if stored['state'] != 'PASS' or stored['measured'] != measured or stored['log_sha256'] != digest(graph / 'qemu.log'):
            raise ValueError('Raw graph evidence differs from stored result')
        symbols = linked_providers((graph / 'link.map').read_text(), candidate / 'repack.o')
        if symbols != json.loads((graph / 'link-audit.json').read_text()):
            raise ValueError('Linked provider evidence differs')
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Graph/accepted file drift')
        result.update(graph_replay='PASS', graph_outputs_and_state_bytes=measured['paired_bytes'],
                      graph_log_sha256=digest(graph / 'qemu.log'), graphs=measured['graphs'])
    result['verified_inputs'] = len(pins)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--graph', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out') or out.exists():
        raise ValueError('Fresh independent audit output required')
    out.mkdir(parents=True)
    try:
        result = audit(args.candidate.resolve(strict=True), args.graph.resolve(strict=True) if args.graph else None)
    except BaseException as exc:
        atomic_json(out / 'result.json', dict(state='FAIL', error=repr(exc)))
        raise
    result['auditor_sha256'] = digest(Path(__file__))
    atomic_json(out / 'result.json', result)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
