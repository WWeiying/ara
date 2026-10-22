"""Resume the reviewed native EL with selection sourced in session-global scope."""
import argparse
from pathlib import Path
import qualify_dwc_points742_v2 as predecessor

b = predecessor.base
SCRIPT = Path(__file__).resolve()
dependencies = {str(p): b.life.digest(p) for p in (
    predecessor.base.HERE / 'qualify_dwc_points742_v2.py',
    predecessor.base.HERE / 'qualify_dwc_points742_v2.tcl',
    predecessor.base.HERE / 'test_qualify_dwc_points742_v2.py',
    b.life.OUT / 'dwc31-fsm168-toggle-native742-agent-20261007-02/error.txt',
    b.life.OUT / 'dwc31-fsm168-toggle-native742-agent-20261007-02/terminal.json')}
original_merge = b.life.merge_pins


def merge(left, right):
    return original_merge(original_merge(left, right), dependencies)


b.life.merge_pins = merge
b.SCRIPT = SCRIPT
b.TCL = SCRIPT.with_suffix('.tcl')
b.TEST = SCRIPT.with_name('test_resume_dwc_native742.py')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run', 'inspect', 'el'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal'); p.add_argument('--file')
    a = p.parse_args(); out = a.output.absolute()
    if a.mode == 'prepare': predecessor.prepare(out)
    elif a.mode == 'el':
        b.require(a.file in ('first.el', 'second.el'), 'Unapproved EL')
        print(b.json.dumps(dict(semantic_records=len(predecessor.parse_el((out / a.file).read_text(),
                                b.json.loads((out / 'config.json').read_bytes()))))))
    else:
        b.require(a.seal, 'Exact seal required')
        if a.mode == 'run': b.run(out, a.seal)
        else: b.verify(out, a.seal, a.mode == 'check')
