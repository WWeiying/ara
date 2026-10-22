"""Cheap generated-Tcl syntax gate; not a GUI, scope, or coverage verifier."""
import argparse
import hashlib
import json
from pathlib import Path
import tkinter


def check(path):
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    if not text.strip() or '\x00' in text:
        raise ValueError('Empty or NUL-containing Tcl program')
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(value, str):
            raise ValueError('Generated Tcl is a serialized JSON string, not a script')
    interpreter = tkinter.Tcl()
    if int(interpreter.call('info', 'complete', text)) != 1:
        raise ValueError('Incomplete Tcl syntax')
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                status='TEXT_AND_SYNTAX_GATE_ONLY', executed=False,
                scope_verified=False, native_qualified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scripts', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps([check(path) for path in args.scripts]))
