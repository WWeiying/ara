#!/usr/bin/env python3
"""One frozen shared-wrapper/narrow-view compile and two bounded VCS runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
MAIN = Path('/home/wangwy/openproject/ara_dsa')
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OUTPUT = VERIFY / 'verification/out/e2e_wide_clients_20261106_01'
OWNED = ('qbs_wide_clients_tb.sv', 'run_wide_clients.py', 'test_wide_clients.py')
INPUTS = {
    'hardware/deps/axi/src/axi_pkg.sv': '244bd5cb3c5bc58d786f2ed2f5eeefd910c4fe03a175f4a2888c6a2ea1c430dc',
    'hardware/include/qbs_pkg.sv': '5cba22278054776e56d74f01a4833f521729a16953a264fe959dbe8848c33a97',
    'hardware/src/vlsu/qbs/qbs_read_engine.sv': 'b5686b6cac03788ae0c3e48ccfd1e792b0050df8fdba4f6fe3f6994bfd729a3c',
    'hardware/src/vlsu/qbs_akv_shared_reader.sv': '8570fdecf2aa6dc7873ea3ab5ff2a7626016903373e4f500a5899d72fc10ffe2',
    'hardware/src/vlsu/qbs_reader_narrow_view.sv': '58203a859091699396dedb14a3deaacceb13747ed472459d009a8a5a72fd592e',
    'hardware/include/shared_reader_types.svh': 'd4c7c54ff6a8c633aa433d14020154e47f06d0769249ab05caf184e5e19d6f6d',
    'hardware/deps/axi/include/axi/typedef.svh': None,
}
TERMINAL = 'WIDE_CLIENTS_COMPONENT_PASS fixtures=2 normal=128 faults=12 copies=128'
NEGATIVE_ARMED = 'WIDE_CLIENTS_NEGATIVE_ARMED upper_mask=1'
NEGATIVE_REASON = 'QBS_READER_NARROW_VIEW_NONNARROW_PAYLOAD'
BAD = r'(?i)\bfatal\s*:|\berror\s*[-:]|\bUVM_(?:ERROR|FATAL)\b|assertion[^\n]*fail|\boffending\b'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def geometry(start, length, size):
    ars = beats = 0
    width = 1 << size
    while length:
        head = start % width
        take = min(length, 4096-start % 4096, 256*width-head)
        ars += 1
        beats += (head+take+width-1)//width
        start += take
        length -= take
    return ars, beats


def expected_case(width, owner, phase):
    lengths = ((16 if phase % 2 == 0 else 292), 840) if owner == 0 else (64, 83+phase)
    sizes = (4, 5 if width == 256 and owner == 0 else 4)
    counts = [geometry(start+phase, length, size) for start, length, size in
              zip((0x10000, 0x21ff0), lengths, sizes)]
    return dict(width=width, owner=owner, phase=phase, ars=sum(a for a, _ in counts),
                beats=sum(b for _, b in counts), payload=sum(lengths), max_outstanding=2)


def records(text):
    result = []
    for line in text.splitlines():
        if not line.startswith('WIDE_CLIENTS_'):
            continue
        tag, *words = line.split()
        fields = {}
        for word in words:
            key, sep, value = word.partition('=')
            require(sep and key not in fields and re.fullmatch(r'[0-9]+', value), 'Malformed/duplicate record field')
            fields[key] = int(value)
        result.append((tag, fields))
    return result


def check_normal(code, text):
    require(code == 0 and not re.search(BAD, text), 'Normal execution/tool failure')
    rows = records(text)
    require(rows and rows[0] == ('WIDE_CLIENTS_BEGIN', dict(version=1)), 'Missing exact begin')
    require(text.splitlines().count(TERMINAL) == 1 and rows[-1] ==
            ('WIDE_CLIENTS_COMPONENT_PASS', dict(fixtures=2, normal=128, faults=12, copies=128)),
            'Missing/incorrect exact terminal')
    cases = [v for k, v in rows if k == 'WIDE_CLIENTS_CASE']
    key = lambda d: (d['width'], d['owner'], d['phase'])
    expected = [expected_case(w, o, p) for w in (128, 256) for o in (0, 1) for p in range(32)]
    require(sorted(cases, key=key) == expected, 'Normal geometry/inventory mismatch')
    faults = [v for k, v in rows if k == 'WIDE_CLIENTS_FAULT']
    wanted = []
    for w in (128, 256):
        for o in (0, 1):
            beats = geometry(0x8003, 61, 4)[1] + geometry(0x9007, 65, 5 if w == 256 and o == 0 else 4)[1]
            for mode in (0, 1):
                wanted.append(dict(width=w, owner=o, mode=mode, kind=3, ars=2, beats=beats, payload=0))
        wanted.extend((dict(width=w, owner=0, mode=2, kind=5, ars=0, beats=0, payload=0),
                       dict(width=w, owner=1, mode=3, kind=2, ars=0, beats=0, payload=0)))
    fkey = lambda d: (d['width'], d['owner'], d['mode'])
    require(sorted(faults, key=fkey) == sorted(wanted, key=fkey), 'Fault identity/drain inventory mismatch')
    copies = [v for k, v in rows if k == 'WIDE_CLIENTS_COPY_PASS']
    require(sorted(copies, key=lambda d: d['width']) ==
            [dict(width=w, vectors=64, fields=24) for w in (128, 256)], 'Direct field-copy coverage mismatch')
    summaries = [v for k, v in rows if k == 'WIDE_CLIENTS_FIXTURE_PASS']
    require(len(summaries) == 2, 'Missing/duplicate fixture summaries')
    for row, w in zip(sorted(summaries, key=lambda d: d['width']), (128, 256)):
        wanted = dict(width=w, per_range=int(w == 256), normal=64, faults=6, commands=70,
                      payload=sum(x['payload'] for x in expected if x['width'] == w),
                      ars=sum(x['ars'] for x in expected if x['width'] == w),
                      beats=sum(x['beats'] for x in expected if x['width'] == w), stalled_faults=2)
        coverage = {'lower_half', 'upper_half', 'full32', 'data_stalls', 'completion_stalls', 'inactive_checks',
                    'mixed_pairs', 'akv_upper'}
        require(set(row) == set(wanted) | coverage and all(row.get(k) == v for k, v in wanted.items()),
                'Fixture accounting mismatch')
        require(all(row[k] > 0 for k in ('lower_half', 'data_stalls', 'completion_stalls', 'inactive_checks')),
                'Missing backpressure/inactive/lower-half coverage')
        require((row['upper_half'] > row['akv_upper'] > 0 and row['full32'] > 0 and row['mixed_pairs'] > 0)
                if w == 256 else (row['upper_half'] == row['full32'] == row['mixed_pairs'] == row['akv_upper'] == 0),
                'Incorrect wide/narrow physical coverage')
    require(len(rows) == 146, 'Unexpected/duplicate/malformed suite records')
    return dict(cases=cases, faults=faults, copies=copies, summaries=summaries)


def check_negative(code, text, dut):
    require(code in (0, 1), 'Unexpected negative process status')
    require(text.splitlines().count(NEGATIVE_ARMED) == 1, 'Missing exact negative fixture witness')
    require(len(re.findall(r'(?i)\bfatal\s*:', text)) == 1, 'Expected exactly one GLOBAL fatal')
    headers = re.findall(r'(?m)^\s*Fatal:\s*"([^"]+)",\s*(\d+):[^\n]*$', text)
    source = Path(dut).read_text()
    guard_line = next(i for i, line in enumerate(source.splitlines(), 1) if '$fatal' in line and NEGATIVE_REASON in line)
    require(headers == [(str(dut), str(guard_line))], 'Fatal did not originate at the exact narrow-view guard')
    require(text.splitlines().count(NEGATIVE_REASON) == 1, 'Wrong/duplicate negative reason')
    require(re.findall(r'\$finish called from file "([^"]+)"', text) == [str(dut)], 'Wrong/duplicate finish origin')
    require(not re.search(r'(?i)\berror\s*[-:]|\bUVM_(?:ERROR|FATAL)\b|assertion[^\n]*fail|NOT_REJECTED|WIDE_CLIENTS_\w*PASS', text),
            'Unexpected negative diagnostic or normal PASS')
    require([k for k, _ in records(text)] == ['WIDE_CLIENTS_NEGATIVE_ARMED'], 'Unexpected negative records')
    return dict(global_fatals=1, source=str(dut), line=guard_line, reason=NEGATIVE_REASON, returncode=code)


def inspect_workers():
    inventories = []
    owned = {str(HERE/n) for n in OWNED}
    for directory in sorted((VERIFY/'verification/out').iterdir()):
        path = directory/'source-pins.json'
        if not path.is_file():
            continue
        pins = json.loads(path.read_text())
        conflicts = sorted(owned.intersection(pins))
        require(not conflicts, 'Owned source already sealed: ' + str(path))
        if any(n in directory.name for n in ('weight', 'rms_norm_vcs', 'mixed_reader')):
            inventories.append(dict(path=str(path), sha256=digest(path),
                                    inherited_documentation=[k for k in pins if k.lower().endswith('.md')]))
    return inventories


class Campaign:
    def __init__(self, out):
        self.out, self.pins, self.identities, self.commands = out, {}, {}, []

    def pin(self, path, expected=None):
        lexical = Path(path).absolute()
        resolved = lexical.resolve(strict=True)
        value = digest(resolved)
        require(expected is None or expected == value, 'Frozen input mismatch: '+str(path))
        require(str(resolved) not in self.pins or self.pins[str(resolved)] == value, 'Input drift: '+str(path))
        self.pins[str(resolved)] = value
        self.identities[str(lexical)] = str(resolved)
        return value

    def verify(self):
        for path, resolved in self.identities.items():
            require(str(Path(path).resolve(strict=True)) == resolved, 'Path identity drift: '+path)
        for path, expected in self.pins.items():
            require(digest(path) == expected, 'Pinned input/image drift: '+path)

    def run(self, argv, label, timeout):
        argv = list(map(str, argv))
        self.pin(argv[0]); self.verify()
        row = dict(label=label, argv=argv, cwd=str(self.out), timeout_seconds=timeout)
        self.commands.append(row)
        write(self.out/'commands.json', self.commands)
        print('COMMAND '+json.dumps(row), flush=True)
        with (self.out/(label+'.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=self.out, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            row['pid'] = child.pid
            print('CHILD '+str(child.pid)+' '+label, flush=True)
            write(self.out/'commands.json', self.commands)
            try:
                code = child.wait(timeout=timeout)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        row['returncode'] = code
        write(self.out/'commands.json', self.commands)
        self.verify()
        return code, (self.out/(label+'.log')).read_text(errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-frozen', action='store_true')
    args = parser.parse_args()
    require(args.execute_frozen, 'Explicit frozen-module execution required')
    inventory = inspect_workers()
    OUTPUT.mkdir(exist_ok=False)
    c = Campaign(OUTPUT)
    result = dict(state='WIDE_CLIENTS_COMPONENT_FAIL', original_failure_preserved=True,
                  soc_integrated=False, full_engines_executed=False, real_mmu_pmp_tested=False,
                  performance_measured=False, area_measured=False, production_deployment_approved=False,
                  rtl_changed=False, historical_tests_rerun=False, one_compile=True, bounded_simulations=2)
    try:
        write(OUTPUT/'worker-pin-inventory.json', inventory)
        snapshot = OUTPUT/'source-snapshot'
        all_inputs = [(MAIN/name, expected, Path(name)) for name, expected in INPUTS.items()]
        all_inputs += [(HERE/name, None, Path('tests')/name) for name in OWNED]
        for path, expected, relative in all_inputs:
            value = c.pin(path, expected)
            dest = snapshot/relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as stream:
                stream.write(path.read_bytes())
            c.pin(dest, value)
        c.pin(Path(sys.executable))
        write(OUTPUT/'source-pins-precompile.json', c.pins)
        code, text = c.run([sys.executable, '-B', snapshot/'tests/test_wide_clients.py'], 'unit-tests', 60)
        require(code == 0, 'Collector unit tests failed before EDA')
        vcs = shutil.which('vcs')
        require(vcs is not None, 'VCS unavailable')
        c.pin(vcs)
        c.pin(Path(vcs).resolve().parent.parent/'linux64/bin/vcs1')
        build = OUTPUT/'build'; build.mkdir()
        image = build/'simv'
        sv = [snapshot/name for name in INPUTS if name.endswith('.sv')]
        sv += [snapshot/'tests/qbs_wide_clients_tb.sv']
        code, text = c.run([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
                           '+incdir+'+str(snapshot/'hardware/include'),
                           '+incdir+'+str(snapshot/'hardware/deps/axi/include'), *sv,
                           '-top', 'qbs_wide_clients_tb', '-Mdir='+str(build/'csrc'), '-o', image], 'compile', 180)
        require(code == 0 and not re.search(BAD, text), 'First compile failure; preserved, do not rerun')
        c.pin(image)
        for path in sorted(build.rglob('*.so')):
            c.pin(path)
        write(OUTPUT/'source-pins-presimulation.json', c.pins)
        code, text = c.run([image, '-no_save'], 'normal', 120)
        measured = check_normal(code, text)
        write(OUTPUT/'measured.json', measured)
        code, text = c.run([image, '-no_save', '+NEGATIVE_UPPER_MASK'], 'negative-upper-mask', 30)
        negative = check_negative(code, text, snapshot/'hardware/src/vlsu/qbs_reader_narrow_view.sv')
        c.verify()
        result.update(state='WIDE_CLIENTS_SHARED_WRAPPER_NARROW_VIEW_COMPONENT_PASS', post_pins_match=True,
                      measured=measured['summaries'], direct_copy_vectors=128, negative=negative,
                      limitations=['Actual shared wrapper/reader/narrow view with synthetic client endpoints',
                                   'Synthetic permission footprint and translation exception, not real MMU/PMP',
                                   'No full engines, physical SoC width selection, SDK or PPA acceptance'])
    except Exception as exc:
        result.update(error=repr(exc), post_pins_match=False)
    finally:
        write(OUTPUT/'source-pins.json', c.pins)
        write(OUTPUT/'path-identities.json', c.identities)
        write(OUTPUT/'commands.json', c.commands)
        result['source_pins_sha256'] = digest(OUTPUT/'source-pins.json')
        result['artifacts'] = {str(p):digest(p) for p in sorted(OUTPUT.rglob('*'))
                               if p.is_file() and not p.is_relative_to(OUTPUT/'build') and p.name != 'result.json'}
        write(OUTPUT/'result.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return int(result['state'] != 'WIDE_CLIENTS_SHARED_WRAPPER_NARROW_VIEW_COMPONENT_PASS')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
