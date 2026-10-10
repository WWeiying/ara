"""Minimal sealed-runner successor: fixed formal770 seal, unchanged600s worker."""
import argparse
import json
from pathlib import Path
import run_sv39_rvv_alias770 as prior

life,require,OUT=prior.life,prior.require,prior.OUT
BASE_SEAL='7f8cbc5061a61c776d008590617c8727a07ead3c87dfb762139626166d2ba80a'


def prepare(out):
    life.read_bound(prior.BASE/'admission-manifest.json',BASE_SEAL)
    out,record=prior.prepare(out)
    require(record['baseline_manifest_sha256']==BASE_SEAL,'Exact parent-reviewed formal770 seal')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_run_sv39_rvv_alias770_bounded.py')):
        record['pins']=life.merge_pins(record['pins'],{str(p):life.digest(p)})
    record.update(formal770_fixed_seal=BASE_SEAL,old_prepared_run_not_authorized=True,
        wave_limit_policy='Post-terminal qualification HOLD if VPD absent/empty/above64MiB; no runtime file-size monitor. Unchanged600s wall budget and11-object read-only profile.')
    life.read_bound(prior.BASE/'admission-manifest.json',BASE_SEAL);life.check(record['pins'])
    return out,record


def run(out,record):
    require(record['formal770_fixed_seal']==BASE_SEAL,'Exact parent-reviewed formal770 required')
    prior.run(out,record)


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();require((a.mode!='prepare')==bool(a.prepared_seal),'Fixed prepared seal required')
    require((a.mode=='run')==a.parent_authorized,'Separate parent authorization required')
    out,record=prepare(a.output);path=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        life.save(path,record);print(json.dumps(dict(prepared=str(path),seal=life.digest(path),pins=len(record['pins']))))
    else:
        require(life.read_bound(path,a.prepared_seal)==record,'Prepared command/pins drift')
        if a.mode=='verify':print('VERIFY_PASS fixed770/600s/noFSDB/S-ECALL48 NO_VCS')
        else:run(out,dict(record,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


if __name__=='__main__':main()
