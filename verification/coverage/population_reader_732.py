"""Exact formal732 root binding for the unwired next-report epoch consumer.

Metadata bootstrap is a separate integrity phase. A future pre-run epoch must
recheck every inherited ledger pin and source/native gate, consume an immutable
snapshot, and use a new post-run epoch. This adapter performs no EDA, population
extension, admission, bitmap OR, or historical policy qualification.
"""
import argparse
from dataclasses import dataclass
import os
from pathlib import Path
from types import MappingProxyType

from population_reader_epoch import PopulationReaderEpoch, require
import verification_epoch as core

ROOT = Path(__file__).resolve().parents[2]
ADMISSION = ROOT / 'verification/out/gap109-offline-admitted-732-parent-20261006-01'
SEAL = 'badbcc7aad21ce6dab6c8c0eeabc7f85b2c13226bbe893a56c88995eab149794'
SCHEMA = 'GAP109_HISTORICAL732_SOFTWARE_NATIVE_ADMISSION_V1'
OUTPUTS = frozenset(('combined-bits.json', 'single-bits.json', 'raw-delta.json',
    'gained-compiled-points.json', 'target-hits.json', 'native-runtime-audit.json',
    'evidence-pins.json', 'status.json', 'combined-inputs.txt'))


def merge_pins(*groups):
    result = {}
    for group in groups:
        for name, expected in group.items():
            name = str(core._path(name))
            expected = core._sha(expected)
            require(result.get(name, expected) == expected, 'Conflicting pin authority: ' + name)
            result[name] = expected
    return result


def validate_manifest(manifest, admission):
    require(manifest['schema'] == SCHEMA and manifest['output'] == str(admission),
            'Exact732 schema/output required')
    expected = {str(admission / name) for name in OUTPUTS}
    require(set(manifest['output_pins']) == expected, 'Exact nine canonical732 outputs required')
    merge_pins(manifest['output_pins'])
    require(Path(manifest['baseline']).name == 'pure-war-offline-admitted-731-parent-20261006-01'
            and manifest['baseline_seal'] ==
            '79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641',
            'Exact formal731 predecessor reference required')
    for key in ('qualification_seal', 'candidate_seal', 'prepared_seal'):
        core._sha(manifest[key])


def validate_status(status, manifest):
    require(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            all(type(status[key]) is int for key in ('baseline', 'aggregate_passed', 'new_passed')) and
            (status['baseline'], status['aggregate_passed'], status['new_passed']) == (731, 732, 1),
            'Exact PASS-only732 population required')
    for key in ('coverage_admitted', 'exact731_prefix', 'complete_software_native_qualified',
                'whole_VRF_CSR_source_guards_qualified', 'inherited731_pins_rechecked',
                'historical_old_image_only'):
        require(status[key] is True, 'Required732 qualification flag differs: ' + key)
    for key in ('full_scalar_isa_verified', 'spike_custom_isa_pass', 'official_DVE_report',
                'rtl_changed', 'simulations_started'):
        require(status[key] is False, 'Actual732 qualification scope differs: ' + key)
    require(dict(status['raw_delta']) == dict(line=0, cond=2, branch=0, fsm=0) and
            all(type(value) is int for value in status['raw_delta'].values()),
            'Actual732 delta differs')
    require(status['qualification_seal'] == manifest['qualification_seal'] and
            status['candidate_seal'] == manifest['candidate_seal'], 'Qualification references differ')


@dataclass(frozen=True)
class RootBinding:
    admission: Path
    seal: str
    manifest: object
    status: object
    ledger: object
    pins: object
    pending_literal_paths: tuple

    def new_pre_run_epoch(self, *, additional_pins=None, aliases=None, json_paths=(), **budgets):
        """Create, never reuse, a complete-pin epoch; no automatic qualification."""
        require(not self.pending_literal_paths,
                'Legacy literal paths require explicit reviewed endpoint adapter; never drop/normalize pins')
        pins = merge_pins(self.ledger, self.pins, additional_pins or {})
        return PopulationReaderEpoch(pins, aliases, json_paths=json_paths, **budgets)


def bind_root(admission, seal):
    admission = core._path(admission)
    require(admission.resolve(strict=True) == admission, 'Canonical admission root required')
    path = admission / 'admission-manifest.json'
    bootstrap = PopulationReaderEpoch({str(path): seal}, json_paths=[str(path)])
    manifest = bootstrap.load_sealed(path, seal)
    bootstrap.finish()
    bootstrap.close()
    validate_manifest(manifest, admission)
    outputs = manifest['output_pins']
    status_path, ledger_path = admission / 'status.json', admission / 'evidence-pins.json'
    reader = PopulationReaderEpoch(outputs, json_paths=[str(status_path), str(ledger_path)])
    status = reader.load_sealed(status_path, outputs[str(status_path)])
    ledger = reader.load_sealed(ledger_path, outputs[str(ledger_path)])
    validate_status(status, manifest)
    require(isinstance(ledger, MappingProxyType) and len(ledger) > 0, 'Nonempty exact ledger required')
    pending = []
    authorities = dict(outputs, **{str(path): seal})
    for name, expected in ledger.items():
        require(isinstance(name, str) and os.path.isabs(name), 'Absolute ledger path required')
        core._sha(expected)
        require(authorities.get(name, expected) == expected, 'Ledger/output pin conflict')
        if name != os.path.normpath(name):
            pending.append(name)
    reader.check_pins(outputs)
    reader.finish()
    reader.close()
    return RootBinding(admission, seal, manifest, status, ledger,
                       MappingProxyType(merge_pins(outputs, {str(path): seal})), tuple(sorted(pending)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('check-root',))
    parser.parse_args()
    root = bind_root(ADMISSION, SEAL)
    import json
    print(json.dumps(dict(status='BOUND_FORMAL732_ROOT_METADATA_ONLY_NOT_REPORT_READY',
        admission=str(root.admission), seal=root.seal, population=732,
        output_pins=len(root.manifest['output_pins']), inherited_ledger_pins=len(root.ledger),
        pending_literal_path_count=len(root.pending_literal_paths),
        inherited_ledger_content_rechecked=False, complete_membership_reconstructed=False,
        native_policy_requalified=False, full_scalar_isa_verified=False,
        immutable_consumed_filesystem_proved=False, EDA_started=False)))


if __name__ == '__main__':
    main()
