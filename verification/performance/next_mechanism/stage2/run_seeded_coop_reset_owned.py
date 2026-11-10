#!/usr/bin/env python3
"""Remove only declaration initialization of the three reset-owned TB registers."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import time

sys.dont_write_bytecode=True
import run_seeded_coop_ordered as prior

HERE=Path(__file__).resolve().parent
ORIGINAL_BENCH=prior.BASE_BENCH
NEW=('run_seeded_coop_reset_owned.py','test_seeded_coop_reset_owned.py')
DECLARATIONS=(('  logic [3:0] delayed_final = 0;','  logic [3:0] delayed_final;'),
    ('  int cycles = 0, final_wait = 0;','  int cycles = 0, final_wait;'),
    ('  bit first_write = 0, active = 0, terminal_seen = 0;',
     '  bit first_write, active = 0, terminal_seen = 0;'))


def base_bench(original,scenarios):
    changed=scenarios
    for before,after in DECLARATIONS: changed=prior.prior.v1.tools.once(changed,before,after)
    result=ORIGINAL_BENCH(original,changed)
    restored=result
    for before,after in reversed(DECLARATIONS): restored=prior.prior.v1.tools.once(restored,after,before)
    if restored!=ORIGINAL_BENCH(original,scenarios): raise ValueError('Repair changed more than initializers')
    return result


def audit_generated(text):
    for name,count in (('delayed_final',2),('final_wait',4),('first_write',3)):
        if len(re.findall(r'\b'+name+r'\s*(?:<=|=(?!=))',text))!=count:
            raise ValueError('Unexpected reset-register writer count: '+name)
    if not (text.index('  logic score_commit;')<text.index('    cycles <= cycles+1;') and
            text.index('  integer score_vd;')<text.index('    cycles <= cycles+1;') and
            text.index('  integer score_vd;')<text.index('  int local_seed_checks=0')):
        raise ValueError('New probe precedes canonical declarations')
    if '-ignore initializer_driver_checks' in text: raise ValueError('No driver-check suppression')


def stable_sampling(text):
    return prior.prior.v1.tools.once(text,'    cycles++;','    cycles <= cycles+1;')


def prepare(out):
    prior.BASE_BENCH=base_bench
    prior.prepare(out)
    local=out/'inputs'/HERE.relative_to(prior.prior.v1.ROOT)
    pins=json.loads((out/'source-pins.json').read_text())
    for name in NEW:
        source,target=HERE/name,local/name
        h=prior.prior.v1.tools.sha(source); shutil.copyfile(source,target)
        if prior.prior.v1.tools.sha(target)!=h: raise ValueError('Reset-owned snapshot race')
        pins[str(source)]=pins[str(target)]=h
    bench=out/'seeded_tb.sv'
    bench.write_text(stable_sampling(bench.read_text()))
    pins[str(bench)]=prior.prior.v1.tools.sha(bench)
    audit_generated(bench.read_text())
    prior.prior.v1.tools.command([sys.executable,'-B',local/'test_seeded_coop_reset_owned.py'],
        out,out/'reset-owned-host-tests.log',time.monotonic()+60,60)
    config=json.loads((out/'selection.json').read_text())
    config.update(reset_owned_entry=str(local/NEW[0]),reset_initializer_only=True,
        final_grant_counter_update='NBA; stable at the sampling edge',
        prior_compile_failure=str(prior.prior.v1.OUT/'stage2_seeded_coop_vcs_20261110_03'))
    prior.prior.v1.tools.save(out/'selection.json',config)
    for p in (out/'selection.json',out/'reset-owned-host-tests.log'): pins[str(p)]=prior.prior.v1.tools.sha(p)
    prior.prior.v1.tools.verify(pins); prior.prior.v1.tools.save(out/'source-pins.json',pins)
    prior.prior.v1.tools.save(out/'prepared.json',dict(state='PREPARED_NOT_EXECUTED',frozen_runner=config['reset_owned_entry'],
        source_pins_sha256=prior.prior.v1.tools.sha(out/'source-pins.json')))
    print('SEEDED_RESET_OWNED_PREPARED '+str(out),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--execute',action='store_true')
    a=p.parse_args(); out=a.output.resolve()
    if a.execute:
        if str(Path(__file__).resolve())!=json.loads((out/'selection.json').read_text())['reset_owned_entry']:
            raise ValueError('Use frozen reset-owned successor')
        raise SystemExit(prior.prior.execute(out))
    prepare(out)
