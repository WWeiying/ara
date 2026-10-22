#!/usr/bin/env python3
"""Future fresh-image recollection with all reviewed long-case wall budgets."""
import run_repaired_recollection_20260930 as entry
import reviewed_wall_budgets as budgets

original = entry.reviewed_inventory


def inventory(selection):
    selected = original(selection)
    selected['cases'], evidence = budgets.apply(selected['cases'])
    selected['files'].update(evidence)
    selected['case_bounds'] = entry.campaign.validate_bounds(selected['cases'], selected['gate_cases']) if all(
        c['timeout_s'] <= 1800 for c in selected['cases']) else reviewed_bounds(selected)
    return selected


def reviewed_bounds(selected):
    # The old generic 1800-second cap stays in force for unreviewed cases.
    bounded = []
    for case in selected['cases']:
        copy = dict(case)
        if copy['timeout_s'] > 1800:
            if copy.get('wall_timeout_adjustment', {}).get('policy') != str(budgets.POLICY):
                raise ValueError('Unreviewed long wall budget')
            copy['timeout_s'] = 1800
        bounded.append(copy)
    result = entry.campaign.validate_bounds(bounded, selected['gate_cases'])
    for case in selected['cases']:
        result[case['name']].update(rtl_wall_s=case['timeout_s'], runner_outer_s=case['timeout_s'] + 600)
    return result


if __name__ == '__main__':
    entry.reviewed_inventory = inventory
    entry.main()
