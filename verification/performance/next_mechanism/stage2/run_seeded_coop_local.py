#!/usr/bin/env python3
"""Pre-execution successor adding suffix-local flags and truthful fault coverage."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True
import run_seeded_coop as v1
BASE_CHECK = v1.check_log

HERE = Path(__file__).resolve().parent
NEW = ('run_seeded_coop_local.py','seeded_coop_local_flags.c','test_seeded_coop_local.py')
LOCAL_TASK = '''
  task automatic load_local_flags;
    string path, token;
    int f, rc, model, n, flags;
    assert ($value$plusargs("SEEDED_LOCAL_FLAGS=%s",path));
    f=$fopen(path,"r"); assert(f!=0);
    rc=$fscanf(f,"%s",token); assert(rc==1 && token=="S2LOCAL1");
    for(int i=0;i<4;i++) begin
      rc=$fscanf(f,"%d %d %d",model,n,flags);
      assert(rc==3 && model==i && n==(i==3?5:16) && flags inside {[0:31]});
      gold_flags[i]=5'(flags);
    end
    rc=$fscanf(f,"%s",token); assert(rc==1 && token=="END"); $fclose(f);
  endtask
'''
MONITOR = '''
  int local_seed_checks=0, local_after_nx=0;
  bit local_previous_nx=0, local_fault_queued=0;
  always @(posedge clk) if(rst_n) begin
    if(success_valid || fault_valid) local_previous_nx=result_fflags[0];
    if(dut.i_engine.i_compute_engine.raw_seed_valid && dut.i_engine.i_compute_engine.raw_seed_ready) begin
      assert(dut.i_engine.i_compute_engine.i_fp_accumulator.fflags_o === 5'b0 && result_fflags === 5'b0)
        else $fatal(1,"SEEDED seed inherited prior FP flags");
      local_seed_checks++;
      if(local_previous_nx) local_after_nx++;
    end
    if(dut.i_engine.i_compute_engine.fault_i &&
       dut.i_engine.i_compute_engine.integer_queue_occupancy != 0) local_fault_queued=1;
  end
  final $display("SEEDED_LOCAL_DONE seed_checks=%0d after_nx=%0d fault_queued=%0d oracle_suffix=1 active_tail_n=5",
                 local_seed_checks,local_after_nx,local_fault_queued);
'''


def adapt(text):
    text=v1.tools.once(text,'  task automatic run_directed_seeded;',LOCAL_TASK+'\n  task automatic run_directed_seeded;')
    text=v1.tools.once(text,'    load_seed_vectors();','    load_seed_vectors();\n    load_local_flags();')
    return v1.tools.once(text,'  initial begin : run_tests\n',MONITOR+'\n  initial begin : run_tests\n')


def check_log(text):
    result=BASE_CHECK(text)
    rows=re.findall(r'^SEEDED_LOCAL_DONE seed_checks=(\d+) after_nx=(\d+) fault_queued=([01]) oracle_suffix=1 active_tail_n=5$',text,re.M)
    if len(rows)!=1 or int(rows[0][0])!=104 or int(rows[0][1])==0:
        raise ValueError('Missing seed flag-clear/suffix-local evidence')
    fault=[line for line in text.splitlines() if line.startswith('STAGE2_QUEUE_COMMAND seq=5 ')]
    if len(fault)!=1: raise ValueError('Missing actual fault FIFO ledger')
    match=re.search(r' fault_drain=(\d+) ',fault[0])
    if match is None or bool(int(match[1]))!=bool(int(rows[0][2])):
        raise ValueError('Fault-time FIFO observation disagrees with original probe')
    result.update(seed_flag_clear_checks=int(rows[0][0]),seed_checks_after_nx=int(rows[0][1]),
        suffix_local_flags_checked=True,inactive_tail_excluded_from_flags=True,
        fault_while_fifo_nonempty=bool(int(rows[0][2])),
        fault_scope='Actual queued fault drain' if int(rows[0][2]) else
                    'Read-fault recovery after prior FIFO work; queued-fault drain not exercised here')
    return result


def prepare(out):
    v1.prepare(out)
    local=out/'inputs'/HERE.relative_to(v1.ROOT)
    pins=json.loads((out/'source-pins.json').read_text())
    for name in NEW:
        source,target=HERE/name,local/name
        h=v1.tools.sha(source); shutil.copyfile(source,target)
        if v1.tools.sha(target)!=h: raise ValueError('Successor snapshot race')
        pins[str(source)]=pins[str(target)]=h
    deadline=time.monotonic()+180
    v1.tools.command(['cc','-O2','-std=c11','-ffp-contract=off','-frounding-math',
        '-I'+str(out/'inputs/verification/qbs'),local/'seeded_coop_local_flags.c',
        out/'inputs/verification/qbs/qbs_ref.c','-lm','-o',out/'local-oracle'],out,out/'local-oracle-build.log',deadline)
    v1.tools.command([out/'local-oracle',out/'vectors.txt',out/'local-flags.txt'],
        out,out/'local-oracle-run.log',deadline)
    (out/'seeded_tb.sv').write_text(adapt((out/'seeded_tb.sv').read_text()))
    v1.tools.command([sys.executable,'-B',local/'test_seeded_coop_local.py','--prepared',out],
        out,out/'local-host-tests.log',deadline,60)
    config=json.loads((out/'selection.json').read_text())
    config.update(frozen_successor=str(local/'run_seeded_coop_local.py'),suffix_local_flags=True,
                  inactive_tail_n=5,old_prepared01_preserved=True)
    v1.tools.save(out/'selection.json',config)
    for p in (out/'seeded_tb.sv',out/'selection.json',out/'local-oracle',out/'local-flags.txt',
              out/'local-oracle-build.log',out/'local-oracle-run.log',out/'local-host-tests.log'):
        pins[str(p)]=v1.tools.sha(p)
    v1.tools.verify(pins); v1.tools.save(out/'source-pins.json',pins)
    v1.tools.save(out/'prepared.json',dict(state='PREPARED_NOT_EXECUTED',frozen_runner=config['frozen_successor'],
        source_pins_sha256=v1.tools.sha(out/'source-pins.json')))
    print('SEEDED_LOCAL_PREPARED '+str(out),flush=True)


def execute(out):
    if Path(__file__).resolve()!=Path(json.loads((out/'selection.json').read_text())['frozen_successor']):
        raise ValueError('Use frozen successor')
    original_command=v1.tools.command
    def command(argv,*args,**kwargs):
        if str(argv[0]).endswith('/simv'):
            argv=[*argv,'+SEEDED_LOCAL_FLAGS='+str(out/'local-flags.txt')]
        return original_command(argv,*args,**kwargs)
    v1.tools.command=command
    v1.check_log=check_log
    # Reuse the sealed lifecycle, bounds, build and image/source identity checks.
    return v1.execute(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if a.execute: raise SystemExit(execute(a.output.resolve()))
    prepare(a.output.resolve())
