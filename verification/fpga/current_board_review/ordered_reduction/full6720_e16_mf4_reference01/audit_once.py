import json
from pathlib import Path
import sys
import traceback
sys.dont_write_bytecode=True
from checker import audit
raw,out=map(Path,sys.argv[1:]);out.mkdir()
try:
    result=audit(raw)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],result['firmware_to_HTIF'])
except BaseException as e:
    (out/'FIRST_FAILURE.json').write_text(json.dumps(dict(error=repr(e),traceback=traceback.format_exc()),indent=2)+'\n')
    raise
