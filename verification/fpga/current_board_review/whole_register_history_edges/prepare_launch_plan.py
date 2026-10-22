#!/usr/bin/env python3
"""Freeze a read-only input/budget plan. No worker, build, service or DUT calls."""
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREP = HERE / 'prepared02'
OUT = HERE / 'launch_plan01'
BASE = HERE.parent / 'integration'
sys.path.insert(0, str(BASE))
import replay_candidate04_regression_final as checked

spec = importlib.util.spec_from_file_location('history_edge_reference', HERE / 'prepare.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
read, sha, require = history.read, history.sha, history.require


def main():
    require(not OUT.exists(), 'Existing plan must not be overwritten')
    accepted = read(PREP / 'complete.json')
    require(sha(PREP / 'complete.json') == '36d3e1b15f276e3b438edb6cbc8d64a888e1e56f39f66e6207cde81c5afde273',
            'Accepted reference aggregate changed')
    require(accepted['status'] == 'HOST_SPIKE_ALL59_EDGES_118_CALLS_PASS_NOT_DUT', 'Reference incomplete')
    edges, coverage = history.geometry()
    history.check_edges(read(PREP / 'edges.json')['pairs'], edges)
    require(read(PREP / 'edges.json')['coverage'] == coverage, 'Saved coverage differs')
    require(accepted['coverage'] == coverage and [r['pair'] for r in accepted['pairs']] == list(range(59)),
            'Original59 coverage differs')
    require(not (PREP / 'failure.json').exists(), 'Reference failure artifact')
    pins = dict(read(PREP / 'input_pins.json'))
    cases = []
    for edge, row in zip(edges, accepted['pairs']):
        g = edge['pair']
        d = PREP / f'pair{g:02d}'
        require(read(d / 'complete.json') == row and row['status'] == 'SPIKE_PAIR_PASS_NOT_DUT', 'Pair record differs')
        require(row['output_byte_checks'] == [1088, 1088] and row['raw_exit'] == 0, 'Incomplete pair oracle')
        require(row['original_skips'] == len(edge['intervening_skips']), 'Skip count differs')
        require(sha(d / 'spike.log') == row['trace_sha256'], 'Spike reference trace changed')
        for backend, elf in row['elfs'].items():
            require(elf['path'] == str(d / (backend + '.elf')) and sha(Path(elf['path'])) == elf['sha256'],
                    'Accepted ELF changed')
        targets = read(d / 'soc.targets.json')
        cases.append(dict(id=f'whole_edge{g:02d}', pair=g, elf=row['elfs']['soc']['path'],
             sha256=row['elfs']['soc']['sha256'], timeout_s=600, outer_timeout_s=660,
             executed_ids=edge['executed_ids'], calls=edge['calls'], skips=edge['intervening_skips'],
             expected_second_entry_vtype=edge['expected_second_entry_vtype'],
             targets=[dict(op=c['op'], **targets[str(c['op'])]) for c in edge['calls']],
             symbols=str(d / 'soc.symbols.json'), output_byte_checks=[1088, 1088],
             pass_markers=[history.marker(edge), f'BOARD_CASE_PASS whole_edge{g:02d}', 'BOARD_REPLAY_PASS'],
             reference_minstret=row['minstret_at_raw_exit']))
        for name in ('complete.json', 'host.json', 'main.c', 'soc.elf', 'spike.elf', 'spike.log',
                     'soc.symbols.json', 'soc.targets.json', 'spike.symbols.json', 'spike.targets.json'):
            pins[str(d / name)] = sha(d / name)
    # Identity validation only: this helper does not inspect running campaigns.
    image, repo, _ = checked.original.identity()
    snapshot = Path(image['snapshot'])
    frozen = read(snapshot / 'snapshot.json')
    require(len(frozen['files']) == 539, 'Frozen source membership differs')
    pins.update(image['files'])
    pins.update({str(repo / name): digest for name, digest in frozen['files'].items()})
    paths = [Path(__file__), HERE / 'LAUNCH_PLAN.md', HERE / 'REFERENCE_REPORT.md', HERE / 'COUNT_AUDIT.json',
             PREP / 'complete.json', PREP / 'edges.json', PREP / 'input_pins.json', PREP / 'host_coverage.json',
             PREP / 'selection.diff', PREP / 'case.c', PREP / 'startup.S', PREP / 'runtime.c',
             PREP / 'replay.ld', PREP / 'host.c', PREP / 'original/whole.S',
             snapshot / 'snapshot.json', checked.original.IMAGE / 'image.json',
             Path(image['simv']).parent / 'simulator.conf', Path(image['simv']).parent / 'vcs_source_manifest.json']
    paths += [BASE / name for name in ('run.py', 'prepare.py', 'replay_memory_regression.py',
              'replay_candidate04_regression.py', 'replay_candidate04_regression_successor.py',
              'replay_candidate04_regression_final.py')]
    for path in paths:
        pins[str(path)] = sha(path)
    checked.base.verify_pins(pins)
    plan = dict(status='LAUNCH_PLAN_PREPARED_NOT_AUTHORIZED', executable_worker_ready=False, VCS_started=False,
         image=str(checked.original.IMAGE), image_sha256=checked.original.IMAGE_SHA,
         snapshot_sha256=image['snapshot_sha256'], image_files=image['files'], pins=pins,
         jobs=6, cases=cases, coverage=coverage, test_timeout_s=600, pair_outer_s=660,
         campaign_deadline_s=3000, service_runtime_max_s=3600, stop_first_fail=True,
         service='ara-whole-history59-candidate04-01.service',
         replace_reservation=dict(unit='ara-whole1134-candidate04-01.service', slots=6,
             output=str(HERE.parent / 'whole_register_original/vcs_candidate04_01'),
             prerequisite='Pinned parent strict terminal acceptance plus no residual owners; not yet supplied'),
         admission=dict(total_live_reserved_cap=24, minimum_available_bytes=32*1024**3,
                        attempts=1, current_parent_roster_required=True, no_busy_wait=True),
         oracle=dict(executed_calls=118, original_skips=117, output_byte_checks=128384,
                     target_order='exact pinned predecessor then successor', whole_preloads=236,
                     whole_output_stores=118, raw_exit=0, abort_allowed=False),
         remaining_before_launch=['Parent strict whole1134 terminal acceptance and slot release',
              'Minimal pair-specific CSV adapter/worker reviewed and pinned in successor launch seal',
              'Parent trigger plus fresh one-shot capacity/pin admission'],
         scope='All59 missing original adjacency pairs, fresh start per pair, not full1134 continuous history or Linux replay')
    OUT.mkdir()
    history.save(OUT / 'plan.json', plan)
    history.save(OUT / 'prepare_complete.json', dict(status='INPUT_BUDGET_PLAN_READY_NOT_LAUNCHED',
          plan_sha256=sha(OUT / 'plan.json'), cases=59, jobs=6, pins=len(pins),
          frozen_sources=539, image_files=len(image['files']), VCS_started=False,
          current_owner_progress_queried=False, executable_worker_ready=False))
    print(json.dumps(read(OUT / 'prepare_complete.json'), indent=2))


if __name__ == '__main__':
    main()
