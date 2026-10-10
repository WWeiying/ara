"""Read-only substantive replay with an exact post-seal stdout append comparison."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path

import report_native_population_union_v2 as adapter

life, require = adapter.life, adapter.require
DEFAULT = life.OUT / 'native-population-union-full761-agent-20261007-03'
CONFIG_SHA = 'cd752e949804ba5cdb82e96ddca8e4b21dc1b5004fc90774938784841086e9aa'
QUAL_SHA = '4cd4ea9aee8d032fd496f93f2662a66c882a818a9af5ccdc5c9ab8f1fd384346'


def differences(before, after, path=''):
    if type(before) is not type(after):
        return [dict(path=path, before=before, after=after)]
    if isinstance(before, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            name = path + '/' + key
            if key not in before or key not in after:
                result.append(dict(path=name, before=before.get(key), after=after.get(key),
                                   presence_changed=True))
            else:
                result.extend(differences(before[key], after[key], name))
        return result
    return [] if before == after else [dict(path=path, before=before, after=after)]


def terminal_append(out, expected, qualification_sha):
    path = out / 'service.log'
    data = path.read_bytes()
    suffix = (json.dumps(dict(status=expected['status'], seal=qualification_sha,
                              system=expected['system'])) + '\n').encode('ascii')
    require(data.endswith(suffix), 'Service tail is not exact original verifier stdout')
    prefix = data[:-len(suffix)]
    require(hashlib.sha256(prefix).hexdigest() == expected['output_pins'][str(path)],
            'Service prefix does not reconstruct sealed bytes')
    identity = json.loads((out / 'live-identity.json').read_bytes())
    require(prefix == ('EXACT742_LIVE pid=%s launch=%s\n' %
                       (identity['pid'], identity['launch_pid'])).encode('ascii'),
            'Service prefix is not exact sealed launch identity')
    return dict(classification='EXACT_POST_QUALIFICATION_STDOUT_APPEND', path=str(path),
                sealed_sha256=expected['output_pins'][str(path)],
                current_sha256=hashlib.sha256(data).hexdigest(), prefix_bytes=len(prefix),
                appended_bytes=len(suffix), appended_json=json.loads(suffix),
                arbitrary_log_changes_allowed=False)


def compare_results(out, expected, actual, seal):
    fields = differences({k: v for k, v in expected.items() if k != 'output_pins'},
                         {k: v for k, v in actual.items() if k != 'output_pins'})
    old, new = expected['output_pins'], actual['output_pins']
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    changed = [dict(path=p, sealed_sha256=old[p], current_sha256=new[p])
               for p in sorted(set(old) & set(new)) if old[p] != new[p]]
    report = dict(substantive_field_differences=fields, added_output_paths=added,
                  removed_output_paths=removed, changed_output_pins=changed,
                  unchanged_output_pins=sum(old[p] == new[p] for p in set(old) & set(new)),
                  output_pin_count=len(old), approved_lifecycle_differences=[])
    require(not fields and not added and not removed, 'Substantive result/output set changed: ' + json.dumps(report))
    if changed:
        require([r['path'] for r in changed] == [str(out / 'service.log')],
                'Non-stdout output changed: ' + json.dumps(report))
        proof = terminal_append(out, expected, seal)
        require(proof['current_sha256'] == new[str(out / 'service.log')], 'Recomputed stdout hash differs')
        report['approved_lifecycle_differences'].append(proof)
    report['status'] = 'STRICT_SUBSTANTIVE_REPLAY_PASS_EXACT_STDOUT_APPEND_ONLY' if changed else 'EXACT_FULL_REPLAY_PASS'
    return report


def replay(out, config_sha, qualification_sha):
    expected = life.read_bound(out / 'qualification.json', qualification_sha)
    require(out == DEFAULT and config_sha == CONFIG_SHA and qualification_sha == QUAL_SHA and
            expected['config_seal'] == config_sha and expected['population'] == 761 and
            expected['status'] == 'SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED',
            'Only exact qualified761 artifacts are supported')
    # None of the original source/input gates is bypassed. Only the service log
    # has an explicitly reconstructed sealed prefix; all other outputs stay exact.
    life.check(expected['input_pins'])
    changed = {p: sha for p, sha in expected['output_pins'].items() if life.digest(Path(p)) != sha}
    require(not changed or set(changed) == {str(out / 'service.log')}, 'Unexpected output drift')
    if changed:
        terminal_append(out, expected, qualification_sha)
    life.check({p: sha for p, sha in expected['output_pins'].items() if p not in changed})
    ns = adapter.namespace()
    body = inspect.getsource(adapter.predecessor.verify)
    anchor = "require(json.loads(path.read_bytes()) == data, 'Sealed result differs')"
    require(body.count(anchor) == 1, 'Exact final immutable-save comparison anchor differs')
    calls, result = [], {}
    def capture(path, data):
        require(path == out / 'qualification.json' and not calls, 'Unexpected/repeated final save comparison')
        calls.append(path)
        result.update(compare_results(out, expected, data, qualification_sha))
    # Keep the v2 check/entry, original native audit engines, source parsers and
    # five-stage/module/root checks. Replace only the final immutable-save branch.
    ns['compare_final'] = capture
    body = body.replace(anchor, 'compare_final(path, data)')
    exec(compile(body, __file__, 'exec'), ns)
    ns['verify'](out, config_sha)
    require(calls == [out / 'qualification.json'], 'Full substantive verifier did not reach final comparison')
    require(life.digest(out / 'qualification.json') == qualification_sha and
            life.digest(out / 'config.json') == config_sha, 'Sealed artifacts changed')
    result.update(config_seal=config_sha, qualification_seal=qualification_sha,
        full_original_substantive_verifier_completed=True, exact_save_interceptions=1,
        source_and_input_gates_unchanged=True, five_stages_preserved=True,
        native_target_and_protected_gates_unchanged=True, sealed_artifacts_modified=False,
        EDA_launched=False, population=761, system=expected['system'],
        module_reports=expected['module_reports'], official_denominator_verified=False,
        integration_scope_not_new_RTL_signoff=True)
    pins = dict(expected['input_pins'])
    pins.update(expected['output_pins'])
    for proof in result['approved_lifecycle_differences']:
        pins[proof['path']] = proof['current_sha256']
    pins.update({str(out / 'qualification.json'): qualification_sha,
                 str(Path(__file__).resolve()): life.digest(Path(__file__).resolve()),
                 str(Path(__file__).with_name('test_compare_native_population_union_replay.py')):
                     life.digest(Path(__file__).with_name('test_compare_native_population_union_replay.py'))})
    life.check(pins)
    result['current_evidence_pins'] = pins
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report-output', type=Path, default=DEFAULT)
    p.add_argument('--config-seal', default=CONFIG_SHA)
    p.add_argument('--qualification-seal', default=QUAL_SHA)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); destination = a.output.resolve()
    require(destination.parent == life.OUT and not destination.exists(), 'Fresh independent evidence only')
    try:
        result = replay(a.report_output.resolve(), a.config_seal, a.qualification_seal)
    except Exception as error:
        life.save(destination, dict(status='HOLD_READONLY_REPLAY_REJECTED', reason=str(error),
            config_seal=a.config_seal, qualification_seal=a.qualification_seal,
            sealed_artifacts_modified=False, EDA_launched=False))
        raise
    life.save(destination, result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(destination),
        unchanged_output_pins=result['unchanged_output_pins'], differences=result['changed_output_pins'],
        output=str(destination))), flush=True)
