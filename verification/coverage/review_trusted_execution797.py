"""Policy candidate scope inventory under explicit whole-execution-IP authorization."""
import argparse
import json
from pathlib import Path

import audit_error_slave797_source as a
import targeted_toggle_evidence_v2 as native
from inventory_operand_debug import Design

DECISIONS = {
    'simd_alu': ('HOLD', 'Historical carry/borrow active-bit FAIL remains unlocalized; do not assert wrapper-only root cause.'),
    'simd_mul': ('RECOMMEND', 'Independent arithmetic/pipeline leaf; strict797 corpus plus VSMUL saturation qualification. Retain vmfpu issue/result/mask/vxsat integration.'),
    'serdiv': ('RECOMMEND', 'Serial arithmetic core, including internal FSM as owned execution-IP implementation. Retain simd_div and scalar mult wrappers, scheduling/flush/result/ID interfaces.'),
    'fpnew_fma': ('RECOMMEND', 'Explicit new authorization includes reusable arithmetic/pipeline IP. Retain all fpnew format/opgroup/top wrappers and vmfpu/QBS owners; result/tag/mask/flags assertions stay enabled.'),
}


def collect():
    pins = {}

    def read(path, seal=None):
        data = path.read_bytes()
        actual = native.digest(path)
        a.need(seal is None or actual == seal, 'Pinned evidence: ' + str(path))
        pins[str(path)] = actual
        return data

    q = json.loads(read(a.REPORT / 'qualification.json',
        '1ebc05103bc71ee6ec26d97e51ed4867fed3d35a21ee38490956c3ccadf2c5c6'))
    a.need(q['population'] == q['actual_selected_tests'] == 797, 'Qualified797')
    manifest = json.loads(read(a.ADMITTED / 'admission-manifest.json',
        '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4'))
    config = json.loads(read(a.REPORT / 'config.json', q['config_seal']))
    path = a.ADMITTED / 'combined-toggle-bits.json'
    rows = json.loads(read(path, manifest['output_pins'][str(path)]))
    book_path = a.BUILD / 'build-source-pins.json'
    book = json.loads(read(book_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'))
    read(a.ROOT / 'verification/coverage/DVE_WAIVERS.md')
    db = Path(config['input_ledger'][0])
    for rel in ('design/verilog.design.xml', 'shape/tgl.verilog.shape.xml',
                'shape/tgl.verilog.info.xml', 'auxiliary/verilog.sourceinfo.xml'):
        path = db / 'snps/coverage/db' / rel
        read(path, config['pins'][str(path)])
    design = Design(db)
    shape = native.xml(db / 'snps/coverage/db/shape/tgl.verilog.shape.xml')
    definitions = {}
    for d in shape.findall('tgldef'):
        definitions.setdefault(d.get('chksum'), []).append(d)
    candidates = []
    for scope, row in rows.items():
        defs = definitions.get(row['checksum'], [])
        if len(defs) != 1:
            continue
        definition = defs[0]
        family = definition.get('name', '').split(' (')[0]
        if family not in DECISIONS:
            continue
        source_path = Path(design.source(scope)['resolved_path'])
        read(source_path, book[str(source_path)])
        decision, reason = DECISIONS[family]
        candidates.append(dict(scope=scope, module=family, decision=decision, reason=reason,
            source=str(source_path), source_sha256=book[str(source_path)],
            design_checksum=design.hierarchy[scope].get('chksum'),
            toggle_checksum=row['checksum'], compiled_definition=definition.attrib,
            native_qualified=False))
    evidence = {}
    for rel in ('vsmul-saturation796-qualified-parent-20261008-01/qualification.json',
                'half-fma-source-tail-qualified-agent-20261007-01/qualification.json',
                'scalar-fpu-fma-arbiter792-qualified-parent-20261008-01/qualification.json',
                'mask-compare-known786-measured-bug-agent-20261008-01.json',
                'gap35-analysis-20261004-01/failure-triage.json'):
        path = a.OUT / rel
        if path.exists():
            data = json.loads(read(path))
            evidence[rel] = dict(status=data.get('status'), sha256=pins[str(path)])
    for rel in ('hardware/src/lane/valu.sv', 'hardware/src/lane/vmfpu.sv',
                'hardware/src/lane/simd_div.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
                'hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv'):
        path = a.ROOT / rel
        read(path, book[str(path)])
    pins[str(Path(__file__).resolve())] = native.digest(Path(__file__).resolve())
    counts = {f: sum(t['module'] == f for t in candidates) for f in DECISIONS}
    a.need(all(counts.values()), 'All four families compiled')
    return dict(status='POLICY_REVIEW_READY_FOR_VOLTA_SCOPE_NATIVE_PREPARE_NOT_APPLIED',
        policy='TRUSTED_IP_INTEGRATION_NOT_UNREACHABILITY_NOT_EXHAUSTIVE_VERIFICATION',
        baseline_population=797, pins=pins, evidence=evidence, decisions=DECISIONS,
        instance_counts=counts, candidates=candidates,
        retained=['valu', 'vmfpu', 'simd_div', 'scalar mult wrapper', 'operand/result queues',
                  'fpnew_top/opgroup/fmt wrappers and arbiters', 'cast/divsqrt',
                  'QBS accumulator/controller', 'MaskU', 'operand_requester', 'SLDU', 'VLSU/addrgen'],
        validation_owner='Existing independent strict functional collectors plus integration assertions/scoreboards; waivers never disable them.',
        caveats=['Scalar FMA hold test did not trigger hold/stall; not an exhaustive backpressure proof.',
                 'Whole fpnew_fma recommendation supersedes earlier narrow-policy HOLD only under new explicit authorization.',
                 'Carry FAIL root not localized: simd_alu HOLD is a conservative evidence-specific hold, not a ban on modified independent IP.',
                 'No blanket fpnew/C910/QBS/vmfpu exclusion. Enumerate exact approved scopes; subtract/reconcile inherited point EL within selected descendants.',
                 'Volta must check actual native scope checksum, saved/reloaded/reset exact scopes and all other scopes protected.',
                 'Retain original raw797 and qualified797+MaskU policy73.18 separately; denominator change is not new stimulus gain.'],
        EDA_started=False, RTL_changed=False, EL_generated=False, applied=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    packet = collect()
    with args.output.open('x') as stream:
        stream.write(json.dumps(packet, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output), sha256=native.digest(args.output),
                         counts=packet['instance_counts'])))
