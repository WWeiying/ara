import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from context import sha
from reference02 import durable,child_once,verify
pins={str(HERE/n):sha(HERE/n) for n in ('check.py','test_short.py','run_host.py','matched.log','preflight.json','result.json')}
durable(HERE/'host_preflight.json',pins)
child_once([sys.executable,'-B',str(HERE/'test_short.py')],HERE/'host.log',HERE/'host_execution.json',120)
verify(pins);durable(HERE/'host_postflight.json',pins)
