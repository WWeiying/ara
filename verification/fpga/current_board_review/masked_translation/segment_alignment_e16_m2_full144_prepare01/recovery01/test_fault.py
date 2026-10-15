import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from checker02 import fault_boundary

h={'op_0':[0x900,0x904,0x90e,0x912,0x916]}
assert fault_boundary('op_0',h,2,0x90e,0x904) is False
assert fault_boundary('op_0',h,3,0x90e,0x90e) is True
negative=[(None,h,2,0x90e,0x904),('op_0',h,4,0x90e,0x912),
          ('op_0',h,3,0x90e,0x912),('op_0',h,1,0x90e,0x900),
          ('op_0',h,2,0x999,0x904)]
for args in negative:
    try:fault_boundary(*args)
    except ValueError:pass
    else:raise ValueError('Invalid target fault position admitted')
print(json.dumps(dict(status='HOST_FAULT_STATUS_PASS',positive=2,negative=len(negative))))
