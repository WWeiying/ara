#!/usr/bin/env python3
"""One closed raw parse; caller owns timeout and durable wait receipt."""
import hashlib
import json
from pathlib import Path
import sys
import traceback
sys.dont_write_bytecode=True
from checker import audit
def main():
    raw,out=map(Path,sys.argv[1:]);out.mkdir(exist_ok=False)
    try:
        result=audit(raw)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(result['status'],result['firmware_to_HTIF'])
    except BaseException as e:
        (out/'failure.json').write_text(json.dumps(dict(status='NOT_ACCEPTED_NO_RETRY',error=repr(e),traceback=traceback.format_exc()),indent=2)+'\n')
        raise
if __name__=='__main__':main()
