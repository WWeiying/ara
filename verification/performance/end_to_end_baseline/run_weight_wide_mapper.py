#!/usr/bin/env python3
"""Bounded standalone VCS test of an uninstantiated native-weight packet mapper."""
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
ROOT = HERE.parents[2]
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
V1 = RUNS / 'e2e_weight_wide_mapper_20261106_01'
OUT = RUNS / 'e2e_weight_wide_mapper_20261106_02'
V1_RESULT_SHA = '8f085ede0c0cbbcfe1082fa8d87154edc800c5f6dc13ef9aab0ff475d3f03f4e'
V1_PINS_SHA = 'e6117a0e517c4658912a6833f45c6011e420de4b6f7f39704b4885b7571e9bb6'
DUT = ROOT / 'hardware/src/vlsu/qbs/qbs_weight_wide_mapper.sv'
PKG = ROOT / 'hardware/include/qbs_pkg.sv'
OWNED = (DUT, HERE / 'qbs_weight_wide_mapper_tb.sv', Path(__file__).resolve(), HERE / 'test_weight_wide_mapper.py')
# Independent explicit native regions: bytes, low start/count, high start/count,
# side ranges (native start/count, destination offset).
REGIONS = {
    1: (144, 16, 128, 0, 0, ((0, 16, 0),)),
    2: (210, 0, 128, 128, 64, ((192, 18, 0),)),
    3: (18, 2, 16, 0, 0, ((0, 2, 0),)),
    4: (176, 48, 128, 16, 32, ((0, 16, 0),)),
    5: (110, 32, 64, 0, 32, ((96, 14, 0),)),
    6: (34, 2, 32, 0, 0, ((0, 2, 0),)),
    7: (84, 16, 64, 0, 0, ((0, 16, 0), (80, 4, 16))),
    8: (22, 6, 16, 0, 0, ((0, 6, 0),)),
    9: (18, 2, 16, 0, 0, ((0, 2, 0),)),
}
REJECTIONS = dict(empty='STRB', prefix='STRB', row_range='RANGE', group_range='RANGE',
                  row='ROW', rows='ROWS', profile='PROFILE', unknown='UNKNOWN')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def write_new(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def locate(profile, native):
    size, ls, ln, hs, hn, sides = REGIONS[profile]
    require(0 <= native < size, 'Oracle native bounds')
    if ls <= native < ls + ln:
        return 0, native - ls, native == ls + ln - 1
    if hn and hs <= native < hs + hn:
        return 1, native - hs, native == hs + hn - 1
    for start, count, offset in sides:
        if start <= native < start + count:
            return 2, offset + native - start, False
    raise ValueError('Incomplete explicit region table')


def expected_coverage():
    profiles = []
    keys = ('cases', 'packets', 'decoded', 'payload', 'side', 'lasts', 'heads', 'fulls', 'tails', 'cross_rows', 'cross_planes')
    for profile, regions in REGIONS.items():
        size = regions[0]
        row = dict(profile=profile, **dict.fromkeys(keys, 0))
        for rows in range(1, 5):
            for grouped in (0, 1):
                for phase in range(32):
                    row['cases'] += 2  # two traffic schedules, identical packetization
                    for r in range(1 if grouped else rows):
                        limit = size * rows if grouped else size
                        start_phase = phase if grouped else (phase + r * size) % 32
                        cursor = 0
                        while cursor < limit:
                            amount = min(32 - start_phase if cursor == 0 else 32, limit - cursor)
                            row['packets'] += 2
                            row['decoded'] += 2 * amount
                            row['heads'] += 2 * (cursor == 0 and start_phase != 0)
                            row['tails'] += 2 * (cursor + amount == limit and (start_phase + limit) % 32 != 0)
                            row['fulls'] += 2 * (amount == 32)
                            touched_rows, touched_planes = set(), set()
                            for b in range(amount):
                                address = cursor + b
                                target = address // size if grouped else r
                                native = address % size if grouped else address
                                plane, _, last = locate(profile, native)
                                row['payload' if plane < 2 else 'side'] += 2
                                row['lasts'] += 2 * last
                                touched_rows.add(target)
                                touched_planes.add(plane)
                            row['cross_rows'] += 2 * (len(touched_rows) > 1)
                            row['cross_planes'] += 2 * (len(touched_planes) > 1)
                            cursor += amount
        profiles.append(row)
    return profiles


def fields(line, prefix):
    require(line.startswith(prefix + ' '), 'Wrong log record')
    values = {}
    for word in line[len(prefix) + 1:].split():
        key, sep, value = word.partition('=')
        require(sep and key not in values and re.fullmatch('[0-9]+', value), 'Malformed/duplicate log fields')
        values[key] = int(value)
    return values


def check(text):
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:ERROR|FATAL)|QBS_WIDE_REJECT|WIDE_NEGATIVE', text),
            'Unexpected simulator/assertion failure')
    records = text.replace('\r', '').splitlines()
    epochs = [fields(line, 'WIDE_MAPPER_EPOCH') for line in records if line.startswith('WIDE_MAPPER_EPOCH')]
    reductions = [fields(line, 'WIDE_REDUCTION_PASS') for line in records if line.startswith('WIDE_REDUCTION_PASS')]
    require(epochs == [dict(epoch=2)] and reductions == [dict(vectors=1282)],
            'Missing v2 execution epoch or independent reduction checks')
    expected = expected_coverage()
    profiles = [fields(line, 'WIDE_PROFILE_PASS') for line in records if line.startswith('WIDE_PROFILE_PASS')]
    require(profiles == expected, 'Missing/duplicate/inexact profile coverage or decoded byte counts')
    final = [fields(line, 'WIDE_MAPPER_COMPONENT_PASS') for line in records if line.startswith('WIDE_MAPPER_COMPONENT_PASS')]
    require(len(final) == 1, 'Missing/duplicate functional terminal')
    row = final[0]
    required = ('cases', 'packets', 'decoded', 'payload', 'side', 'lasts')
    totals = {key: sum(p[key] for p in expected) for key in required}
    discarded = 2 * sum(min(32, region[0]) + 32 for region in REGIONS.values())
    totals.update(abort_cases=36, discarded=discarded, accepted=totals['decoded'] + discarded)
    require(set(row) == set(totals) | {'stalls', 'output_stalls'} and
            all(row[k] == value for k, value in totals.items()) and
            row['stalls'] > 0 and row['output_stalls'] > 0, 'Incomplete byte/state conservation or backpressure')
    require(sum(line.startswith('WIDE_') for line in records) == 12, 'Unexpected component records')
    return dict(functional_epoch=2, reduction_vectors=1282, profiles=profiles, totals=row, input_ii1_checked=True,
                oracle='Explicit nine-profile native regions, not package mapping; each native byte checked exactly once',
                shared_data_and_all_metadata_checked=True, stall_stability_checked=True, clear_reset_drop_checked=True,
                invalid_packet_not_reset_or_cleared_checked=True)


def check_rejection(text, name, returncode):
    require(name in REJECTIONS, 'Unknown expected rejection')
    wanted = 'QBS_WIDE_REJECT_' + REJECTIONS[name]
    require(text.count('WIDE_NEGATIVE_ARMED name=' + name + '\n') == 1 and text.count('Fatal:') == 1 and
            re.findall(r'\bQBS_WIDE_REJECT_[A-Z]+\b', text) == [wanted] and
            'qbs_weight_wide_mapper.sv' in text and
            not re.search(r'WIDE_NEGATIVE_NOT_REJECTED|WIDE_PROFILE_PASS|WIDE_MAPPER_COMPONENT_PASS|Error[-:]|TB ', text),
            'Missing exact DUT contract assertion: ' + name)
    return dict(name=name, assertion=wanted, returncode=returncode,
                classification='expected_contract_rejection_not_normal_functional_PASS')


class Pins:
    def __init__(self):
        self.values = {}

    def pin(self, path):
        path = Path(path).resolve(strict=True)
        value = digest(path)
        require(str(path) not in self.values or self.values[str(path)] == value, 'Input drift: ' + str(path))
        self.values[str(path)] = value

    def verify(self):
        for path, sha in self.values.items():
            require(digest(path) == sha, 'Final source/image drift: ' + path)


def inventories():
    names = ('e2e_sdk_dispatch_model_pair_20261106_01', 'e2e_sdk_dispatch_model_campaign_20261106_01',
             'e2e_rms_norm_vcs_20261106_01', 'e2e_sdk_single_input_vcs_20261106_01',
             'e2e_weight_line_assembler_20261106_01')
    out = []
    for name in names:
        path = RUNS / name / 'source-pins.json'
        data = path.read_bytes()
        pins = json.loads(data)
        conflicts = [str(p) for p in OWNED if str(p) in pins]
        require(not conflicts, 'Owned source already sealed: ' + repr(conflicts))
        out.append(dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), entries=len(pins),
                        conflicts=conflicts, inherited_documentation={k: v for k, v in pins.items() if k.lower().endswith('.md')}))
    return out


def oracle_region_text(text):
    start = text.index('  task automatic regions(')
    end = text.index('  task automatic check_packet;', start)
    return text[start:end]


def module_ports(text):
    start = text.index('module qbs_weight_wide_mapper (')
    end = text.index(');\n  import qbs_pkg::*;', start) + 2
    return text[start:end]


def preserve_v1(pins):
    pins.pin(V1 / 'result.json')
    pins.pin(V1 / 'source-pins.json')
    require(digest(V1 / 'result.json') == V1_RESULT_SHA and digest(V1 / 'source-pins.json') == V1_PINS_SHA,
            'Original v1 receipt identity changed')
    result = json.loads((V1 / 'result.json').read_text())
    prior_pins = json.loads((V1 / 'source-pins.json').read_text())
    require(result['state'] == 'WEIGHT_WIDE_MAPPER_COMPONENT_PASS' and
            result['source_pins_sha256'] == V1_PINS_SHA, 'Original v1 evidence not accepted')
    for path, value in result['artifacts'].items():
        require(Path(path).is_relative_to(V1) and digest(path) == value, 'v1 artifact changed: ' + path)
        pins.pin(path)
    images = {}
    for path, value in prior_pins.items():
        if Path(path).is_relative_to(V1 / 'build'):
            require(digest(path) == value, 'v1 actual image changed: ' + path)
            pins.pin(path)
            images[path] = value
    require(str(V1 / 'build/simv') in images, 'v1 actual executable absent')
    require(oracle_region_text((HERE / 'qbs_weight_wide_mapper_tb.sv').read_text()) ==
            oracle_region_text((V1 / 'source-snapshot/qbs_weight_wide_mapper_tb.sv').read_text()),
            'Independent native region oracle changed during structural refactor')
    require(module_ports(DUT.read_text()) == module_ports((V1 / 'source-snapshot' / DUT.name).read_text()),
            'v1/v2 public mapper ports changed')
    require(digest(PKG) == prior_pins[str(V1 / 'source-snapshot' / PKG.name)], 'Generated package changed')
    return dict(result_sha256=V1_RESULT_SHA, source_pins_sha256=V1_PINS_SHA, actual_images=images,
                snapshot_and_actual_image_preserved=True, ports_and_region_oracle_unchanged=True,
                use='Historical v1 evidence only; canonical files now v2; never inherited as v2 functional PASS')


def run(output):
    output = Path(output).absolute()
    nested = output.parent == OUT and output.name in {f'attempt-{i:02d}' for i in range(1, 100)}
    require((output == OUT or nested) and output == output.resolve(), 'Only assigned fresh component output allowed')
    observations = inventories()
    output.mkdir(exist_ok=False)
    pins, commands = Pins(), []
    result = dict(state='WEIGHT_WIDE_MAPPER_COMPONENT_FAIL', functional_epoch=2, current_acceptance_epoch=2,
                  v1_pass_used_for_v2_acceptance=False, soc_integrated=False, production_path_changed=False,
                  assembler_instantiated=False, physical_supply_widened=False, performance_measured=False, area_measured=False)

    def command(argv, label, bound):
        argv = list(map(str, argv))
        pins.pin(argv[0])
        pins.verify()
        row = dict(label=label, argv=argv, cwd=str(output), timeout=bound)
        commands.append(row)
        with (output / (label + '.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=output, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
        row['returncode'] = code
        pins.verify()
        return code, (output / (label + '.log')).read_text()

    try:
        write_new(output / 'worker-pin-inventory.json', observations)
        v1 = preserve_v1(pins)
        write_new(output / 'v1-preserved-evidence.json', v1)
        snapshot = output / 'source-snapshot'
        snapshot.mkdir()
        for path in (*OWNED, PKG):
            pins.pin(path)
            destination = snapshot / path.name
            with destination.open('xb') as stream:
                stream.write(path.read_bytes())
            pins.pin(destination)
            require(digest(path) == digest(destination), 'Snapshot differs')
        pins.pin(Path(sys.executable).resolve())
        code, _ = command([sys.executable, '-B', snapshot / 'test_weight_wide_mapper.py'], 'unit-tests', 60)
        require(code == 0, 'Host checker tests failed')
        vcs = shutil.which('vcs')
        require(vcs is not None, 'Host VCS unavailable')
        pins.pin(vcs)
        vcs1 = Path(vcs).resolve().parent.parent / 'linux64/bin/vcs1'
        if vcs1.is_file():
            pins.pin(vcs1)
        build = output / 'build'
        build.mkdir()
        image = build / 'simv'
        write_new(output / 'source-pins-precompile.json', pins.values)
        code, log = command([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
                             snapshot / PKG.name, snapshot / DUT.name, snapshot / 'qbs_weight_wide_mapper_tb.sv',
                             '-top', 'qbs_weight_wide_mapper_tb', '-Mdir=' + str(build / 'csrc'), '-o', image], 'compile', 180)
        require(code == 0 and not re.search(r'Error[-:]|Fatal:', log), 'Component compile failed')
        pins.pin(image)
        for path in sorted(build.rglob('*.so')):
            pins.pin(path)
        code, log = command([image], 'functional', 120)
        require(code == 0, 'Component simulator returned failure')
        measured = check(log)
        rejected = []
        for name in REJECTIONS:
            code, log = command([image, '+NEGATIVE=' + name], 'reject-' + name, 15)
            rejected.append(check_rejection(log, name, code))
        write_new(output / 'measured.json', measured)
        write_new(output / 'contract-rejections.json', rejected)
        write_new(output / 'ports.json', dict(
            inputs={'clk_i,rst_ni,clear_i,valid_i,ready_i': 'logic', 'profile_i': 'qbs_weight_profile_e',
                    'row_count_i': '[2:0], 1..4', 'group_mode_i': '0=row-local, 1=contiguous R4 blocks',
                    'row_i': '[1:0], ignored in group mode', 'offset_i': '[9:0], row-local or R4 byte offset',
                    'data_i': '[255:0], source byte b at [8*b+:8]', 'strb_i': '[31:0], nonempty compacted prefix'},
            outputs={'ready_o,valid_o': 'elastic handshake', 'data_o': 'one registered shared [255:0]',
                     'profile_o,row_count_o,group_mode_o,row_o,offset_o,strb_o': 'registered input metadata',
                     'source_start_o': '[3:0][1:0][4:0], row x plane source index',
                     'count_o': '[3:0][1:0][5:0], 0 disables segment; otherwise prefix length 1..32',
                     'payload_offset_o': '[3:0][1:0][7:0], first destination payload byte',
                     'payload_last_o': '[3:0][1:0], segment contains actual native payload-region final byte',
                     'side_mask_o': '[3:0][19:0]', 'side_source_index_o': '[3:0][19:0][4:0]'},
            wrapper_contract='For each enabled segment: shift shared data right by 8*source_start; generate prefix(count). '
                             'No SRAM/AXI/assembler instance is present; clear/reset drops valid only; invalid packet contents are unspecified',
            structure='v2 independent per-byte decode; fixed row/plane and side hit masks; balanced 32-way popcount/first-one; '
                      'one-hot OR source/offset encoding; only valid has reset/clear; no synthesis/PPA measurement',
            latency='one registered elastic stage; II=1 with ready sink', functional_epoch=2, regions=REGIONS))
        pins.verify()
        result.update(state='WEIGHT_WIDE_MAPPER_COMPONENT_PASS', measured=measured['totals'],
                      contract_rejections=len(rejected), post_pins_match=True,
                      reduction_vectors=measured['reduction_vectors'], v1_preservation=v1,
                      limitations=['Uninstantiated component only, not SoC/FPGA/performance/area acceptance',
                                   'Validated-descriptor profiles, nonempty compacted source prefixes, at most four native rows',
                                   'Future wrapper must shift shared data per segment and connect private assemblers'])
    except Exception as exc:
        result.update(error=repr(exc), post_pins_match=False)
    write_new(output / 'source-pins.json', pins.values)
    write_new(output / 'commands.json', commands)
    result['source_pins_sha256'] = digest(output / 'source-pins.json')
    result['artifacts'] = {str(p): digest(p) for p in sorted(output.rglob('*'))
                           if p.is_file() and not p.is_relative_to(output / 'build')}
    write_new(output / 'result.json', result)
    print(json.dumps(result, indent=2))
    return 0 if result['state'] == 'WEIGHT_WIDE_MAPPER_COMPONENT_PASS' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    return run(parser.parse_args(argv).output)


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
