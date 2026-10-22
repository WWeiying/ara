"""Remove one byte-exact pinned UCLI source echo in memory, never a failure."""
import hashlib


def normalize(log, script):
    lines = script.splitlines()
    if (len(lines) < 5 or lines[-1] != 'quit' or not all(x.startswith('#') for x in lines[:2])
            or lines[2] != 'if {[catch {'
            or script.count('FAILED:') != 1
            or lines[-4:] != ['} error]} {', '    puts "FAILED: gap65 observer $error"', '}', 'quit']):
        raise ValueError('unsupported observer echo source')
    echo = '\n'.join(['ucli% ' + x for x in lines[:3]] + lines[3:-1]) + '\n'
    if log.count(echo) != 1 or log.count('ucli% if {[catch {') != 1:
        raise ValueError('missing, changed, or repeated pinned observer echo')
    start = log.index(echo)
    boundary = log.find('[DUT_BOUNDARY_CONTRACT]')
    if boundary < start + len(echo):
        raise ValueError('observer echo is not before execution boundary')
    return log[:start] + log[start + len(echo):], dict(
        schema='gap65-ucli-source-echo-v1', removed_bytes=len(echo.encode()),
        echo_sha256=hashlib.sha256(echo.encode()).hexdigest(), occurrences=1,
        source='pinned observer Tcl', normalization='in-memory only; original log preserved')
