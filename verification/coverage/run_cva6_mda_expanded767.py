"""Thin display-expansion successor, retaining the immutable singleton lifecycle."""
import argparse
import json
from pathlib import Path
import run_cva6_mda_readonly767 as base

ORIGIN = base.OUT / 'cva6-mda-readonly-singleton767-agent-20261007-01'
SEAL = '7e02a198abae1d64fb51556ad9ede4dbd7602bc431d48d900bd51514edb638ec'
HERE = Path(__file__).resolve().parent


def prepare(out):
    base.t.require(not out.exists() and out.parent == base.OUT, 'Fresh successor output')
    base.t.require(base.t.digest(ORIGIN / 'config.json') == SEAL, 'Original singleton binding drift')
    c = json.loads((ORIGIN / 'config.json').read_bytes()); base.check(c['pins'])
    body = Path(c['entry']).read_text()
    base.t.require(body.count('puts MDA_READONLY_DONE') == 1, 'Exact immutable native entry')
    body = body.replace(str(ORIGIN), str(out))
    extension = HERE / 'probe_cva6_mda_expanded767.tcl'
    addition = 'source {' + str(extension) + '}\n'
    for index, scope, name in ((0, base.source.SCOPES[0], 'fwd_res[7:0][63:0]'),
                               (2, base.source.SCOPES[2], 'mem[31:0][63:0]')):
        addition += 'mda_expand_one {' + scope + '} {' + name + '} {' + str(out / ('expanded_%d.tclrows' % index)) + '}\n'
    body = body.replace('puts MDA_READONLY_DONE', addition + 'puts MDA_READONLY_DONE')
    vendor = Path(c['identity']['executable']).parents[2] / 'auxx/gui/dve/preferencesCovMainMenu.tcl'
    text = vendor.read_text()
    base.t.require('gui_cov_tgl_compress -id $window -opt $opt' in text, 'Installed native uncompress API changed')
    c['pins'] = dict(c['pins'])
    for p in (Path(__file__), extension, vendor, ORIGIN / 'config.json'):
        c['pins'][str(p)] = base.t.digest(p)
    base.check(c['pins']); out.mkdir()
    entry = out / 'entry.tcl'
    with entry.open('x') as stream: stream.write(body)
    c.update(output=str(out), entry=str(entry), readonly_expansion=True,
             predecessor_config_seal=SEAL, expanded_arrays=['mem[31:0][63:0]', 'fwd_res[7:0][63:0]'])
    c['pins'][str(entry)] = base.t.digest(entry)
    base.save(out / 'config.json', c)
    print('EXPANDED_PREPARED', base.t.digest(out / 'config.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    args = parser.parse_args(); out = args.output.resolve()
    if args.mode == 'prepare': prepare(out)
    else:
        base.t.require(args.seal is not None, 'Explicit successor seal'); base.run(out, args.seal)
