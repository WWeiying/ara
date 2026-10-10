"""Reuse a strict sealed R1 single bitmap against frozen722; no recollection or admission."""
import argparse
import json
from pathlib import Path

import collect_narrow_reject_r1_cached_strict as strict

life, require, bitmap = strict.life, strict.require, strict.bitmap
CANDIDATE = life.OUT/'narrow-reject-r1-cached-strict-candidate-719-20261006-01'
CANDIDATE_SEAL = '81df1b592740010754f8208ae96daf0500d89c750e8891386134279da3589301'
BASE = life.OUT/'gap104-offline-admitted-722-20261006-02'
BASE_SEAL = 'b9ad9d11e0eeb709ebcf3e4bd6d5ccbdd94d4a229e9c80b144ef10cf8213415a'


def combine(before,single):
    require(len(before['tests'])==len(set(before['tests']))==722 and single['tests']==[str(strict.RUN/'code.vdb')],
            'Exact722/one R1 candidate membership differs')
    proposed=bitmap.combine(before,single)
    require(proposed['tests'][:722]==before['tests'] and len(proposed['tests'])==len(set(proposed['tests']))==723,
            'Full prefix/unique candidate differs')
    return proposed,bitmap.delta(before,proposed)


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh reconciliation directory')
    status=life.read_bound(CANDIDATE/'status.json',CANDIDATE_SEAL)
    require(status['status']=='R1_CACHED_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED' and not status['coverage_admitted'],
            'Not complete strict R1 PASS candidate')
    life.check(status['pins'])
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL);life.check(base['output_pins'])
    before=json.loads((BASE/'combined-bits.json').read_text())
    require((BASE/'combined-inputs.txt').read_text().splitlines()==[str(strict.DESIGN),*before['tests']],'Full722 input order differs')
    single=json.loads((CANDIDATE/'single-raw-bits.json').read_text())
    proposed,delta=combine(before,single)
    baselinepins=json.loads((BASE/'evidence-pins.json').read_text())
    pre=life.read_bound(strict.runner.PRE/'preflight-manifest.json',strict.PRE_SEAL)
    elfpath=Path(pre['input_elf']);elfsha=status['pins'][str(elfpath)]
    require(not any(path.endswith('.elf') and sha==elfsha for path,sha in baselinepins.items()),'Duplicate722 ELF')
    pins=life.merge_pins(status['pins'],base['output_pins'])
    paths=[Path(__file__).resolve(),Path(__file__).with_name('test_reconcile_r1_cached_raw722.py')]
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in paths})
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL,str(CANDIDATE/'status.json'):CANDIDATE_SEAL})
    life.check(pins)
    hits=json.loads((CANDIDATE/'target-hits.json').read_text())
    rebased=[]
    for h in hits:
        row=before['metrics'][h['metric']][h['scope']];i=h['point']['raw_index'];bit=1<<(row['width']-1-i)
        was=bool(int(row['bits'],16)&bit)
        rebased.append(dict(**h,hit722=was,new_vs722=h['hit_single'] and not was))
    out.mkdir()
    life.save(out/'raw-union.proposed.json',proposed);life.save(out/'raw-bitmap-delta.json',delta)
    life.save(out/'target-reconciliation722.json',rebased);life.save(out/'evidence-pins.json',pins)
    outputs={str(path):life.digest(path) for path in out.iterdir() if path.is_file()}
    receipt=dict(status='R1_STRICT_PASS_RAW_RECONCILED722_NOT_ADMITTED',candidate=str(CANDIDATE),candidate_seal=CANDIDATE_SEAL,
                 baseline=str(BASE),baseline_seal=BASE_SEAL,baseline_tests=722,proposed_tests=723,admitted0=True,
                 exact722_prefix=True,unique_new_vdb=True,duplicate_elf=False,elf_sha256=elfsha,
                 targets_hit_single=sum(h['hit_single'] for h in hits),new_targets_vs722=sum(h['new_vs722'] for h in rebased),
                 unhit_targets=[dict(metric=h['metric'],point=h['point']) for h in hits if not h['hit_single']],
                 raw_delta=delta['metrics'],pins=life.merge_pins(pins,outputs),coverage_admitted=False,
                 simulations_started=False,collector_rerun=False,VDB_recollected=False,RTL_changed=False,
                 exclusions_generated=False,official_DVE_report=False,authorization_source='OFFLINE_RECONCILIATION_ONLY_NO_FORMAL_ADMISSION_AUTHORIZATION')
    life.save(out/'status.json',receipt)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'status.json'),raw_delta=delta['metrics'],new_targets_vs722=receipt['new_targets_vs722'],admitted=0)))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');a=p.parse_args()
    if a.mode=='prepare':require(not a.seal,'Fresh prepare only');prepare(a.output.absolute())
    else:
        require(a.seal,'Sealed reconciliation required');d=life.read_bound(a.output.absolute()/'status.json',a.seal);life.check(d['pins'])
        require(d['status']=='R1_STRICT_PASS_RAW_RECONCILED722_NOT_ADMITTED' and not d['coverage_admitted'],'Status drift')
        print('VERIFY_PASS R1_RECONCILIATION722 NOT_ADMITTED')


if __name__=='__main__':main()
