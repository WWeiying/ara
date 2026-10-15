"""Scoped successor: accepted cancellation, fixed max8 scheduling, pilot first."""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from support import ANCESTOR,load
accepted=load(ANCESTOR/'scheduler.py','nf8_accepted_cancel')
Abort=accepted.Abort

def run_groups(groups,jobs,run_one,abort):
    if not 1<=jobs<=8: raise ValueError('Own jobs must be1..8')
    pending=list(groups); results={}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        running={}
        def dispatch():
            with abort.lock:
                while pending and len(running)<jobs and abort.reason is None:
                    group=pending.pop(0)
                    running[pool.submit(run_one,group,abort)]=group
        dispatch()
        while running:
            completed,_=wait(running,return_when=FIRST_COMPLETED)
            for future in completed:
                group=running.pop(future)
                try: result=future.result()
                except Exception as error: result=dict(status='FAIL',error=str(error))
                results[group]=result
                if result.get('status')!='PASS': abort.stop(dict(group=group,result=result))
            dispatch()
    for group in pending: results[group]=dict(status='CANCELLED_NOT_LAUNCHED')
    return results

def pilot_then_remaining(run_one,abort,on_pilot):
    pilot=run_groups([0],1,run_one,abort)
    if pilot[0]['status']!='PASS':
        return {**pilot,**{g:dict(status='CANCELLED_NOT_LAUNCHED') for g in range(1,48)}}
    try: on_pilot(pilot[0])
    except Exception as error:
        abort.stop(dict(pilot_admission_error=str(error)))
        return {**pilot,**{g:dict(status='CANCELLED_NOT_LAUNCHED') for g in range(1,48)}}
    return {**pilot,**run_groups(list(range(1,48)),8,run_one,abort)}
