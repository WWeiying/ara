"""Actual observer service exit only, never DUT acceptance."""
import json,os,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
with (HERE/'service_exit.json').open('x') as f:
    json.dump(dict(kind='ACTUAL_SYSTEMD_OBSERVER_EXIT_NOT_DUT_RESULT',
        **{k:os.environ.get(k) for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')},
        observed_at=time.time(),pid=os.getpid(),DUT_acceptance_claimed=False,
        observation_timeout_is_not_DUT_terminal=True),f,indent=2)
    f.flush();os.fsync(f.fileno())
