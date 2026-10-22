"""Independent read-only RR190/class-padding/FPNEW90 suffix-zero audit."""
import argparse
import hashlib
import json
from pathlib import Path

import report_population784_rr190 as prior

life, need = prior.life, prior.need
BASE = life.OUT / 'scalar-entropy64-offline-admitted788-agent-20261008-01'
BASE_SHA = 'cf59a7fd898c33493f662b247448d52642b694a6cce68785e938f20112d12641'
REPORT = life.OUT / 'current-population785-rr190-prepared-agent-20261008-01'
CONFIG_SHA = '796fbe9f3c009b8b6aed24b840d3699a965a9e257341757e5615d6b08b997a49'
QUAL_SHA = '8e0a97845146bd0296be674c65f889fae674d2726516c593be748c47d6f960c2'


def audit_rows(rows, families):
    prior.suffix_rows(rows, families)
    return {name: dict(scopes=len(groups), target_directions=sum(len(g['positions']) for g in groups.values()),
                      activated_directions=0) for name, groups in families}


def evidence():
    pins, contents = {}, {}
    def read(path, sha, structured=False):
        path = Path(path); key = str(path)
        need(key not in pins or pins[key] == sha, 'Conflicting expected SHA')
        if key not in contents:
            data = path.read_bytes(); need(hashlib.sha256(data).hexdigest() == sha, 'Bound file changed: ' + key)
            contents[key] = data; pins[key] = sha
        return json.loads(contents[key]) if structured else contents[key]
    config = read(REPORT / 'config.json', CONFIG_SHA, True)
    qualified = read(REPORT / 'qualification.json', QUAL_SHA, True)
    need(config['population'] == qualified['population'] == qualified['actual_selected_tests'] == 785 and
         qualified['config_seal'] == CONFIG_SHA and
         qualified['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         all(qualified[k] is True for k in ('complete_approved_EL_bitmask_union', 'all_other_bits_protected',
                                          'raw_reset_final_equal', 'applied_reloaded_equal')), 'Qualified785 predecessor')
    families = []
    sources = ((prior.native, prior.LOCAL, prior.LOCAL_SHA, 'RR190', 'missing_coordinates'),
               (prior.previous.native, prior.previous.LOCAL, prior.previous.LOCAL_CONFIG_SHA, 'CLASS_PADDING', 'raw_coordinates'),
               (prior.previous.previous.native, prior.previous.previous.LOCAL, prior.previous.previous.LOCAL_CONFIG_SHA, 'FPNEW90', 'coordinates'))
    for module, directory, seal, name, coordinate in sources:
        cfg = read(directory / 'config.json', seal, True)
        proof = read(module.SOURCE, module.SOURCE_SHA, True)
        need(cfg['design'] == config['input_ledger'][0], 'Same frozen native design')
        if name == 'RR190': prior.native.source_gate(proof)
        groups = prior.target_groups(proof, cfg, coordinate)
        families.append((name, groups))
        # Recheck the relevant source/compiled shape closure, not every historical ELF/log.
        for path, sha in proof['pins'].items():
            if path.endswith(('.sv', '.svh')) or '/shape/' in path or '/design/' in path or path.endswith('/build-source-pins.json'):
                read(path, sha)
    scopes = {s for _, groups in families for s in groups}
    records = []; directory, seal = BASE, BASE_SHA
    while len(records) < 3:
        manifest_path = directory / 'admission-manifest.json'
        manifest = read(manifest_path, seal, True)
        status_path = directory / 'status.json'
        status = read(status_path, manifest['output_pins'][str(status_path)], True)
        population = status['aggregate_passed']
        need(type(population) is int and population == 788 - len(records) and status['coverage_admitted'] is True and
             manifest['coverage_admitted'] is True and manifest['output'] == str(directory), 'Exact formal suffix status/owner')
        ledger_path = directory / 'combined-inputs.txt'
        ledger = read(ledger_path, manifest['output_pins'][str(ledger_path)]).decode().splitlines()
        need(len(ledger) == len(set(ledger)) == population + 1 and ledger[:786] == config['input_ledger'], 'Exact qualified785 prefix')
        paths = list((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(paths) == 1, 'One actual suffix Toggle member')
        path = paths[0]; sha = manifest['input_pins'][str(path)]; read(path, sha)
        rows, measured_sha = prior.native.source.rank.t.rows(path, scopes)
        need(measured_sha == sha, 'Suffix Toggle SHA race')
        summary = audit_rows(rows, families)
        records.append(dict(population=population, manifest=str(manifest_path), manifest_sha256=seal,
                            ledger=ledger, new_vdb=ledger[-1], toggle_data=str(path), toggle_sha256=sha, families=summary))
        directory, seal = Path(manifest['baseline']), manifest['baseline_seal']
    records.reverse()
    for previous, current in zip(records, records[1:]):
        need(current['ledger'][:-1] == previous['ledger'], 'Consecutive exact formal append')
    need(directory / 'admission-manifest.json' == Path(config['admission']['path']) and seal == config['admission']['sha256'], 'Exact785 ancestor seal')
    for record in records: record.pop('ledger')
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_audit_constant_suffix788.py'),
                 Path(prior.__file__).resolve(), Path(prior.population.__file__).resolve(),
                 Path(prior.native.source.rank.t.__file__).resolve()):
        read(path, life.digest(path))
    for path, sha in pins.items(): need(life.digest(Path(path)) == sha, 'Post-audit pin drift')
    return dict(status='FORMAL788_INHERITED_THREE_CONSTANT_FAMILIES_SUFFIX_ZERO_VERIFIED_NOT_REPORT',
        formal_population=788, formal_manifest=str(BASE / 'admission-manifest.json'), formal_seal=BASE_SHA,
        qualified_predecessor=dict(path=str(REPORT), config_seal=CONFIG_SHA, qualification_seal=QUAL_SHA),
        target_family_totals={name: dict(scopes=len(groups), directions=sum(len(g['positions']) for g in groups.values()))
                              for name, groups in families}, suffixes=records, input_pins=pins,
        native_MDA_mapping_inferred=False, exclusions_added=False, EDA_started=False, official_percentage_claimed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); value = evidence(); life.save(args.output, value)
    print(json.dumps(dict(status=value['status'], output=str(args.output), sha256=life.digest(args.output),
                          totals=value['target_family_totals'], suffix_populations=[r['population'] for r in value['suffixes']])))
