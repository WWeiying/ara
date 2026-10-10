"""Offline compiled-coordinate handoff only; no native discovery or exclusion."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import closure_point_inventory as inventory

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BASE = OUT / 'akv-column-boundary-offline-admitted-721-20261006-01'
PREFLIGHT = OUT / 'memory-emul-r2-preflight-721-20261006-01'
SEAL = 'eda7720583e3232e97cd4486d7790a678abc108018f6acbd56d0b1c287e20c8b'
SOURCE_SHA = '9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
LOWER = {('line', 1228), ('line', 1311), ('branch', 360), ('branch', 414)}
UPPER = {('line', 1308), ('branch', 362)}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def legal_proof():
    rows = []
    for sew in (8, 16, 32, 64):
        for exponent in range(-3, 4):
            lmul = Fraction(2) ** exponent
            if sew > min(lmul, 1) * 64:
                continue
            for eew in (8, 16, 32, 64):
                emul = lmul * eew / sew
                require(emul >= Fraction(1, 8), 'legal EMUL lower bound')
                rows.append(dict(sew=sew, lmul=str(lmul), eew=eew, emul=str(emul)))
    require(len(rows) == 88, 'legal combination count')
    return rows


def bind_targets(targets, mapped, metrics):
    require({(t['metric'], t['point']['raw_index']) for t in targets} == LOWER | UPPER
            and len(targets) == 6, 'exact six preflight points required')
    result = []
    for target in targets:
        metric, index = target['metric'], target['point']['raw_index']
        row = metrics[metric][SCOPE]
        require(target['scope'] == SCOPE, 'scope drift')
        require((row['width'], row['checksum']) ==
                (target['bitmap_width'], target['metric_checksum']), 'metric drift')
        require(mapped[metric][index] == target['point'], 'complete compiled signature drift')
        require(not (int(row['bits'], 16) >> (row['width'] - 1 - index)) & 1,
                'target hit on formal721')
        lower = (metric, index) in LOWER
        require(target['scope_status'] == ('HOLD_LOWER_EMUL_NOT_PROVEN_BY_VILL_CONTEXT'
                if lower else 'UPPER_EMUL_CANDIDATE_NOT_MEASURED'), 'classification drift')
        result.append(dict(target, role='LOWER_HOLD' if lower else 'UPPER_PROTECTED',
                           actual_native_identity_qualified=False))
    return result


def prepare():
    pins = {}

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = digest(path)
        require(expected is None or expected == actual, 'input drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'concurrent input drift')
        pins[str(path)] = actual
        return path

    def read(path, expected=None):
        return json.loads(pin(path, expected).read_text())

    admission = read(BASE / 'admission-manifest.json', SEAL)
    bits_path = BASE / 'combined-bits.json'
    bits = read(bits_path, admission['output_pins'][str(bits_path)])
    require(len(bits['tests']) == len(set(bits['tests'])) == 721, 'formal population drift')
    preflight = read(PREFLIGHT / 'preflight-manifest.json')
    require(preflight['baseline_manifest_seal'] == SEAL and not preflight['vcs_started']
            and not preflight['coverage_admitted'], 'preflight status drift')
    for name, expected in preflight['pins'].items():
        pin(name, expected)
    targets = read(PREFLIGHT / 'target-reconciliation721.json')
    proof = read(PREFLIGHT / 'emul-contract-proof.json')
    require(targets == preflight['targets'] and proof == preflight['emul_proof'],
            'preflight companion drift')
    require(proof['legal_vtype_memory_combinations'] == legal_proof()
            and proof['no_waiver_generated'], 'legal-only proof drift')
    snapshot = OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pin(snapshot, SOURCE_SHA)
    source_pins = read(OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json')
    require(source_pins[str(ROOT / 'hardware/src/ara_dispatcher.sv')] == SOURCE_SHA,
            'snapshot not compiled source')
    db = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    for relative, expected in bits['design'].items():
        pin(db / relative, expected)
    tree = inventory.read_xml(db / 'design/verilog.design.xml')
    nodes = {n.get('id'): (n, d) for d in tree.findall('srcdef') for n in d.findall('srcinst')}

    def path(key, ancestors=()):
        require(key not in ancestors, 'hierarchy cycle')
        n, _ = nodes[key]
        parent = n.get('pid')
        return (path(parent, ancestors + (key,)) + '.' if parent in nodes else '') + n.get('name')

    modules = [d for key, (_, d) in nodes.items() if path(key) == SCOPE]
    require(len(modules) == 1, 'ambiguous compiled child scope')
    module = modules[0]
    sourceinfo = inventory.read_xml(pin(db / 'auxiliary/verilog.sourceinfo.xml'))
    files = {n.get('id'): n.get('name') for n in sourceinfo.iter('fileinfo')}
    require(files['547'] == str(ROOT / 'hardware/src/ara_dispatcher.sv'), 'source file ID drift')
    mapped, coordinates, definitions = {}, {}, {}
    for metric in ('line', 'branch', 'cond'):
        row = bits['metrics'][metric][SCOPE]
        info = inventory.read_xml(pin(db / ('shape/%s.verilog.info.xml' % metric)))
        checksums = [n.get('chksum') for n in info.iter('instance_data') if n.get('name') == SCOPE]
        require(checksums == [row['checksum']], 'per-instance checksum drift')
        definition = inventory.definition(inventory.read_xml(db / ('shape/%s.verilog.shape.xml' % metric)),
                                          module, row['checksum'])
        coordinates[metric] = inventory.points(metric, definition, row['width'])
        mapped[metric] = {p['raw_index']: p for p in coordinates[metric]}
        definitions[metric] = dict(attributes=dict(definition.attrib), width=row['width'],
                                   checksum=row['checksum'])
    bound = bind_targets(targets, mapped, bits['metrics'])
    # No point is authorized for exclusion: even the four prospective points stay protected.
    protection = {m: dict(width=r[SCOPE]['width'], checksum=r[SCOPE]['checksum'],
                         protected_raw_indices=list(range(r[SCOPE]['width'])))
                  for m, r in bits['metrics'].items() if SCOPE in r}
    for name, expected in pins.items():
        require(digest(name) == expected, 'final input drift: ' + name)
    pin(__file__)
    pin(inventory.__file__)
    pin(inventory.score.__file__)
    return dict(status='READONLY_COMPILED_MAPPING_HOLD_NOT_NATIVE_QUALIFICATION',
                population=721, admission_seal=SEAL, scope=SCOPE,
                module_attributes=dict(module.attrib), frozen_source=str(snapshot),
                frozen_source_sha256=SOURCE_SHA, targets=bound, definitions=definitions,
                complete_source_coordinates=coordinates, protection=protection,
                legal_vtype_combinations=88, legal_minimum_EMUL='1/8',
                VILL_not_hit_evidence=True, actual_native_identity_qualified=False,
                interpretation='XML native_id/vector are compiled coordinates, not GUI ItemID/token. '
                    'Merged branch expressions are retained whole; singleton GUI identity remains unmeasured. '
                    'Legal-vtype arithmetic alone is not final source-proof waiver approval. '
                    'Reset/reserved/VILL decode reachability still requires review. Other scopes unchanged.',
                exclusions_generated=False, application_approval=False,
                dve_started=False, rtl_changed=False, input_pins=pins)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'fresh output required')
    report = prepare()
    args.output.mkdir(parents=True)
    target = args.output / 'mapping.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    seal = {'mapping_sha256': digest(target), 'input_pins': report['input_pins']}
    (args.output / 'seal.json').write_text(json.dumps(seal, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output), mapping_sha256=seal['mapping_sha256'],
                         targets=len(report['targets']), status=report['status'])))


if __name__ == '__main__':
    main()
