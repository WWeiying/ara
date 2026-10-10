#!/usr/bin/env python3
"""Offline whole-core trusted-IP proposal; never launches native tools."""
import argparse
import hashlib
import json
from pathlib import Path

from inventory_operand_debug import Design, ROOT

OUT = ROOT / 'verification/out'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
BASE = OUT / 'trusted-ip797-global-parent-20261008-01'
SYSTEM = 'ara_tb.dut.i_ara_soc.i_system'
MODULE = 'ct_vfdsu_srt_radix16_with_sqrt'
EVIDENCE = (
    'scalar-divsqrt-finite-qualified-agent-20261007-01',
    'c910-float-edge-initialized-qualified777-parent-20261007-01',
    'fclass-divsqrt783-qualified-agent-20261008-02',
    'scalar-div-subnormal794-qualified-v2-parent-20261008-01',
)
STATUSES = (
    'EXACT20_SCALAR_FP_RATIONAL_SPIKE_DUT_QUALIFIED',
    'C910_INITIALIZED_FLOAT_EDGE_FULL_SCALAR_NATIVE_CSR_RAW777_PASS_NOT_ADMITTED',
    'FCLASS_DIVSQRT783_FULL_ARCHITECTURE_NATIVE_RAW_QUALIFIED_NOT_ADMITTED',
    'FULL_SCALAR_DIV_SUBNORMAL144_NATIVE_QUALIFIED_NOT_ADMITTED',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_roots(roots, inherited):
    require(len(roots) == 17 and len(set(roots)) == 17, 'Exact unique 17 roots required')
    for scope in roots:
        require(scope.startswith(SYSTEM + '.') and scope.endswith('.x_' + MODULE),
                'Not an exact system SRT arithmetic core')
        require(not any(scope == p or scope.startswith(p + '.') or p.startswith(scope + '.')
                        for p in inherited), 'Overlap with inherited whole scope')
        require(not any(scope != p and scope.startswith(p + '.') for p in roots),
                'Ancestor root in proposal')


def review():
    pins = {}

    def read(path):
        pins[str(path)] = sha(path)
        return json.loads(path.read_bytes())

    q = read(BASE / 'qualification.json')
    require(pins[str(BASE / 'qualification.json')] ==
            'd7b929c065495868e6dc4656f8c575168e8b19530acda570b5a9bc1c691c91fc',
            'Wrong qualified baseline')
    config = read(BASE / 'config.json')
    require(len(config['trusted_roots']) == 577, 'Wrong inherited roots')
    source_pins = read(BUILD / 'build-source-pins.json')
    design = Design(BUILD / 'sim/simv.vdb')
    db = BUILD / 'sim/simv.vdb/snps/coverage/db'
    for rel in ('design/verilog.design.xml', 'auxiliary/verilog.sourceinfo.xml',
                'shape/tgl.verilog.info.xml'):
        pins[str(db / rel)] = sha(db / rel)
    roots = sorted(s for s, d in design.hierarchy.items()
                   if s.startswith(SYSTEM + '.') and d.get('name') == MODULE)
    validate_roots(roots, config['trusted_roots'])
    rows = []
    for scope in roots:
        owned = [scope] + sorted(s for s in design.hierarchy if s.startswith(scope + '.'))
        require(len(owned) == 4, 'Unexpected core descendants')
        require(sorted(design.hierarchy[s].get('name') for s in owned[1:]) ==
                ['ct_vfdsu_srt_radix16_bound_table', 'gated_clk_cell', 'gated_clk_cell'],
                'Unexpected child module')
        identity = []
        for s in owned:
            item = design.source(s)
            path = Path(item['resolved_path'])
            pins[str(path)] = sha(path)
            require(source_pins.get(str(path)) == pins[str(path)], 'Source differs from image')
            item.update(scope=s, source_sha256=pins[str(path)],
                        toggle_checksum=design.info['tgl'].get(s))
            identity.append(item)
        require(identity[0]['definition_checksum'] == '406590228' and
                identity[0]['toggle_checksum'] == '3969040510', 'Wrong core identity')
        wrapper = scope.split('.i_ct_vfdsu_top.', 1)[0]
        parent = scope.rsplit('.', 1)[0]
        rows.append(dict(scope=scope, checksum='406590228', decision='RECOMMEND',
                         architecture='scalar' if '.i_ariane.' in scope else 'vector',
                         owned_subtree=identity, protected_parent=parent,
                         protected_wrapper=wrapper,
                         compiled_wrapper=dict(design.hierarchy[wrapper].attrib),
                         compiled_wrapper_toggle_definition=dict(design.definition(wrapper, 'tgl').attrib)))
    evidence = []
    for name, status in zip(EVIDENCE, STATUSES):
        path = OUT / name / 'qualification.json'
        e = read(path)
        require(e['status'] == status, 'Wrong functional evidence status')
        if 'signature' in e:
            require(e['signature']['failures'] == 0, 'Known functional signature failure')
        if 'vector' in e:
            require(e['vector']['status'] == 'PASS' and
                    e['vector']['skipped_unknown_bytes'] == 0, 'Vector evidence incomplete')
        keys = ('status', 'operations', 'result_flags_checks', 'guard_checks',
                'scalar_exact_counts', 'signature', 'architecture', 'vector',
                'scope', 'coverage_admitted')
        evidence.append(dict(path=str(path), sha256=pins[str(path)],
                             observed={k: e[k] for k in keys if k in e},
                             limitation='Historical functional evidence, not exhaustive core proof or new native qualification'))
    review_path = OUT / EVIDENCE[0] / 'arithmetic-source-review.json'
    upstream = read(review_path)
    require(upstream['upstream_bytes_equal'] is True and upstream['source_sha256'] ==
            rows[0]['owned_subtree'][0]['source_sha256'], 'Wrong upstream evidence')
    for rel in ('verification/fpu/README.md',
                'verification/diagnostics/fpnew_conv_mask_repair_20260928.md'):
        pins[str(ROOT / rel)] = sha(ROOT / rel)
    for path, digest in pins.items():
        require(sha(path) == digest, 'Evidence changed during review')
    return dict(schema='SRT_WHOLE_TRUSTED797_PROPOSAL_V1',
                status='RECOMMEND_PENDING_PARENT_AND_NATIVE_WHOLE_SCOPE_QUALIFICATION',
                policy='TRUSTED_IP_INTEGRATION', native_qualified=False,
                EDA_launched=False, RTL_modified=False, unreachability_claim=False,
                baseline=dict(path=str(BASE), qualification_sha256=pins[str(BASE / 'qualification.json')],
                              inherited_roots=577, Toggle=q['reports']['applied'][SYSTEM]['Toggle']),
                counts=dict(new_roots=17, scalar=1, vector=16, owned_descendants=51,
                            proposed_union_roots=594),
                source_parameters=dict(DATA_WIDTH=56, REM_WIDTH=61, QT_WIDTH=58),
                compiled_parameter_disclosure='Core design definition is the bare module name; no direct actual parameter serialization. Source parameters and compiled source identity are bound; do not label these metadata-reported actuals.',
                upstream=dict(commit=upstream['upstream_commit'], bytes_equal_evidence=str(review_path)),
                known_bug_review=dict(core_unresolved_bug_identified=False,
                    scope='Bounded review of the listed source/evidence only; absence of a located bug is not a bug-free assertion.',
                    preserved='Cast/div flag/rounding and wrapper issue/flush/PC/TID/completion failures remain visible and in coverage.',
                    distinct_MVP='verification/fpu/README.md failures concern the separate dirty MVP non-restoring divider, not this compiled C910 radix16 core.'),
                action_policy=dict(operation='Exact GUI exclude Instance+Hier, one per proposed root, all metrics including covered positions',
                    annotation='Trusted execution IP integration scope; not unreachability or exhaustive verification',
                    inherited='Load complete qualified 577-root applied EL; preserve all inherited semantic exclusions outside the 17 new subtrees.',
                    native='Reuse mature whole-scope save/reload/reset five-phase exporter; no native EL qualification claimed by this packet.',
                    protected='All ancestors, sibling round/pack/prepare/ctrl, wrapper flags/tags/flush/ready-valid, VALU/VMFPU/queues/hazard/exception/completion remain covered.',
                    report='Preserve raw and existing 73.18 and 72.81 reports. Same 797 members and original 73 reporting scopes; report all metrics and denominator losses honestly. No percentage forecast.',
                    validation_owner='Existing scalar/vector architectural, result/fflags, lifecycle checks and assertions remain enabled; parent integration owns request/flush/completion.'),
                trusted_roots={s: '406590228' for s in roots}, instances=rows,
                functional_evidence=evidence, input_pins=pins)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packet = review()
    with args.output.open('x') as stream:
        json.dump(packet, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=packet['status'], counts=packet['counts'],
                          output=str(args.output.resolve()), sha256=sha(args.output))))


if __name__ == '__main__':
    main()
