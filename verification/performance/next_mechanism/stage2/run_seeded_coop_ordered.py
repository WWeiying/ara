#!/usr/bin/env python3
"""TB declaration-order successor; preserve the original 02 compile failure."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
import run_seeded_coop_local as prior

HERE = Path(__file__).resolve().parent
BASE_BENCH = prior.v1.bench_source
NEW = ('run_seeded_coop_ordered.py','test_seeded_coop_ordered.py')


def bench_source(original, scenarios):
    text = BASE_BENCH(original,scenarios)
    ports = scenarios.split('// BEGIN ROUTINES\n',1)[0]
    marker = '  always_ff @(posedge clk or negedge rst_n) begin\n'
    if ports.count(marker) != 1: raise ValueError('Non-unique directed monitor boundary')
    monitors = marker+ports.split(marker,1)[1]
    text = prior.v1.tools.once(text,monitors,'')
    text = prior.v1.tools.once(text,'  task automatic load_seed_vectors;',
                               monitors+'\n  task automatic load_seed_vectors;')
    # A pure relocation: restoring the old location must reproduce 02 exactly.
    restored = prior.v1.tools.once(text,monitors+'\n  task automatic load_seed_vectors;',
                                  '  task automatic load_seed_vectors;')
    restored = prior.v1.tools.once(restored,'\n  qbs_engine_composed #(\n',
                                  monitors+'\n  qbs_engine_composed #(\n')
    if restored != BASE_BENCH(original,scenarios):
        raise ValueError('Declaration-order repair changed test behavior')
    return text


def prepare(out):
    prior.v1.bench_source = bench_source
    prior.prepare(out)
    local = out/'inputs'/HERE.relative_to(prior.v1.ROOT)
    pins = json.loads((out/'source-pins.json').read_text())
    for name in NEW:
        source,target = HERE/name,local/name
        h=prior.v1.tools.sha(source); shutil.copyfile(source,target)
        if prior.v1.tools.sha(target)!=h: raise ValueError('Ordered successor snapshot race')
        pins[str(source)]=pins[str(target)]=h
    prior.v1.tools.command([sys.executable,'-B',local/'test_seeded_coop_ordered.py'],
        out,out/'ordered-host-tests.log',time.monotonic()+60,60)
    pins[str(out/'ordered-host-tests.log')]=prior.v1.tools.sha(out/'ordered-host-tests.log')
    config=json.loads((out/'selection.json').read_text())
    config.update(ordered_entry=str(local/NEW[0]),repair='Relocate test monitors after canonical declarations only',
                  preserved_failure=str(prior.v1.OUT/'stage2_seeded_coop_vcs_20261110_02'))
    prior.v1.tools.save(out/'selection.json',config)
    pins[str(out/'selection.json')]=prior.v1.tools.sha(out/'selection.json')
    prior.v1.tools.verify(pins); prior.v1.tools.save(out/'source-pins.json',pins)
    prior.v1.tools.save(out/'prepared.json',dict(state='PREPARED_NOT_EXECUTED',frozen_runner=config['ordered_entry'],
        source_pins_sha256=prior.v1.tools.sha(out/'source-pins.json')))
    print('SEEDED_ORDERED_PREPARED '+str(out),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--execute',action='store_true')
    a=p.parse_args(); out=a.output.resolve()
    if a.execute:
        if str(Path(__file__).resolve())!=json.loads((out/'selection.json').read_text())['ordered_entry']:
            raise ValueError('Use frozen ordered successor')
        raise SystemExit(prior.execute(out))
    prepare(out)
