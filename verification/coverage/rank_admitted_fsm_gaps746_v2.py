"""Normalize both qualified native record schemas before gap prioritization."""
import argparse
from pathlib import Path
from types import FunctionType
import rank_admitted_fsm_gaps746 as original


def exclusions(tree):
    for record in original.exclusions(tree):
        if record[0] == 'fsm':
            _, scope, module, metric, machine, machine_sha, kind, name, signature = record
            yield (module, metric, scope, machine, machine_sha, '', kind, name, signature)
        else:
            yield record


def collect():
    namespace = dict(original.collect.__globals__, exclusions=exclusions,
                     __file__=str(Path(__file__).resolve()))
    result = FunctionType(original.collect.__code__, namespace)()
    result['supersedes_diagnostic_only'] = str(original.life.OUT /
        'admitted746-fsm-priority-parent-20261007-01.json')
    result['correction'] = ('DWC native schema starts with metric kind; now normalized. '
                           'The previous ranking did not apply exclusions or report percentages.')
    for path in (Path(original.__file__).resolve(),
                 Path(original.__file__).with_name('test_rank_admitted_fsm_gaps746.py')):
        result['pins'][str(path)] = original.life.digest(path)
    original.life.check(result['pins'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original.require(args.output.parent.resolve() == original.life.OUT and
                     not args.output.exists(), 'Fresh output only')
    result = collect()
    original.life.save(args.output, result)
    for row in result['instances'][:15]:
        print(row['remaining_transitions'], row['remaining_states'], row['scope'])
