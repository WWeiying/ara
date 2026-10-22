"""Immutable full771 observer reconciliation; no new exclusion or EDA entry."""
import argparse
import copy
import csv
import inspect
import json
from pathlib import Path
import subprocess
from types import FunctionType, SimpleNamespace
import c910_prepare_pack_native as native
import report_native_full771 as frozen

life, require = frozen.life, frozen.require
OUT = life.OUT / 'native-full771-padding-pack-prepared-agent-20261007-01'
SEAL = '3269a95bf92f99d3c4e31066b6807176e65e7f36c74a374752f9ac52bafcdbb0'
OWNER_SEAL = 'c9611bb7e6ea4bbe197f4198d639ed2b3148c88ea62afd4d4608da812362fada'
OWNER_CONFIG = '5fb95c5a9f572e4a4cf26a35c7b5f341e07821979d10e3eb392da1c57befcb3a'
NAMES = {'ex4_expnt_rst': (12, 0, 'net'), 'ex4_frac': (54, 0, 'net'),
         'ex4_frac_52': (51, 0, 'reg')}
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')
UNIT = 'ara-native-full771-parent-20261007-01.service'


def corrected_groups(groups, instances, bindings, authority):
    result = copy.deepcopy(groups)
    proofs = []
    expected = set()
    for instance in instances:
        if instance['module'] != 'ct_vfdsu_pack' or not instance['targets']:
            continue
        scope = instance['scope']
        require(len(instance['targets']) == 3 and
                {n['name'] for n in instance['targets']} == set(NAMES), 'Exact pack three owners')
        matches = [(k, g) for k, g in result.items() if g['scope'] == scope]
        require(len(matches) == 1 and matches[0][0].startswith('pack323'), 'Unique pack323 observer')
        key, group = matches[0]
        labels = []
        for name, (left, right, typ) in NAMES.items():
            b = bindings[scope, name]
            require((b['left'], b['right'], b['native_type']) == (left, right, typ) and
                    b['design_checksum'] == instance['design_checksum'] and
                    b['toggle_checksum'] == instance['toggle_checksum'], 'Exact owner type/bounds/checksums')
            record = (scope, name, json.dumps(b, sort_keys=True))
            require(record in authority, 'Existing qualified canonical owner required')
            label = '%s[%d:%d]' % (name, left, right)
            require(sum(r[2] == label for r in group['reference']) == 1 and
                    label not in group['targets'], 'Unique previously protected owner')
            labels.append(label)
            expected.add((scope, label))
        group['targets'] = sorted(set(group['targets']) | set(labels))
        proofs.append(dict(key=key, scope=scope, labels=sorted(labels),
                           source_bindings={name: bindings[scope, name] for name in NAMES}))
    require(len(proofs) == 16 and len(expected) == 48, 'Exact16 vector scopes/48 existing owners')
    return result, proofs, expected


def differences(out, original, corrected, expected):
    found = []
    for index, (key, group) in enumerate(original.items()):
        for stage in STAGES:
            with (out / ('observer766_%s_%d.tsv' % (stage, index))).open() as stream:
                for row in csv.DictReader(stream, delimiter='\t'):
                    wanted = str(int(stage in ('selected', 'reloaded') and row['name'] in group['targets']))
                    if row['excluded'] == wanted:
                        continue
                    require((group['scope'], row['name']) in expected and
                            stage in ('selected', 'reloaded') and wanted == '0' and row['excluded'] == '1',
                            'Unexpected ownership conflict/stage/flag')
                    found.append((group['scope'], row['name'], stage))
    require(set(found) == {(s, n, t) for s, n in expected for t in ('selected', 'reloaded')}
            and len(found) == 96, 'Exact96 conflicts required')
    return found


def audit(out, c):
    family = c['future_captures']['c910240']
    require(family['seal'] == OWNER_SEAL, 'Exact qualified family seal')
    owner = Path(family['output'])
    q = life.read_bound(owner / 'capture-result.json', OWNER_SEAL)
    require(q['status'] == 'EXACT_C910_PREPARE192_PACK48_NATIVE_ROUNDTRIP_PASS' and
            q['semantic_reload'] is True and q['reset_global_empty'] is True and
            q['non_target_exclusions'] == 0 and q['population_application'] is False,
            'Existing qualification scope/status differs')
    oc = life.read_bound(owner / 'config.json', OWNER_CONFIG)
    bindings = native.source_bindings(oc)
    first = native.parse_el((owner / 'first.el').read_text(), oc)
    require(first == native.parse_el((owner / 'second.el').read_text(), oc) and
            [list(r) for r in first] == family['canonical_records'] and
            [list(r) for r in first] == c['expected_union']['c910240'],
            'Exact240 native reload/union ownership')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require((owner / name).read_bytes() == b'', 'Existing native empty stage differs')
    original = frozen.model()['merged_observers'](c)
    corrected, proof, expected = corrected_groups(original, oc['instances'], bindings,
                                                  {tuple(r) for r in first})
    for name in ('applied.el', 'reloaded.el'):
        frozen.canonical_gate(c, (out / name).read_text())
    conflicts = differences(out, original, corrected, expected)
    frozen.base.prior.audit_observers(out, dict(c, observer_captures=corrected))
    return dict(existing_owner_family='c910240', owner_seal=OWNER_SEAL,
                owner_config_seal=OWNER_CONFIG, source_proof=proof,
                unique_existing_objects=48, conflicts=conflicts, changed_EL_coordinates=0,
                five_stage_full_complement_passed=True, scalar_pack_and_ports_retained=True,
                dynamic_arithmetic_not_constant=True), q, oc


def verify(destination):
    require(destination.parent == life.OUT and not destination.exists(), 'Fresh offline output')
    require(not (OUT / 'qualification.json').exists(), 'Preserve original failed report')
    c = life.read_bound(OUT / 'config.json', SEAL)
    require(c['schema'] == frozen.SCHEMA and c['population'] == 771 and c['output'] == str(OUT),
            'Exact failed full771 identity')
    failure = json.loads((OUT / 'failure.json').read_bytes())
    require(failure == dict(reason='Observer target/protected membership differs: ex4_expnt_rst[12:0]',
                            no_retry=True), 'Exact original failure')
    before = {str(p): life.digest(p) for p in OUT.rglob('*') if p.is_file()}
    proof, q, oc = audit(OUT, c)
    # Validate each unique historical input once, rather than re-running producers.
    pins = {}
    for book in (c['pins'], q['pins'], oc['pins']):
        for path, sha in book.items():
            require(path not in pins or pins[path] == sha, 'Conflicting input pins')
            pins[path] = sha
    life.check(pins)
    external = {str(Path(__file__).resolve()): life.digest(__file__),
                str(Path(__file__).with_name('test_verify_full771_pack_owner_offline.py')):
                life.digest(Path(__file__).with_name('test_verify_full771_pack_owner_offline.py'))}
    names = 'Id,LoadState,ActiveState,SubState,ExecMainPID,ExecMainCode,ExecMainStatus,ExecStart'
    text = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '--property=' + names], text=True)
    fields = dict(line.split('=', 1) for line in text.splitlines())
    require(all(fields.get(k) == v for k, v in dict(Id=UNIT, LoadState='loaded', ActiveState='failed',
                SubState='failed', ExecMainPID='334704', ExecMainCode='1', ExecMainStatus='1').items()),
            'Exact original terminal wrapper failure required')
    require(str(Path(frozen.__file__).resolve()) in fields['ExecStart'] and
            str(OUT) in fields['ExecStart'] and SEAL in fields['ExecStart'], 'Original command identity')
    live = json.loads((OUT / 'live-identity.json').read_bytes())
    log = (OUT / 'service.log').read_text()
    require(live['executable_verified'] is True and
            log.startswith('EXACT742_LIVE pid=%s launch=%s\n' % (live['pid'], live['launch_pid'])) and
            log.count('Traceback (most recent call last):') == 1 and
            log.rstrip().endswith('ValueError: ' + failure['reason']), 'Exact verifier-only failure log')
    body = inspect.getsource(frozen.predecessor.frozen.closure.report.base.prior.old.frozen.prior.old.base.run)
    require("require(code == 0, 'DVE nonzero exit')\n        verify(out, seal)" in body,
            'Original zero-return-before-verify source guard')
    life.check(before)
    destination.mkdir()
    result = dict(status='FULL771_PACK_EXISTING_OWNER_FIVE_STAGE_OFFLINE_AUDIT_PASS',
                  population=771, config_seal=SEAL, original_output=str(OUT),
                  observer_owner_reconciliation=proof, input_pins=pins, output_pins=before,
                  adapter_pins=external, original_failure_preserved=True, EDA_launched=False,
                  complete_report_qualification=False,
                  remaining_gate='Replay remaining frozen full771 report verifier with private owner adapter')
    life.save(destination / 'owner-audit.json', result)
    # Reuse every substantive frozen report check. Only observer ownership and the
    # final write destination differ; no historical producer is re-executed.
    ns = frozen.namespace()
    qualified = {}
    def check(out, seal):
        require(out == OUT and seal == SEAL and life.digest(out / 'config.json') == seal,
                'Immutable full771 config identity')
        return c
    def snapshot(data, out):
        require(out == OUT and data['output_pins'] == before, 'Original complete output identity')
        data.update(population=771, formal771_manifest_seal=frozen.MANIFEST_SHA,
                    added_qualified_families=sorted(frozen.ADDED), excluded_MFPU272=False,
                    monitor_included=False, observer_owner_reconciliation=proof,
                    original_failure_preserved=True, EDA_replayed=False,
                    lifecycle_stdout=dict(path=str(OUT / 'service.log'), sha256=before[str(OUT / 'service.log')],
                                          immutable_terminal_log=True, no_snapshot_copy=True),
                    terminal_evidence=dict(wrapper_OS_exit_status=1, launch_process_returncode=0,
                        standalone_DVE_OS_return_receipt_available=False,
                        source='PINNED_ZERO_RETURN_GUARD_AND_VERIFIER_ONLY_TRACEBACK',
                        systemd_properties=fields, live_identity=live))
    def save(path, data):
        require(path == OUT / 'qualification.json' and not qualified, 'Only redirect final qualification')
        qualified.update(copy.deepcopy(data))
        qualified['offline_adapter_pins'] = external
        life.check(before); life.check(external)
        life.save(destination / 'qualification.json', qualified)
    def digest(path):
        if Path(path) == OUT / 'qualification.json':
            require(qualified, 'Qualification not generated')
            return life.digest(destination / 'qualification.json')
        return life.digest(path)
    def observers(out, config):
        require(out == OUT and config is c, 'Private observer consumption identity')
        return proof
    ns.update(check=check, audit_observers=observers, snapshot_stdout=snapshot,
              life=SimpleNamespace(**dict(vars(life), save=save, digest=digest)))
    FunctionType(ns['verify'].__code__, ns)(OUT, SEAL)
    require(qualified and qualified['population'] == 771 and qualified['config_seal'] == SEAL,
            'Full substantive report replay incomplete')
    life.check(before); life.check(external)
    closure = dict(status='FULL771_EXISTING_PACK_OWNER_OFFLINE_CLOSURE_PASS',
        population=771, config_seal=SEAL, qualification_sha256=life.digest(destination / 'qualification.json'),
        owner_audit_sha256=life.digest(destination / 'owner-audit.json'), input_pins=before,
        adapter_pins=external, source_directory_unchanged=True, original_failure_preserved=True,
        EDA_launched=False, changed_EL_coordinates=0)
    life.save(destination / 'closure.json', closure)
    print(json.dumps(dict(output=str(destination), closure_seal=life.digest(destination / 'closure.json'),
                          qualification_seal=closure['qualification_sha256'], system=qualified['system'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args().output.resolve())
