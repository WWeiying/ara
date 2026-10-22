"""Reuse mature numeric-first transport; single2M reference, single closed audit."""
import argparse
import json
from pathlib import Path
import resource
import sys
sys.dont_write_bytecode=True
from checker import HERE,G,load,require
transport=load('sealed_reference_transport',G/'fp_compare_unboxed_full17920_prepare01/reference_entry02/execute_once.py')
sha,save,wait_child=transport.sha,transport.save,transport.wait_child
def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',type=Path,required=True);ap.add_argument('--review-sha256',required=True);args=ap.parse_args()
    require(sha(args.review)==args.review_sha256,'Actual reviewer hash')
    review=json.loads(args.review.read_text());entry=json.loads((HERE/'ENTRY.json').read_text())
    require(review['status']=='NO_BLOCKER_REFERENCE_ENTRY' and review['entry_sha256']==sha(HERE/'ENTRY.json') and review['input_pins_sha256']==sha(HERE/'input_pins.json'),'Exact independent core review')
    pins=json.loads((HERE/'input_pins.json').read_text());pins.update({str(p):sha(p) for p in (args.review,HERE/'ENTRY.json',HERE/'input_pins.json')})
    require(all(sha(Path(p))==h for p,h in pins.items()),'Preflight input drift')
    require(entry['debug_command']=='rs 2000000\nquit\n' and entry['reference_seconds']==120 and entry['audit_seconds']==600 and entry['raw_limit_bytes']==512*1024*1024,'Approved fixed bounds')
    host=json.loads((HERE/'host01.wait.json').read_text());require(type(host['actual_wait_exit']) is int and host['actual_wait_exit']==0 and host['timed_out'] is False and sha(HERE/'host01.log')==host['log_sha256'],'Actual short Host pass')
    out=HERE/'reference01';out.mkdir();save(out/'inputs_before.json',pins)
    debug=out/'spike.cmd';debug.write_text(entry['debug_command'])
    argv=[entry['spike'],'-d','--debug-cmd='+str(debug),'--isa='+entry['isa'],'-m2','--log-commits','--log='+str(out/'commits.log'),entry['elf']]
    try:
        actual=wait_child(argv,out/'spike',120,limits)
        require(actual['actual_wait_exit']==0 and not actual['timed_out'],'Actual reference exit')
        raw=out/'commits.log';require(raw.is_file() and 0<raw.stat().st_size<=512*1024*1024,'Raw bound')
        rawpin=dict(path=str(raw),bytes=raw.stat().st_size,sha256=sha(raw));save(out/'raw_before.json',rawpin)
        require(all(sha(Path(p))==h for p,h in pins.items()),'Postreference input drift')
        checked=wait_child([sys.executable,'-B',str(HERE/'audit_once.py'),str(raw),str(out/'audit01')],out/'audit',600)
        require(checked['actual_wait_exit']==0 and not checked['timed_out'],'Actual closed audit exit')
        result=json.loads((out/'audit01/result.json').read_text());require(result['status']=='REFERENCE_FULL6720_PASS_SOURCE_ONLY_NOT_DUT','Complete original scope')
        require(sha(raw)==rawpin['sha256'] and all(sha(Path(p))==h for p,h in pins.items()),'Final raw/input drift')
        save(out/'inputs_after.json',pins)
        save(out/'COMPLETE.json',dict(status='REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_TERMINAL_REVIEW',result=result,actual_reference=actual,actual_audit=checked,raw=rawpin,
             result_sha256=sha(out/'audit01/result.json'),entry_sha256=sha(HERE/'ENTRY.json'),review_sha256=args.review_sha256,input_pins_unchanged=True,reference_attempts=1,closed_semantic_parses=1,DUT=False))
        print(result['status'],result['firmware_to_HTIF'])
    except BaseException as e:
        save(out/'NOT_ACCEPTED.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=repr(e)));raise
if __name__=='__main__':main()
