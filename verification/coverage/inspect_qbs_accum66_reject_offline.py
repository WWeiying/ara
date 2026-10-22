"""Read-only validation of rejected accumulator native capture; never admission."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re

import qbs_accum66_native as original

OUT = original.life.OUT / 'qbs-accum66-native-agent-20261007-01'
DEST = original.life.OUT / 'qbs-accum66-native-reject-offline-agent-20261007-01'
SEAL = 'c08cab66d3ecd385d397b09433ea0daacc49fb9350a720eef396185a527f04c5'
FAILURE = 'Nonunique root not bound to exact fullscope/displayed node'
SCHEMA = ['Stage', 'Scope', 'Token', 'Handle', 'GUIPath', 'Name',
          'Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch']


def validate(out, config):
    need = original.require
    terminal = json.loads((out / 'terminal.json').read_bytes())
    need(terminal['returncode'] == 0 and terminal['timeout'] is False
         and len(terminal['actual_dve']) == 1, 'Native terminal is not successful')
    reject = json.loads((out / 'qualification-reject.json').read_bytes())
    need(reject == dict(status='REJECTED_NOT_QUALIFIED', reason='Native session failed',
         config_seal=SEAL, captures_preserved=True, automatic_retry=False), 'Original reject changed')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    error = (out / 'error.txt').read_text()
    need(log.splitlines().count('QBS_ACCUM66_FAILED ' + FAILURE) == 1
         and 'QBS_ACCUM66_NATIVE_DONE' not in log and error.startswith(FAILURE + '\n')
         and 'qc_capture before' in error and 'p740_summary $stage' in error,
         'Not the exact initial rooted-metric rejection')
    inventories = {}
    for index, instance in enumerate(config['instances']):
        inventories[instance['scope']] = original.inventory(out, config, 'before', index)
    need(sum(len(v) for v in inventories.values()) == 2425, 'Full initial inventory incomplete')
    need(len(list(out.glob('native_before_*.tsv'))) == 38, 'Foreign initial inventory')
    need(original.el(out, config, 'before') == []
         and (out / 'cleanup-empty.el').read_bytes() == b'', 'Initial/cleanup EL not empty')
    need(len(original.records((out / 'candidate.el').read_text(), config)) == 4224,
         'Prepared exact candidate changed')
    absent = ['actual-binding.json', 'capture-result.json']
    for stage in original.STAGES[1:]:
        need(not list(out.glob('native_' + stage + '_*.tsv')), 'Unexpected later stage inventory')
        absent.extend([original.EL_FILES[stage], 'rooted_' + stage + '.csv'])
    need(all(not (out / name).exists() for name in absent), 'Later stage/admission evidence appeared')
    with (out / 'rooted_before.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        need(reader.fieldnames == SCHEMA, 'Partial rooted schema differs')
        rows = list(reader)
    need(len(rows) == 3, 'Initial rooted prefix differs')
    for row, instance in zip(rows, config['instances']):
        scope = instance['scope']
        need(row['Stage'] == 'before' and row['Scope'] == row['Token'] == scope
             and row['Handle'].isdigit() and row['GUIPath'] == row['Name'] == scope.split('.')[-1],
             'Partial rooted prefix identity differs')
        for metric in SCHEMA[6:]:
            value = row[metric]
            need(value == 'NA' and metric == 'FSM' or
                 re.fullmatch(r'(?:0|[1-9][0-9]?|100)\.[0-9]{2}%', value) is not None
                 and 0 <= float(value[:-1]) <= 100, 'Partial rooted percent invalid')
    namespaces = defaultdict(list)
    for instance in config['instances']:
        namespaces[instance['scope'].split('.')[-1]].append(instance['scope'])
    return dict(status='BLOCKED_INCOMPLETE_NATIVE_ROUNDTRIP_NOT_QUALIFIED',
        config_seal=SEAL, original_capture=str(OUT), original_reject_preserved=True,
        native_returncode=0, native_timeout=False, original_harness_exit_failed=True,
        actual_dve=terminal['actual_dve'], before_scopes=38, before_objects=2425,
        before_target_objects=66, before_protected_typed_objects=2251,
        before_protected_arrays=108, before_all_objects_excluded_zero=True,
        prepared_candidate_source_bits=2112, prepared_candidate_direction_members=4224,
        prepared_candidate_is_not_native_saved_target_EL=True,
        initial_and_cleanup_global_EL_empty=True, completed_rooted_prefix=rows,
        failed_scope=config['instances'][3]['scope'],
        failed_stage='before/rooted metrics; before actual-binding and candidate load',
        failed_guard=FAILURE,
        guard_alternatives=['GUIPath differs from Name',
            'Name differs from basename and configured exact root alias', 'unexpected sibling'],
        exact_failed_GUI_operands_not_recorded=True,
        repeated_display_basenames={name: scopes for name, scopes in namespaces.items() if len(scopes) > 1},
        static_rooted_contract=dict(full_token='p740_select clears prior selection and checks one exact fullscope token',
            root='p740_row resets to ara_tb, selects exact token, and then sets CoverageTable root to that token',
            display='first child must have GUIPath==Name; Name must equal final basename or configured root alias; no sibling',
            configured_alias='selection.tcl binds each fullscope to only scope.split(.)[-1], not an observed generated display label',
            concrete_failed_scope=config['instances'][3]['scope']),
        unsupported_hypothesis='DVE may render generated scopes with a compound display name; not established by this capture',
        missing_required_stages=list(original.STAGES[1:]), missing_required_files=absent,
        native_qualified=False, coverage_admitted=False, population_application=False,
        official_denominator=None, measured_qualified_gain=None,
        conclusion='No offline repair can recover unexecuted apply/reset/reload/final captures. Keep scope and complement unchanged.',
        next_unified_session_contract=dict(local_native_retry=False,
            qualification='First actual five-stage qualification, not reuse of this incomplete capture',
            ordering='Run isolated66 five-stage qualification in the next unified session before loading the full approved report union; prior canonical exclusions must not contaminate its non-target0 proof',
            rooted_percentage_table_optional=True,
            scopes=38, objects=2425, target_fields=66, protected_typed=2251, protected_arrays=108,
            required=['fresh exact fullscope token selection with returned-token equality before each Toggle context',
                'full scoped actual path/meta/name/bounds inventory, immutable compiled/source checksums',
                'actual initial binding before applying any exclusion',
                'before/apply/reset/reload/final full inventories with every non-target excluded0',
                'typed saved EL exact target direction-member union and global non-target complement',
                'fullbatch EL union matches approved predecessor plus exact66; no foreign members',
                'reset/final/cleanup global EL empty; exact save/reload roundtrip',
                'actual successful native terminal, no timeout; original reject remains preserved'],
            metrics='Only actual unified DVE percentages may support report gain; no capacity estimate'),
        inventory= inventories)


def collect():
    config = original.life.read_bound(OUT / 'config.json', SEAL)
    original.contract(config)
    original.life.check(config['pins'])
    original.tools.revalidate(config['identity'])
    result = json.loads(json.dumps(validate(OUT, config)))
    result['pins'] = {**config['pins'], **{str(p): original.life.digest(p)
        for p in OUT.rglob('*') if p.is_file()}}
    for name in ('inspect_qbs_accum66_reject_offline.py', 'test_inspect_qbs_accum66_reject_offline.py'):
        p = Path(__file__).resolve().parent / name
        result['pins'][str(p)] = original.life.digest(p)
    original.life.check(result['pins'])
    return result


def main(destination):
    original.require(destination.parent == original.life.OUT, 'Independent workspace output required')
    result = collect()
    path = destination / 'inspection.json'
    if path.exists():
        original.require(json.loads(path.read_bytes()) == result, 'Independent inspection replay differs')
    else:
        original.require(not destination.exists(), 'Fresh output required')
        destination.mkdir()
        original.life.save(path, result)
    print(json.dumps(dict(status=result['status'], output=str(path), sha256=original.life.digest(path))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEST)
    main(parser.parse_args().output.absolute())
