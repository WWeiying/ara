"""Pin-only prepared02 successor; original worker/Host/prepared01 untouched."""
from scope import *
import replay_successor02 as replay
from prepare_only import command

original=replay.owned_pins
required=[SHARED/'collect_successor.py',SHARED/'exit_hook_successor.py']


def closure():
    pins=original()
    pins.update({str(p):sha(p) for p in required})
    pins[str(Path(__file__))]=sha(Path(__file__))
    return pins


if __name__=='__main__':
    require(not (HERE/'prepared02').exists(),'Fresh pin-only successor, no retry')
    old=read(HERE/'prepared01/plan.json')
    require(not (HERE/'prepared01/replay').exists(),'Old plan not launched')
    require(all(str(p) not in old['pins'] for p in required),'Exact missing pin cause')
    replay.durable(HERE/'PIN_CLOSURE02.json',dict(status='PREPARED01_HOLD_SOURCE_PIN_OMISSION_NOT_DUT_FAILURE',
        old_plan_sha256=sha(HERE/'prepared01/plan.json'),missing_paths=list(map(str,required)),
        successor='prepared02',worker_code_unchanged=True,Host_repeated=False))
    # Private preparation process only; run-time already hashes every disk-plan pin.
    replay.owned_pins=closure
    out=HERE/'prepared02';replay.prepare(out)
    plan=read(out/'plan.json')
    require(all(plan['pins'].get(str(p))==sha(p) for p in required),'All shared closure present')
    require(plan['cases']==old['cases'] and plan['spec']==old['spec'] and plan['owner_contract']==old['owner_contract'],
        'Pin-only successor preserves source/strict/owner scope')
    command([sys.executable,'-B',str(HERE/'replay_successor02.py'),'dryrun','--out',str(out),
        '--plan-sha256',sha(out/'plan.json')],HERE/'dryrun02',180)
    print('PIN_CLOSURE_READY_PARENT_LAUNCH_ONLY',sha(out/'plan.json'),flush=True)
