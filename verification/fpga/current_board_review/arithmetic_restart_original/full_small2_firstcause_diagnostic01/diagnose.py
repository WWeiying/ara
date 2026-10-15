#!/usr/bin/env python3
"""One read-only e8 prefix traversal, stop on the first unchanged Strict error."""
import csv
from collections import deque
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
WORK=HERE.parent/'full_small2_vcs_m6_plan01'
RUN=WORK/'prepared01'
CASE=RUN/'replay/tests/arithmetic_full_e8_mf8'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,value):
    with (HERE/name).open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def identity(p):
    s=p.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def need(ok,why):
    if not ok: raise ValueError(why)

def main():
    started=time.monotonic()
    save('started.json',dict(pid=os.getpid(),limit_seconds=120,max_rows=250000,no_retry=True))
    def timeout(*_): raise TimeoutError('Bounded first-failure diagnostic120s')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    pins={str(p):sha(p) for p in (WORK/'checker.py',RUN/'plan.json',RUN/'complete.json',
          RUN/'replay/summary.json',CASE/'child_outcome.unvalidated.json',CASE/'input.elf',Path(__file__))}
    need(pins[str(WORK/'checker.py')]=='18c9b86ab1a13b05d0f69823299d761a1f54a8d7c20c8b1ca30afd867ec8bf0f','Frozen checker')
    need(pins[str(RUN/'plan.json')]=='7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee','Frozen plan')
    terminal=read(RUN/'complete.json')
    need(terminal['status']=='NOT_PASS' and terminal['aborted'] is True,'Actual failed terminal')
    save('input_pins.json',pins)
    sys.path.insert(0,str(WORK))
    spec=importlib.util.spec_from_file_location('unchanged_small2_checker',WORK/'checker.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    shape='rvv_matrix_e8_mf8'
    state=checker.Strict(read(RUN/'plan.json')['specs'][shape],read(checker.REF/shape/'model.json'))
    path=CASE/'commit_trace.csv';before=identity(path)
    digest=hashlib.sha256();byte_count=0;history=deque(maxlen=16);writers={}
    with path.open('rb') as stream:
        def lines():
            nonlocal byte_count
            for line in stream:
                digest.update(line);byte_count+=len(line)
                yield line.decode('ascii')
        reader=csv.DictReader(lines())
        for index,row in enumerate(reader,1):
            need(index<=250000,'Prefix limit reached; no full parse authorized')
            previous=dict(state.regs)
            try:
                state.consume(row)
            except Exception as error:
                insn=int(row['insn'],16);desc=checker.memory_op(insn)
                detail=dict(status='FIRST_UNCHANGED_CHECKER_FAILURE_CAPTURED_NOT_DUT_ACCEPTANCE',
                    error=repr(error),csv_row=index,csv_physical_line=reader.line_num,row=row,
                    decoded=desc,known_integer_registers={str(k):hex(v) for k,v in previous.items()},
                    previous_retirements=list(history),completed_helper_calls=len(state.calls),
                    bss_next=hex(state.bss_next),main_entered=state.main_entered)
                if desc:
                    addr=int(row['mem_addr'],16);rmask=int(row['mem_rmask'],16);wmask=int(row['mem_wmask'],16)
                    wdata=int(row['mem_wdata'],16);size=desc['size'];mask=(1<<(8*size))-1
                    rs2=previous.get(desc['register']);base=previous.get(desc['base'])
                    enable=((1<<size)-1)<<(addr%8)
                    detail.update(expected_enable=hex(enable),actual_rmask=hex(rmask),actual_wmask=hex(wmask),
                        actual_wdata=hex(wdata),known_rs2=None if rs2 is None else hex(rs2),
                        known_base=None if base is None else hex(base),
                        expected_address=None if base is None else hex((base+desc['offset'])&checker.MASK64),
                        expected_store_low=None if rs2 is None else hex(rs2&mask),actual_store_low=hex(wdata&mask),
                        rs2_last_write=writers.get(desc['register']),base_last_write=writers.get(desc['base']),
                        failed_store_conditions=dict(wmask_matches=wmask==enable,rmask_zero=rmask==0,
                            source_register_known=rs2 is not None,value_matches=None if rs2 is None else (wdata&mask)==(rs2&mask)))
                need(identity(path)==before,'CSV changed during bounded diagnostic')
                detail.update(csv_identity=before,bytes_consumed=byte_count,prefix_sha256=digest.hexdigest(),
                              full_csv_parsed=False,stopped_immediately_at_first_error=True,elapsed_s=time.monotonic()-started)
                save('first_failure.json',detail)
                for p,h in pins.items(): need(sha(Path(p))==h,'Input drift '+p)
                print(json.dumps({k:detail[k] for k in ('error','csv_row','row','decoded','failed_store_conditions')}),flush=True)
                return 0
            if row['event']=='retire':
                history.append(dict(csv_row=index,**row))
                for reg,val in state.regs.items():
                    if previous.get(reg)!=val:
                        writers[reg]=dict(csv_row=index,**row)
    raise ValueError('EOF without expected error; not an acceptance audit')

if __name__=='__main__':
    start=time.monotonic()
    try:
        rc=main()
    except BaseException as error:
        save('diagnostic_error.json',dict(error=repr(error),no_retry=True));rc=1
    finally:
        signal.alarm(0)
    save('exit.json',dict(returncode=rc,elapsed_s=time.monotonic()-start,attempt=1))
    sys.exit(rc)
