"""Bounded six-policy eligibility audit; no historical prepare or EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / 'verification/out'
BASE = OUT / 'branch-combo-six-policy-population-723-parent-20261006-02'
LATEST = OUT / 'queue-mask-offline-admitted-740-agent-20261007-01'
SEALS = {
    LATEST / 'admission-manifest.json': '752d493c5fa8179ddd414d7810da479b1a56341a1600dff56c5b5afa0a3304b5',
    BASE / 'config.json': '391d4ae3ff427ba27f33fa6b7c47f7ccd7f193c92969b6daeccd4ad5ed9f3bc5',
    BASE / 'capture-result.json': 'ffb5573d71d9c9618a7c86216a29f0fab140c5f3662b8f80efc2a022d5495e0f',
    BASE / 'combined.el': '3e2345b2bc906413c1baf65dd912a15faa70d55276e7c0cd772585a591bbca7f',
    BASE / 'applied.el': '918418f549e18d8cf49d73a1353be806518402d88a22154726f289b15fe8e0e9',
    BASE / 'after-root.el': '918418f549e18d8cf49d73a1353be806518402d88a22154726f289b15fe8e0e9',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Evidence:
    def __init__(self):
        self.pins = {}

    def record(self, path, digest, expected=None):
        key = str(Path(path).absolute())
        require(key not in self.pins or self.pins[key] == digest, 'Conflicting identity: ' + key)
        require(expected is None or expected == digest, 'SHA mismatch: ' + key)
        self.pins[key] = digest
        return digest

    def read(self, path, expected=None):
        raw = Path(path).read_bytes()
        self.record(path, hashlib.sha256(raw).hexdigest(), expected)
        return raw

    def digest(self, path, expected=None):
        key = str(Path(path).absolute())
        if key not in self.pins:
            h = hashlib.sha256()
            with Path(path).open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
            self.record(path, h.hexdigest())
        return self.record(path, self.pins[key], expected)

    def load(self, path, expected=None):
        return json.loads(self.read(path, expected))


def native_worker():
    # Legacy imports mutate shared annotation globals: one process per group.
    x = json.load(sys.stdin)
    group, config = x['group'], x['config']
    if group == 'qbs':
        import apply_qbs_rooted_701 as m
        bind = lambda raw: m.base.qualification.bind_native(raw, config)
    elif group == 'debug':
        import apply_operand_debug_1832 as m
        bind = lambda raw: m.qualification.bind_native(raw, config)
    elif group == 'operand':
        import capture_operand_1144 as m

        def bind(raw):
            rows = m.parse_native(raw)
            expected = {r['scope'] + '|' + r['point']: r for r in config['qualified']}
            require(set(rows) == set(expected) and len(rows) == 1144, 'Operand population differs')
            for key, row in rows.items():
                n = expected[key]['native']
                require(row['checksum'] == n['checksum'] and row['directive'] == n['native_directive']
                        and row['signature'] == n['native_signature'] and row['annotation'] == m.ANNOTATION,
                        'Operand native signature differs')
            return rows
    else:
        import importlib
        m = importlib.import_module({'ff1': 'capture_ff1_native904',
                                     'exponent': 'capture_narrow_exponent_native1272',
                                     'pack': 'capture_fp16_pack_native208_v2'}[group])
        if group == 'pack':
            m.validate_plan(config['plan'])
        bind = lambda raw: m.bind_native(raw, config)
    checked = {}
    for name, text in x['native'].items():
        rows = bind(text.encode('ascii'))
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        require(digest == x['expected'], 'Native binding differs: ' + name)
        checked[name] = dict(records=len(rows), binding_sha256=digest)
    print(json.dumps(checked, sort_keys=True))


def coordinates(items):
    result = {}
    for scope, index in sorted(items):
        result.setdefault(scope, []).append(index)
    return result


def audit():
    import prepare_six_policy_population as population
    from inventory_operand_debug import Design
    frozen = population.frozen
    ev = Evidence()
    manifest = ev.load(LATEST / 'admission-manifest.json', SEALS[LATEST / 'admission-manifest.json'])
    require(manifest['schema'] == 'QUEUE_MASK_HISTORICAL740_ADMISSION_V1'
            and manifest['output'] == str(LATEST), 'Not exact formal740')
    files = manifest['output_pins']
    for name in ('combined-bits.json', 'combined-inputs.txt', 'status.json', 'evidence-pins.json'):
        require(str(LATEST / name) in files, 'Missing sealed admission output: ' + name)
    bitmap = ev.load(LATEST / 'combined-bits.json', files[str(LATEST / 'combined-bits.json')])
    status = ev.load(LATEST / 'status.json', files[str(LATEST / 'status.json')])
    inputs = ev.read(LATEST / 'combined-inputs.txt', files[str(LATEST / 'combined-inputs.txt')]).decode().splitlines()
    ledger = ev.load(LATEST / 'evidence-pins.json', files[str(LATEST / 'evidence-pins.json')])
    population.validate_population(bitmap, status, inputs, 740)
    require(all(ledger.get(path) == digest for path, digest in bitmap['input_hashes'].items()),
            'Member metric identity absent from sealed ledger')
    config = ev.load(BASE / 'config.json', SEALS[BASE / 'config.json'])
    result = ev.load(BASE / 'capture-result.json', SEALS[BASE / 'capture-result.json'])
    require(result['config_sha256'] == SEALS[BASE / 'config.json'] and result['tests'] == 723
            and result['records'] == 5808 and result['protected'] == 13562
            and result['final_reset'] is True and result['after_root_audit'] is True
            and result['after_root_native_export'] is True, 'Not completed exact723 native reference')
    require(all(g['plan']['design_vdb'] == inputs[0] for g in config['groups'].values()),
            'Mixed native/design input')
    for relative, digest in bitmap['design'].items():
        ev.digest(Path(inputs[0]) / 'snps/coverage/db' / relative, digest)
    context = population.Context(LATEST, SEALS[LATEST / 'admission-manifest.json'], 740)

    def source_digest(path):
        return ev.digest(context.mapping.get(str(Path(path).absolute()), path))

    source_binding = config['source_snapshot_binding']
    ev.digest(population.snapshot.BUILD, source_binding['build_manifest_sha256'])
    build = json.loads(ev.read(population.snapshot.BUILD))
    require(build[str(population.snapshot.HARDWARE_PATH)] == source_binding['sha256'],
            'Frozen source snapshot mapping differs')
    ev.digest(source_binding['snapshot'], source_binding['sha256'])
    review = population.review_function(740, source_digest)(config['groups'], bitmap, Design(Path(inputs[0])), 740)
    owners, targets, protected = frozen.inventory(config['groups'])
    native = {name: frozen.partition(ev.read(BASE / name, SEALS[BASE / name]), owners)
              for name in ('combined.el', 'applied.el', 'after-root.el')}
    bindings = {}
    for group in frozen.GROUPS:
        expected = result['group_results'][group]
        require(expected['binding_sha256'] == config['bindings'][group]['binding_sha256'],
                'Reference binding disagreement')
        for path, digest in expected['dependencies'].items():
            ev.digest(path, digest)
        request = dict(group=group, config=config['groups'][group], expected=expected['binding_sha256'],
                       native={name: parts[group].decode('ascii') for name, parts in native.items()})
        child = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--native-worker'],
                               input=json.dumps(request), text=True, capture_output=True, timeout=60, cwd=ROOT)
        require(child.returncode == 0, 'Isolated native binding failed: ' + group + ': ' + child.stderr)
        bindings[group] = json.loads(child.stdout)
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require(ev.read(BASE / name) == b'', 'Nonempty reset evidence')
    ev.digest(Path(__file__).resolve())
    return dict(schema='SIX_POLICY_FORMAL740_ELIGIBILITY_AUDIT_V1',
                status='EXACT_SIX_POLICY_740_ELIGIBLE_NOT_APPLIED', historical_only=True,
                current_RTL_signoff=False, aggregate_application_approval=False, EDA_launched=False,
                full_history_prepare_executed=False, member_files_rehashed=False,
                member_identity_basis='Exact sealed formal740 ledger; no readmission of historical ELF/oracles',
                admission=str(LATEST), admission_manifest_sha256=SEALS[LATEST / 'admission-manifest.json'],
                native_reference=str(BASE), source_snapshot_binding=source_binding,
                design_vdb=inputs[0], ordered_inputs=inputs, review=review,
                classifications=frozen.CLASSIFICATIONS, native_bindings=bindings,
                coordinates={g: dict(metric='branch', targets=coordinates(targets[g]),
                                     protected=coordinates(protected[g])) for g in frozen.GROUPS},
                evidence_pins=ev.pins,
                exclusions_not_included=['LZC', 'snapshot24', 'RVH'],
                percentage_claim=None,
                reuse=dict(application='prepare_six_policy_population.py private latest_review + isolated six workers',
                           population_schema_adapter_required='QUEUE_MASK_HISTORICAL740_ADMISSION_V1',
                           prohibit='historical full prepare/qualification707; shared-process legacy annotation globals'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--native-worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.native_worker:
        native_worker()
        return
    require(args.output is not None and not args.output.exists(), 'New output file required')
    report = audit()
    data = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as stream:
        stream.write(data)
    print(json.dumps(dict(output=str(args.output.absolute()), sha256=hashlib.sha256(data).hexdigest(),
                          status=report['status'], review=report['review']), sort_keys=True))


if __name__ == '__main__':
    main()
