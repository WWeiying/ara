"""Evidence-bound wall budgets; never modify the RTL cycle watchdog or oracle."""
import copy
from pathlib import Path

import run_vcs_dve_checkpoint as base

POLICY = Path(__file__).with_name('reviewed_wall_budgets_20260930.json')


def apply(cases):
    policy = base.read(POLICY)
    if policy['version'] != 1 or len(policy['cases']) != 14:
        raise ValueError('Expected reviewed 14-case wall policy')
    adjusted = copy.deepcopy(cases)
    evidence = base.pins([POLICY, Path(__file__)])
    names = set()
    for rule in policy['cases']:
        name = rule['source_name']
        if name in names:
            raise ValueError('Duplicate wall-budget rule')
        names.add(name)
        matched = [c for c in adjusted if c.get('source_name') == name and c['elf_sha256'] == rule['elf_sha256']]
        if len(matched) != 1 or matched[0]['kind'] != 'directed':
            raise ValueError('Missing, ambiguous, or changed wall-budget ELF: ' + name)
        budget = rule['wall_seconds']
        expected = 7200 if name == 'app:akv_d256_reuse_smoke' else 2400 if name == 'app:akv_portability_smoke' else 1200
        if type(budget) is not int or budget != expected:
            raise ValueError('Unreviewed wall budget: ' + name)
        paths = [Path(rule[k]) for k in ('history_outcome', 'history_summary', 'history_audit')]
        outcome, summary, audit = map(base.read, paths)
        if (outcome['status'] != 'PASS' or outcome['elf_sha256'] != rule['elf_sha256'] or
                len(summary) != 1 or summary[0]['status'] != 'PASS' or summary[0]['name'] != name or
                audit.get('status') != 'PASS' or audit.get('errors') or
                not 0 < summary[0]['elapsed_s'] < budget):
            raise ValueError('Invalid historical wall-budget evidence: ' + name)
        evidence.update(base.pins(paths))
        case = matched[0]
        case['wall_timeout_adjustment'] = {'previous_seconds': case['timeout_s'],
            'reviewed_seconds': budget, 'evidence': str(paths[0]),
            'policy': str(POLICY), 'not_a_pass_claim': True}
        case['timeout_s'] = max(case['timeout_s'], budget)
    return adjusted, evidence
