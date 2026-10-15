"""Metadata-only post-service collection; no repeated semantic CSV parse."""
import argparse
import time
from scope import *
import replay as r
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve();require(out.parent==HERE,'Owned collector')
    result=dict(status='NOT_ACCEPTED',DUT_rerun=False,semantic_CSV_parses=0)
    try:
        hook=read(out/'service_exit.json');require(hook['kind']=='ACTUAL_SYSTEMD_EXEC_STOP_POST' and hook['SERVICE_RESULT']=='success' and hook['EXIT_CODE']=='exited' and hook['EXIT_STATUS']=='0','Actual service success0')
        done=read(out/'complete.json');r.disk_gate(out,done['plan_sha256'])
        require(done['status']==PASS and done['aborted'] is False and done['pins_unchanged'] is True and done['retries']==0,'Producer full acceptance')
        require(len(done['results'])==1 and done['results'][0]['name']==NAME and done['results'][0]['status']=='PASS' and type(done['results'][0]['returncode']) is int and done['results'][0]['returncode']==0,'Exact one runtime result')
        root=out/'replay/tests'/NAME;n=read(root/'child_outcome.unvalidated.json')
        require(type(n['returncode']) is int and n['returncode']==0 and n['timed_out'] is False and n['failure_seen'] is False and 0<n['elapsed_s']<=TIMEOUT,'Persisted numeric child0')
        report=read(root/'strict_original.json');s=report['strict'];g=report['generic']
        require([s[k] for k in ('calls','output_bytes','flags','vstarts','helper_instructions','capacity_instructions')]==[6720,967680,6720,6720,141120,3],'Full original scope')
        require(s['events']==dict(input_SH=128,seed_SD=128,fixture_fields=6720,mask_SD=26880,output_SD=120960,output_LD=120960),'Exact original events')
        require(s['rows']==g['rows'] and s['retired']==g['retire_count'] and g['backend_uop_alloc_count']==g['backend_uop_done_count']>0 and g['cvx_exception_count']==0,'Complete actual protocol')
        require(report['closed_semantic_passes']==1 and report['owners']['status']=='EVERY_NECESSARY_OWNER_COMPLETED' and report['owners']['contract']==r.owner_contract(),'Every source necessary owner')
        csv=root/'commit_trace.csv';require(done['evidence_pins'][str(csv)]==report['csv_sha256'] and csv.stat().st_size>0,'Closed CSV identity')
        for path,h in done['evidence_pins'].items():
            if path!=str(csv):require(sha(path)==h,'Small terminal artifact drift')
        r.checker.console_gate((root/'console.log').read_text());r.checker.console_gate((root/'work/run.vcs.log').read_text())
        run=read(out/'replay/run.json');require(run['status']=='COMPLETE' and run['status_counts']=={'PASS':1} and run['tests']==[NAME],'Runner COMPLETE')
        result.update(status='PASS_FULL6720_M9_METADATA_COLLECTED_NOT_LINUX',scope={k:s[k] for k in ('calls','output_bytes','flags','vstarts','rows')},actual_simulator_wait=n,service_exit=hook,
                      owner_contract=report['owners']['contract'],csv_identity_inherited_from_complete=report['csv_sha256'],pins_unchanged=True,
                      evidence_pins={str(p):sha(p) for p in [out/'plan.json',out/'complete.json',out/'service_exit.json',root/'strict_original.json',root/'child_outcome.unvalidated.json']})
    except BaseException as e:result['error']=repr(e)
    result['finished']=time.time();r.durable(out/'collector_result.json',result)
    return int(result['status']!='PASS_FULL6720_M9_METADATA_COLLECTED_NOT_LINUX')
if __name__=='__main__':raise SystemExit(main())
