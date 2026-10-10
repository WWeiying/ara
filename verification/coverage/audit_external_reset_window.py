"""Independent focused-VCD reset-window check, not architecture/PASS admission."""
import argparse
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(path, selection):
    names = {'clk': 'ara_tb.clk', 'reset': 'ara_tb.rst_n',
             'stage': selection['ext_target']}
    if selection['ext_guard']:
        names['guard'] = selection['ext_guard']
    wanted = set(names.values())
    scopes, ids, widths, state, changes = [], {}, {}, {}, {}
    time, last, body = 0, -1, False
    falls, transitions = [], []

    def value(values, name):
        bits = values.get(ids[names[name]])
        return int(bits, 2) if bits and set(bits) <= {'0', '1'} else None

    def consume():
        before = dict(state)
        state.update(changes)
        changes.clear()
        if value(before, 'clk') == 1 and value(state, 'clk') == 0:
            falls.append(time)
        old, new = value(before, 'reset'), value(state, 'reset')
        if old != new:
            transitions.append(dict(time=time, old=old, new=new,
                                    stage=value(before, 'stage'),
                                    guard=value(before, 'guard') if 'guard' in names else 1))

    with Path(path).open() as stream:
        for raw in stream:
            line = raw.strip()
            if not body:
                if line.startswith('$scope '):
                    scopes.append(line.split()[2])
                elif line.startswith('$upscope'):
                    require(bool(scopes), 'VCD scope underflow')
                    scopes.pop()
                elif line.startswith('$var '):
                    fields = line.split()
                    name = '.'.join(scopes + [fields[4].lstrip('\\')])
                    if name in wanted:
                        require(name not in ids, 'Duplicate selected declaration')
                        ids[name] = fields[3]
                        widths[fields[3]] = int(fields[2])
                elif line.startswith('$enddefinitions'):
                    require(set(ids) == wanted, 'Missing selected HDL declarations')
                    require(widths[ids[names['clk']]] == widths[ids[names['reset']]] == 1,
                            'Clock/reset width differs')
                    if 'guard' in names:
                        require(widths[ids[names['guard']]] == 1, 'Guard must be a bit')
                    body = True
                continue
            if line.startswith('#'):
                new = int(line[1:])
                require(new > last, 'Nonmonotonic timestamp')
                consume()
                time = last = new
            elif line and line[0].lower() in '01xz' and line[1:] in widths:
                require(widths[line[1:]] == 1, 'Invalid scalar width')
                changes[line[1:]] = line[0].lower()
            elif line.startswith(('b', 'B')):
                bits, code = line[1:].split()
                if code in widths:
                    require(set(bits.lower()) <= set('01xz') and len(bits) <= widths[code],
                            'Invalid selected vector')
                    changes[code] = bits.lower()
    require(body and last >= 0, 'Missing VCD body')
    consume()
    pulses = [r for r in transitions if (r['old'], r['new']) == (1, 0)]
    require(len(pulses) == 1, 'Exactly one post-startup reset required')
    assertion = pulses[0]
    releases = [r for r in transitions if r['time'] > assertion['time'] and
                (r['old'], r['new']) == (0, 1)]
    require(len(releases) == 1, 'Exactly one reset release required')
    release = releases[0]
    require(not any(assertion['time'] < r['time'] < release['time'] for r in transitions),
            'Reset must remain continuously known and low')
    require(assertion['stage'] == int(selection['ext_value']) and assertion['guard'] == 1,
            'Actual pre-reset stage/guard differs')
    require(assertion['time'] in falls and release['time'] in falls,
            'Reset must be deposited on falling edges')
    held = [t for t in falls if assertion['time'] < t <= release['time']]
    require(len(held) == 4, 'Four full clocks required')
    periods = [b-a for a, b in zip([assertion['time']] + held, held)]
    require(len(set(periods)) == 1 and periods[0] > 0, 'Nonuniform reset clocks')
    return dict(status='ACTUAL_COMPUTE_STAGE_FOUR_CLOCK_RESET_WINDOW_PASS_ONLY',
                target=names['stage'], actual_stage=assertion['stage'], guard=assertion['guard'],
                assertion_timestamp=assertion['time'], release_timestamp=release['time'],
                clock_period_ticks=periods[0], full_clocks=4,
                architecture_checked=False, coverage_admitted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = args.run / 'manifest.json'
    terminal = args.run / 'simulation-status.json'
    wave = args.run / 'external-reset.vcd'
    status = json.loads(terminal.read_bytes())
    require(status['returncode'] == 0 and status['status'] == 'SIMULATION_EXITED_NOT_ADMITTED',
            'Successful simulator terminal required')
    result = audit(wave, json.loads(manifest.read_bytes())['selection'])
    paths = [manifest, terminal, wave, Path(__file__).resolve(),
             Path(__file__).with_name('test_audit_external_reset_window.py')]
    result['pins'] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'actual_stage', 'full_clocks')}))


if __name__ == '__main__':
    main()
