"""Post-service metadata collection; no second source/generic CSV traversal."""
import argparse
import time
from scope import *
import replay as r

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();require(out.parent==HERE,'Owned terminal collection')
    answer=dict(status='NOT_ACCEPTED',DUT_rerun=False,semantic_CSV_parses=0)
    try:
        hook=read(out/'service_exit.json')
        require(hook['kind']=='ACTUAL_SYSTEMD_EXEC_STOP_POST' and hook['SERVICE_RESULT']=='success' and
                hook['EXIT_CODE']=='exited' and hook['EXIT_STATUS']=='0','Actual main-service success0, not GC defaults')
        complete=read(out/'complete.json');digest=complete['plan_sha256'];r.disk_gate(out,digest)
        require(complete['status']==PASS and complete['pins_unchanged'] is True and complete['aborted'] is False and
                complete['retries']==0 and complete['full_parent'] is True and complete['linux'] is False,'Full producer acceptance')
        root=out/'replay/tests'/NAME;numeric=read(root/'child_outcome.unvalidated.json')
        require(type(numeric['returncode'])is int and numeric['returncode']==0 and numeric['timed_out'] is False and
                numeric['failure_seen'] is False and 0<numeric['elapsed_s']<=TIMEOUT,'Actual persisted child0')
        require(len(complete['results'])==1 and complete['results'][0]['name']==NAME and
                complete['results'][0]['status']=='PASS' and type(complete['results'][0]['returncode'])is int and
                complete['results'][0]['returncode']==0,'Exact one runtime result')
        report=read(root/'strict_original.json');s=report['strict'];generic=report['generic']
        require([s[k] for k in ('calls','result_bits','guards','flags','vstarts','helper_instructions','capacity_instructions',
                 'fresh_stores','input_LD','output_LWU','record_LD','FPR_committed_writebacks')]==
                [17920,286720,35840,17920,17920,326144,3,734720,143360,17920,2240,10752], 'Full exact scalar/source scope')
        require(s['raw_scalar_seed_counts']=={str(i):336 for i in range(32)},'All original raw FT0 seeds')
        require(report['closed_semantic_passes']==1 and report['owners']['contract']==r.owner_contract() and
                report['owners']['status']=='EVERY_NECESSARY_OWNER_COMPLETED','Source-derived full owner gate')
        require(s['rows']==generic['rows'] and s['retired']==generic['retire_count'] and
                generic['backend_uop_alloc_count']==generic['backend_uop_done_count']>0 and generic['cvx_exception_count']==0,
                'All actual protocol paired')
        pins=complete['evidence_pins'];csvpath=root/'commit_trace.csv'
        require(pins[str(csvpath)]==report['csv_sha256'] and csvpath.stat().st_size>0,'Producer closed CSV binding')
        # Preserve the producer's closed CSV digest; do not repeat its large read.
        for path,h in pins.items():
            if path!=str(csvpath): require(sha(path)==h,'Terminal small artifact drift '+path)
        r.checker.console_gate((root/'console.log').read_text())
        r.checker.console_gate((root/'work/run.vcs.log').read_text())
        run=read(out/'replay/run.json')
        require(run['status']=='COMPLETE' and run['status_counts']=={'PASS':1} and run['tests']==[NAME], 'Actual runner COMPLETE')
        answer.update(status='PASS_FULL17920_M9_METADATA_COLLECTED_NOT_LINUX',plan_sha256=digest,
            scope={k:s[k] for k in ('calls','result_bits','guards','flags','vstarts','FPR_committed_writebacks','rows')},
            actual_simulator_wait=numeric,service_exit=hook,owner_contract=report['owners']['contract'],
            csv_identity_inherited_from_complete=report['csv_sha256'],independent_numerical_reaudit=False,
            pins_unchanged=True,evidence_pins={str(p):sha(p) for p in [out/'complete.json',out/'service_exit.json',
                out/'plan.json',root/'strict_original.json',root/'child_outcome.unvalidated.json']})
    except BaseException as e: answer['error']=repr(e)
    answer['finished']=time.time();r.durable(out/'collector_result.json',answer)
    return int(answer['status']!='PASS_FULL17920_M9_METADATA_COLLECTED_NOT_LINUX')
if __name__=='__main__':raise SystemExit(main())
