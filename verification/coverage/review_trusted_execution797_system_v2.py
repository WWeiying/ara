"""Seal trusted-IP candidates strictly within the paper's i_system root."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system'
PRIOR = OUT / 'trusted-execution797-leaves-review-agent-20261008-01.json'
PRIOR_SHA = 'd09a67f4b3985dea799ca5e32613e54260dd0c4d52f99e99578a47518ffb742c'
POLICY = ROOT / 'verification/coverage/DVE_WAIVERS.md'
POLICY_SHA = '43c28dd340442a32a0cd966d572d5c501e57da011dd7282d78dbc3a122d00311'
COUNTS = dict(simd_alu=4, simd_mul=16, serdiv=5, fpnew_fma=32,
              fpnew_classifier=127, fpnew_rounding=50, lzc=453)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(scope):
    return scope == SCOPE or scope.startswith(SCOPE + '.')


def restrict(candidates):
    need(len({t['scope'] for t in candidates}) == len(candidates), 'Unique candidate scope')
    selected = [t for t in candidates if inside(t['scope'])]
    removed = [t for t in candidates if not inside(t['scope'])]
    approved = [t for t in selected if t['decision'] == 'RECOMMEND']
    roots = [t['scope'] for t in approved if not any(t['scope'].startswith(p['scope'] + '.')
             for p in approved)]
    return selected, removed, roots


def validate(packet):
    need(packet['coverage_scope'] == SCOPE, 'Exact paper coverage root')
    need(all(inside(t['scope']) for t in packet['candidates']), 'Outside candidate forbidden')
    selected, removed, roots = restrict(packet['candidates'])
    need(not removed and roots == packet['minimal_recommended_roots'], 'Exact minimal selected roots')
    counts = {f: sum(t['module'] == f for t in selected) for f in COUNTS}
    need(counts == packet['instance_counts'] == COUNTS, 'Exact i_system family counts')
    need(len(roots) == 577 and len(selected) == 687, 'Exact577 roots/687 candidates')
    need(sum(t['decision'] == 'RECOMMEND' for t in selected) == 683, 'Exact683 recommended')
    need(all(t['decision'] == ('HOLD' if t['module'] == 'simd_alu' else 'RECOMMEND')
             for t in selected), 'Preserve known-bug HOLD')
    need(not packet['EDA_started'] and not packet['EL_generated'] and not packet['applied'],
         'Read-only policy candidate')


def collect():
    need(digest(PRIOR) == PRIOR_SHA, 'Frozen predecessor packet')
    packet = json.loads(PRIOR.read_bytes())
    previous_policy = packet['pins'].get(str(POLICY))
    for path, seal in packet['pins'].items():
        if path != str(POLICY):
            need(digest(Path(path)) == seal, 'Frozen predecessor source/design/evidence pin: ' + path)
    need(digest(POLICY) == POLICY_SHA, 'Current reviewed authorization changed')
    policy = POLICY.read_text()
    need('Local edits do not by themselves disqualify a module.' in policy
         and 'known unresolved failure' in policy, 'Current broad authorization and bug hold')
    selected, removed, roots = restrict(packet['candidates'])
    need(len(removed) == 48 and all(t['module'] == 'lzc' for t in removed), 'Exact48 outside LZC')
    packet.update(schema='TRUSTED_IP_INTEGRATION797_ISYSTEM_ONLY_V2',
        status='ISYSTEM_ONLY_CURRENT_POLICY_SEALED_PREPARE_CANDIDATE_NOT_NATIVE_QUALIFIED',
        coverage_scope=SCOPE, scope_expansion_authorized=False,
        scope_correction='Predecessor leaf enumerator unintentionally traversed whole-design union. Outside48 LZC removed, not approved as an expanded paper scope.',
        predecessor=dict(path=str(PRIOR), sha256=PRIOR_SHA, policy_sha256=previous_policy),
        current_policy=dict(path=str(POLICY), sha256=POLICY_SHA),
        candidates=selected, outside_scope_REMOVED_NOT_APPROVED=removed,
        minimal_recommended_roots=roots, instance_counts=COUNTS,
        recommended_instances=683, nested_recommended_leaves_already_owned=106)
    packet['pins'][str(POLICY)] = POLICY_SHA
    packet['pins'][str(PRIOR)] = PRIOR_SHA
    packet['pins'][str(Path(__file__).resolve())] = digest(Path(__file__).resolve())
    validate(packet)
    need(digest(POLICY) == POLICY_SHA and digest(PRIOR) == PRIOR_SHA, 'Read-end drift')
    return packet


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packet = collect()
    with args.output.open('x') as stream:
        stream.write(json.dumps(packet, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output), sha256=digest(args.output),
        recommended=683, roots=577, hold=4, outside_removed=48)))
