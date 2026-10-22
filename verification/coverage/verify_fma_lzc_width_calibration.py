"""Read-only replay of sealed real original-module LZC calibration, not native eligibility."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'verification/out/fma-lzc-width-array768-prepared-agent-20261007-01'
PLAN_SHA='a13048c0624c8c86054262a20c683d71be3a1c68fce98dbe2b17d6abd950e8d6'
RESULT_SHA='b3a05e477a10d4e6ef6098887a7282308971c90b446c056dc010f1025a27f362'
SOURCE_SHA='f31989be4369ea7c4809c0c3d61df28581e9ac7666005fde6e476a975d1acd07'
BENCH_SHA='6719871fb680dfd0e9c5a690e817d066f2148723853d1aca87260f62be872513'
CHECKS={25:330,51:1331,109:6000}


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(path,seal):
    require(digest(path)==seal,'Sealed file differs: '+str(path))
    return json.loads(Path(path).read_bytes())


def source_gate(source,bench):
    require(hashlib.sha256(source).hexdigest()==SOURCE_SHA,'Original frozen LZC source drift')
    require(hashlib.sha256(bench).hexdigest()==BENCH_SHA,'Original independent checker drift')


def log_gate(text):
    rows=re.findall(r'^LZC_WIDTH_PASS WIDTH=(\d+) MODE=1 CHECKS=(\d+)$',text,re.M)
    require(len(rows)==3 and {int(w):int(n) for w,n in rows}==CHECKS,'Exact three WIDTH checks')
    require(text.splitlines().count('FMA_LZC_THREE_WIDTHS_PASS')==1,'Single completed calibration')
    require(not re.search(r'(?i)(?:fatal|mismatch|incomplete pattern|bounded standalone calibration timeout)',text),
            'Calibration failure diagnostic')
    zero=re.findall(r'^LZC_ZERO WIDTH=(\d+) EMPTY=1 COUNT=\d+ COUNT_NOT_ASSERTED$',text,re.M)
    require(len(zero)==3 and set(map(int,zero))==set(CHECKS),'Zero empty observations; no zero count contract')


def verify():
    plan=bound(OUT/'plan.json',PLAN_SHA);result=bound(OUT/'calibration-result.json',RESULT_SHA)
    for pins in (plan['pins'],result['pins']):
        require(pins,'Nonempty source/actual evidence pins')
        for path,seal in pins.items():require(digest(path)==seal,'Pinned bytes drift: '+path)
    source_gate((ROOT/'hardware/deps/common_cells/src/lzc.sv').read_bytes(),
                (ROOT/'verification/tests/fma_lzc_width_calibration.sv').read_bytes())
    require(plan['calibration_command']==result['calibration_command'] and
            plan['simulation_command']==result['simulation_command'],'Exact actual command binding')
    require(result['compile_returncode']==result['simulation_returncode']==0 and
            result['total_checks']==7661 and result['checks']=={str(k):v for k,v in CHECKS.items()},'Actual calibration completion')
    log_gate((OUT/'simulation.stdout').read_text())
    require(result['product_VDB_modified'] is False and result['official_denominator'] is None and
            result['native_launch_authorized'] is False,'Standalone only; no coverage/eligibility promotion')
    return dict(status='READONLY_ACTUAL_LZC_CALIBRATION_REPLAY_PASS',result_seal=RESULT_SHA,
                total_checks=7661,native_qualified=False,EDA_launched=False,files_written=False)


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(verify()))
