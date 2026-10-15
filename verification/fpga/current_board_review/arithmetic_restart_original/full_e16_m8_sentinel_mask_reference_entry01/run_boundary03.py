from context import *
from reference02 import child_once,durable
pins={str(HERE/n):sha(HERE/n) for n in ('reference02.py','reference_check02.py','test_boundary03.py','context.py','lifecycle.py','PROFILE02.json','run_boundary03.py')}
durable(HERE/'host03_preflight.json',pins)
child_once([sys.executable,'-B',str(HERE/'test_boundary03.py')],HERE/'host03.log',HERE/'host03_execution.json',120)
require(all(sha(p)==h for p,h in pins.items()),'Boundary pin drift')
durable(HERE/'host03_postflight.json',pins)
