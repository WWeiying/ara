"""Save native directives before an unchanged fail-closed protected-state audit."""
from pathlib import Path
import fsm741_exact_capture_v2 as capture

if __name__ == '__main__':
    capture.HOOK = Path(__file__).with_suffix('.tcl').resolve()
    out = capture.life.OUT / 'fsm741-native-relation-diagnostic-20261007-01'
    sha = capture.life.digest(Path(__file__).resolve())
    try:
        capture.run(out, False)
    finally:
        if out.is_dir():
            capture.require(capture.life.digest(Path(__file__).resolve()) == sha, 'Diagnostic driver changed')
            capture.life.save(out / 'diagnostic-driver.json', dict(path=str(Path(__file__).resolve()), sha256=sha,
                             not_native_qualification=True, hypothesis='State display may inherit all incident transition exclusions; exact EL must be checked.'))
