"""One bounded frozen-image run; strict architectural checks precede admission."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType
import prepare_half_fma_finite as reference
import run_gap110_simulation as lifecycle

life, require = reference.life, reference.require
PRE = life.OUT/'operand-mask-data-preflight-parent-20261007-01'
OUT = life.OUT/'operand-mask-data-old-image-parent-20261007-01'
ELF = PRE/'input.elf'
NAME = 'operand_mask_full_width_data'
BUDGET = 1800
shared = reference.reused.old.shared.shared


def command(output):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD='+str(ELF), '+TESTCASE='+NAME,
            '+COMMIT_TRACE='+str(output/'commit_trace.csv'),
            '+VECTOR_TRACE='+str(output/'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(output/'code.vdb'),
            '-cm_name', NAME, '+ARA_CONTRACT_TRACE_LIMIT=100000']


def prepare():
    require(not OUT.exists(), 'Fresh one-shot output required')
    pre = json.loads((PRE/'preflight.json').read_bytes())
    require(pre['status']=='SPIKE_INDEPENDENT_INTEGER_ORACLE_PASS_NOT_RTL' and
            pre['software_checks']==5256 and pre['target_instructions']==12, 'Independent preflight required')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv']==str(life.IMAGE) and len(plan['image'])==66, 'Frozen image binding')
    pins = life.merge_pins(pre['pins'], plan['image'])
    for p in (PRE/'preflight.json', Path(__file__).resolve(), Path(lifecycle.__file__).resolve(),
              Path(shared.__file__).resolve(), life.PLAN):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    counts = shared.reference_counts(shared.spike_trace.parse_spike_commits(PRE/'spike.trace'), pre['symbols'])
    record = dict(case=NAME, pins=pins, command=command(OUT), timeout_s=BUDGET,
                  preflight=pre, counts=counts, rtl_modified=False, automatic_retry=False,
                  coverage_admitted=False)
    path = OUT.with_name(OUT.name+'.prepared.json')
    life.save(path, record)
    print(json.dumps(dict(prepared=str(path), seal=life.digest(path))))


def run(seal):
    path = OUT.with_name(OUT.name+'.prepared.json')
    record = life.read_bound(path, seal)
    require(record['command']==command(OUT) and record['timeout_s']==BUDGET, 'Bounded prepared command differs')
    record['pins'] = life.merge_pins(record['pins'], {str(path):seal})
    ns = dict(vars(lifecycle), NAME=NAME, ELF=ELF, ELF_SEAL=life.digest(ELF),
              BUDGET=BUDGET, command=command)
    FunctionType(lifecycle.run.__code__, ns)(OUT, record)
    try:
        log = (OUT/'run.vcs.log').read_text()
        require(log.count('Core Test *** SUCCESS ***')==1 and not re.search(
            r'(?m)^UVM_(ERROR|FATAL)\b|\[ARA_CONTRACT_ERROR\]', log), 'Functional terminal/contract failure')
        scalar = shared.spike_trace.compare_commit_prefix(PRE/'spike.trace', OUT/'commit_trace.csv',
            0x80000000, terminal_tohost_address=record['preflight']['symbols']['tohost'],
            rvfi_store_data_layout='unshifted')
        shared.scalar_exact(scalar, record['counts'])
        vector = shared.compare_vector_commits(PRE/'spike.trace', OUT/'commit_trace.csv',
                                               OUT/'vector_trace.csv', 0x80000000)
        require(vector['status']=='PASS' and all(vector[k]==0 for k in
            ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')) and
            not vector['incomplete_requests'] and not vector['unretired_requests'], 'Strict vector comparison')
        life.save(OUT/'scalar-comparison.json', scalar)
        life.save(OUT/'vector-comparison.json', vector)
        life.save(OUT/'architecture-result.json', dict(status='STRICT_ARCHITECTURE_PASS_COVERAGE_GAIN_PENDING',
            coverage_admitted=False, software_checks=5256, independent_preflight_bytes=8256))
    except Exception as error:
        life.save(OUT/'qualification-hold.json', dict(status='HOLD_NOT_ADMITTED', reason=str(error),
                                                     coverage_admitted=False))
        raise


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare','run')); p.add_argument('--seal')
    a = p.parse_args()
    if a.mode=='prepare': prepare()
    else:
        require(a.seal, 'Prepared seal required'); run(a.seal)
