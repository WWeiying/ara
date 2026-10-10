"""Exact parent-reviewed 732 -> 733 candidate adapter; no automatic admission."""
import argparse
from pathlib import Path

import admit_store_fault_flush as frozen

life,require=frozen.life,frozen.require
CANDIDATE=frozen.OUT/'store-fault-flush-gain-732-parent-20261006-01'
CANDIDATE_SHA='4be1c9ae6db77bb743fb656063eb5e57c0523849c45cfaba4f05f385b0ccac6a'
PREDECESSOR_SHA='5926e96aeaf057ee9461d794395468446f377e0b6aaac7a985a18c0f457df51b'
EXPECTED_DELTA=dict(line=1,cond=1,branch=1,fsm=0)
ORIGINAL_EVALUATE=frozen.evaluate


def identity(directory,seal):
    require(directory==CANDIDATE and seal==CANDIDATE_SHA,'Only exact reviewed fault/recovery candidate allowed')
    require(life.digest(Path(frozen.__file__))==PREDECESSOR_SHA,'Frozen admission predecessor drift')


def exact_record(record):
    frozen.gate(record)
    require(record['output']==str(CANDIDATE) and record['baseline']==str(frozen.gain.BASE) and
            record['baseline_seal']==frozen.gain.BASE_SEAL and record['baseline_tests']==732 and
            record['proposed_population']==733 and record['raw_delta']==EXPECTED_DELTA,
            'Exact reviewed 732/733/three-point gain differs')


def evaluate(directory,seal):
    identity(directory,seal)
    record,products,text=ORIGINAL_EVALUATE(directory,seal)
    exact_record(record)
    hits=products['target-hits.json']
    require(len(hits)==2 and [h['point']['raw_index'] for h in hits]==[54,43] and
            all(h['before_hit'] is False and h['single_hit'] is True and h['fresh_target_gain'] is True for h in hits),
            'Exact primary54/conditional43 fresh evidence differs')
    dependencies=[Path(__file__).resolve(),Path(__file__).with_name('test_admit_store_fault_flush_733.py')]
    products['evidence-pins.json']=life.merge_pins(products['evidence-pins.json'],
        {str(p):life.digest(p) for p in dependencies})
    life.check(products['evidence-pins.json'])
    return record,products,text


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--candidate-seal',required=True)
    args,_=parser.parse_known_args(argv)
    identity(args.candidate.absolute(),args.candidate_seal)
    previous=frozen.evaluate
    try:
        frozen.evaluate=evaluate
        frozen.main(argv)
    finally:
        frozen.evaluate=previous


if __name__=='__main__':main()
