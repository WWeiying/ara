"""The only closed raw parse; executor owns audit600 and numeric receipt."""
import json
from pathlib import Path
import sys
import traceback
from checker import audit
from execute import save

raw,out=map(Path,sys.argv[1:]);out.mkdir()
try:
    result=audit(raw);save(out/'result.json',result)
    print(result['status'],result['firmware_to_HTIF'],flush=True)
except BaseException as error:
    save(out/'firstcause.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=repr(error),traceback=traceback.format_exc()))
    raise
