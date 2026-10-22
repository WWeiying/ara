"""Evaluate actual generated selection Tcl without EDA or filesystem side effects."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


DRIVER = r'''
proc checked_source {slave path} {
    global allowed
    if {[lsearch -exact $allowed $path] < 0} {error "unsealed Tcl source: $path"}
    set f [open $path r]
    set text [read $f]
    close $f
    if {![info complete $text]} {error "incomplete Tcl source: $path"}
    interp eval $slave $text
}
if {[catch {
    set allowed [split $env(REPORT_TCL_ALLOWED) "\n"]
    interp create -safe generated
    interp alias generated source {} checked_source generated
    checked_source generated $env(REPORT_TCL_PATH)
    foreach name [split $env(REPORT_TCL_REQUIRED) "\n"] {
        if {$name ne "" && ![interp eval generated [list info exists $name]]} {
            error "missing generated global: $name"
        }
    }
} message]} {
    puts stderr $message
    exit 1
}
puts GENERATED_TCL_ACTUAL_EVAL_PASS
'''


def evaluate(path, pins, required_variables=()):
    path = Path(path).resolve()
    if str(path) not in pins or not pins:
        raise ValueError('Generated Tcl must be sealed before evaluation')
    for name in required_variables:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
            raise ValueError('Invalid required variable')
    for filename, sha in pins.items():
        p = Path(filename)
        if not p.is_absolute() or '\n' in filename or p.resolve() != p:
            raise ValueError('Noncanonical Tcl dependency path')
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError('Tcl bytes differ: ' + filename)
        try:
            decoded = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            decoded = None
        if isinstance(decoded, str):
            raise ValueError('JSON-serialized string is not Tcl source: ' + filename)
    env = dict(os.environ, REPORT_TCL_PATH=str(path), REPORT_TCL_ALLOWED='\n'.join(pins),
               REPORT_TCL_REQUIRED='\n'.join(required_variables))
    result = subprocess.run(['tclsh'], input=DRIVER, text=True, capture_output=True,
                            env=env, timeout=10)
    if result.returncode or result.stdout.strip() != 'GENERATED_TCL_ACTUAL_EVAL_PASS':
        raise ValueError('Actual generated Tcl evaluation failed: ' + result.stderr.strip())
    return dict(status='GENERATED_TCL_ACTUAL_EVAL_PASS_NO_EDA', pins=dict(pins),
                required_variables=list(required_variables), gui_semantics_verified=False)
