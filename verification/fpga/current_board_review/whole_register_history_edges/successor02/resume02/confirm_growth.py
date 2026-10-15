#!/usr/bin/env python3
"""One two-sample CSV growth observation; no service/process polling."""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parent/'preflight01'


def sample(path):
    with path.open('rb') as f:
        size = f.seek(0, 2)
        offset = max(0, size-65536)
        f.seek(offset)
        chunk = f.read()
    lines = chunk.decode().split('\n')[:-1]
    if offset:
        lines = lines[1:]
    rows = list(csv.reader(lines))
    rows = [r for r in rows if len(r) == 14 and r[0].isdigit()]
    retire = next(r for r in reversed(rows) if r[1] == 'retire')
    return dict(bytes=size, last_cycle=int(rows[-1][0]), retire_cycle=int(retire[0]),
                retire_order=int(retire[2]), retire_pc=retire[5])


def main():
    paths = [OUT/'pairs'/f'pair{n:02d}'/'run/tests'/f'whole_edge{n:02d}'/'commit_trace.csv' for n in range(6)]
    before = {str(p): sample(p) for p in paths}
    time.sleep(3)
    after = {str(p): sample(p) for p in paths}
    growth = {p: dict(bytes=after[p]['bytes']-b['bytes'], cycles=after[p]['last_cycle']-b['last_cycle'],
                      retirements=after[p]['retire_order']-b['retire_order']) for p, b in before.items()}
    moving = [p for p, g in growth.items() if g['bytes'] > 0 and g['cycles'] > 0 and g['retirements'] > 0]
    evidence = dict(status='STARTUP_TRACE_GROWTH_CONFIRMED_NOT_DUT_PASS' if moving else 'NO_GROWTH_OBSERVED',
         utc=datetime.now(timezone.utc).isoformat(), interval_s=3, before=before, after=after, growth=growth,
         moving_traces=len(moving), service='ara-whole-history59-candidate04-01.service',
         service_proof_source='Parent explicit one-time observation, not re-queried here',
         parent_observation=dict(active=True, MainPID=450565, simv_pids=list(range(451223,451229)),
                                 private_ELF_and_trace_paths_verified=True),
         additional_service_queries=0, additional_process_queries=0,
         note='No further observation/polling. Background service continues under existing bounds.')
    with (HERE/'startup_observation.json').open('x') as f:
        json.dump(evidence, f, indent=2)
        f.write('\n')
    print(json.dumps(dict(status=evidence['status'], moving_traces=len(moving), growth=growth), indent=2))
    if not moving:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
