#!/usr/bin/env python3
"""Resource-scoped, host-only replay of one immutable failed bank worker."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = ROOT / 'verification/performance/end_to_end_baseline'
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
WORKER = RUNS / 'e2e_weight_wide_bank_20261106_01'
OUT = RUNS / 'e2e_weight_wide_bank_audit_20261106_01'
OWNED = tuple(HERE / name for name in ('collect_weight_wide_bank.py', 'test_weight_wide_bank_collect.py'))
RESULT_SHA = '146470d39e3e95519881ad634b1cb99e2e3a7449449316e9579d5917d8eeee31'
PINS_SHA = 'd9abda0583a1a2df9a8b3e57c5d0ca645dcf2273e0299379e8016df9e2748315'
RAW_SHA = '545cd523607f6b921da0b7f53ddf75704709d03ddfddce15f6c81f26e7c36616'
CHECKER_SHA = '11c827c460cb1659a92ae1339087ce9fd2926e9f8b192956fc1bf837433a152b'
TB_SHA = '62d192fb2e5835da5eafa8970d08a769c0642a940744ba84c4a07c4a66c354aa'
DUT_SHA = 'afc5492ae3766f327ab56fe47ab3bc77c0fca9f65f0816355c27d9e054b34570'
OBSERVED = dict(mapper_packet_bits=948, logical_low_bytes=128, logical_high_bytes=64,
                logical_sram_bytes=192, target_sram_mc_min_words=8,
                target_sram_mc_physical_bytes=2048, compute_window_bits=128,
                assembler_payload_bits=1024, side_storage_bits=640, compiled_target_sram_mc=0)
CHANGES = dict(logical_low_bytes=(128, 512), logical_high_bytes=(64, 256),
               logical_sram_bytes=(192, 768), assembler_payload_bits=(1024, 4096))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            value.update(chunk)
    return value.hexdigest()


def load_checker():
    path = WORKER / 'source-snapshot/run_weight_wide_bank.py'
    require(digest(path) == CHECKER_SHA, 'Frozen checker identity')
    spec = importlib.util.spec_from_file_location('frozen_bank_checker', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard_worker(result):
    wanted = dict(state='WEIGHT_WIDE_BANK_COMPONENT_FAIL', phase='functional',
                  error="ValueError('Actual resource declaration mismatch')",
                  dut_sha256=DUT_SHA, first_failure_preserved=True, one_component_attempt=True,
                  retry_permitted=False, source_pins_sha256=PINS_SHA, post_pins_match=False,
                  area_measured=False, performance_measured=False, production_path_changed=False,
                  soc_integrated=False)
    require(set(result) == set(wanted) | {'artifacts'} and
            all(type(result[k]) is type(v) and result[k] == v for k, v in wanted.items()),
            'Only the exact original resource FAIL is eligible')
    require(isinstance(result['artifacts'], dict) and len(result['artifacts']) == 18,
            'Original artifact inventory')


def clean_sv(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)


def one(pattern, text):
    matches = list(re.finditer(pattern, text, re.S))
    require(len(matches) == 1, 'Static declaration not unique: ' + pattern)
    return matches[0]


def packed_bits(dimensions):
    pairs = re.findall(r'\[\s*(\d+)\s*:\s*(\d+)\s*\]', dimensions)
    require(re.sub(r'\[\s*\d+\s*:\s*\d+\s*\]', '', dimensions).strip() == '',
            'Unsupported nonliteral packed dimension')
    return math.prod(abs(int(a)-int(b))+1 for a, b in pairs)


def resource_bill(sources):
    """Restricted declaration inspection; production also pins every source byte."""
    dut, mapper, assembler, pkg, payload, tb = (clean_sv(sources[k]) for k in
        ('dut', 'mapper', 'assembler', 'pkg', 'payload', 'tb'))
    compact = lambda s: re.sub(r'\s+', '', s)
    rows = int(one(r'for\s*\(genvar r = 0; r < (\d+); r\+\+\) begin : gen_rows', dut)[1])
    planes = int(one(r'for\s*\(genvar p = 0; p < (\d+); p\+\+\) begin : gen_plane', dut)[1])
    geometry = one(r'qbs_payload_sram\s*#\(\.NumWords\(p == 0 \? (\d+) : (\d+)\), '
                   r'\.DataWidth\((\d+)\)\) i_payload', dut)
    low, high, width = map(int, geometry.groups())
    require((rows, planes, low, high, width) == (4, 2, 4, 2, 256), 'Fixed bank geometry')
    profile_width = packed_bits(one(r'typedef enum logic (\[\d+:\d+\])\s*\{[^}]+\}'
                                    r'\s*qbs_weight_profile_e;', pkg)[1])
    body = one(r'typedef struct packed\s*\{([^}]+)\}\s*packet_t;', mapper)[1]
    packet_fields = {}
    for declaration in body.split(';'):
        if not declaration.strip():
            continue
        match = re.fullmatch(r'\s*(logic|qbs_weight_profile_e)\s*((?:\[\d+:\d+\]\s*)*)'
                             r'(\w+)\s*', declaration)
        require(match is not None, 'Unsupported packet declaration')
        kind, dimensions, name = match.groups()
        require(name not in packet_fields, 'Duplicate packet field')
        packet_fields[name] = packed_bits(dimensions) * (profile_width if kind != 'logic' else 1)
    one(r'packet_t packet_d, packet_q;', mapper)
    data_bits = sum(packed_bits(one(r'logic\s*((?:\[\d+:\d+\]\s*)+)'+name+r';', assembler)[1])
                    for name in ('carry_data_q', 'output_data_q'))
    side = one(r'logic\s*(\[\d+:\d+\])\s*side_q\s*\[(\d+)\]\[(\d+)\];', dut)
    window = one(r'output logic\s*(\[\d+:\d+\])\s*window_o\s*\[(\d+)\]\[(\d+)\]', dut)
    require(tuple(map(int, side.groups()[1:])) == (rows, 20) and
            tuple(map(int, window.groups()[1:])) == (rows, planes), 'Side/window extent')
    macro = one(r'TS1N28HPCPUHDSVTB(\d+)X(256)M1SWBSO i_sram', payload)
    min_words, macro_width = map(int, macro.groups())
    require('`ifndefTARGET_SRAM_MCtc_sram#(.NumWords(NumWords),.DataWidth(DataWidth),'
            '.ByteWidth(8),.NumPorts(1),.Latency(1),.SimInit("none"),'
            '.ImplKey("qbs_payload_1p"))i_sram' in compact(payload), 'Real generic synchronous SRAM path')
    # The pinned bench checks geometry in every generated instance, not the broken sum.
    for fragment in (
        'for(genvar r=0;r<4;r++) begin:gen_observe_row',
        'for(genvar p=0;p<2;p++) begin:gen_observe_plane',
        'if(dut.gen_rows[r].gen_plane[p].i_payload.NumWords != (p==0?4:2) || '
        'dut.gen_rows[r].gen_plane[p].i_payload.DataWidth != 256) $fatal(1,"WB_REAL_SRAM_GEOMETRY");',
        'for(int nrows=1;nrows<=4;nrows++) for(int grouped=0;grouped<2;grouped++) '
        'for(int phase=0;phase<32;phase++) for(int schedule=0;schedule<2;schedule++) '
        'run_epoch(p,nrows,grouped,phase,schedule,0);',
        'window[r][p][8*b+:8] !== payload_value[r][p][start+b]',
        'native_value[r][b]=pattern(p,r,b,salt);',
        "return 8'(1+((p*17+r*53+b*37+epoch*71+b/7)%255));",
        '`ifdef TARGET_SRAM_MC $fatal(1,"WB_GENERIC_REAL_SRAM_REQUIRED"); `endif',
    ):
        require(compact(fragment) in compact(tb), 'Missing instance/readback witness: ' + fragment)
    require(all(len({1+(base+r*53)%255 for r in range(rows)}) == rows for base in range(255)),
            'Readback row pattern is not distinct')
    bill = dict(mapper_packet_bits=sum(packet_fields.values()), logical_low_bytes=rows*low*width//8,
                logical_high_bytes=rows*high*width//8, logical_sram_bytes=rows*(low+high)*width//8,
                target_sram_mc_min_words=min_words,
                target_sram_mc_physical_bytes=rows*planes*min_words*macro_width//8,
                compute_window_bits=packed_bits(window[1]), assembler_payload_bits=rows*planes*data_bits,
                side_storage_bits=packed_bits(side[1])*int(side[2])*int(side[3]), compiled_target_sram_mc=0)
    evidence = dict(rows=rows, planes=planes, instances=rows*planes, low_words_per_row=low,
                    high_words_per_row=high, data_width=width, mapper_field_bits=packet_fields,
                    assembler_data_bits_per_instance=data_bits, geometry_assert_instances=rows*planes,
                    four_row_normal_epochs=9*2*32*2, distinct_row_pattern_verified=True,
                    compiled_target_sram_mc=0, macro_allocation_arithmetic_only=True,
                    scope='Data register bits only, not all flops or area. Macro branch was NOT simulated.')
    return bill, evidence


def project_resource(raw, bill, checker):
    expected = dict(OBSERVED)
    expected.update({k: new for k, (_, new) in CHANGES.items()})
    require(bill == expected == checker.RESOURCES, 'Independently derived static resource bill mismatch')
    lines = raw.decode('utf-8').splitlines(keepends=True)
    found = [i for i, line in enumerate(lines) if line.startswith('WB_RESOURCE')]
    require(len(found) == 1, 'Missing/duplicate resource record')
    index = found[0]
    require(checker.fields(lines[index].rstrip('\r\n'), 'WB_RESOURCE') == OBSERVED,
            'Not the exact known unreliable resource record')
    before = lines[index]
    after = before
    for key, (old, new) in CHANGES.items():
        after, count = re.subn(r'(?<= )'+key+'='+str(old)+r'(?=\s|$)', key+'='+str(new), after)
        require(count == 1, 'Resource-only projection ambiguity')
    lines[index] = after
    projected = ''.join(lines)
    # No helper mutation, bypass, or alternate functional checker.
    return projected, dict(version=2, scope='RESOURCE_ONLY_CHECKER_INPUT_NOT_SIMULATOR_OUTPUT',
                           original_resource_line=before.rstrip('\r\n'),
                           projected_resource_line=after.rstrip('\r\n'),
                           changes={k: dict(observed=a, static=b) for k, (a, b) in CHANGES.items()},
                           raw_sha256=sha(raw), projected_sha256=sha(projected.encode()))


def replay(raw, bill, checker):
    require(sha(raw) == RAW_SHA, 'Only the exact original raw trace is eligible')
    try:
        checker.check(raw.decode('utf-8'))
    except ValueError as exc:
        require(str(exc) == 'Actual resource declaration mismatch', 'Different original check failure')
    else:
        raise ValueError('Original worker unexpectedly passes')
    projected, scope = project_resource(raw, bill, checker)
    measured = checker.check(projected)
    return projected, scope, measured


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def collect(output):
    require(Path(output).absolute() == OUT and OUT.resolve() == OUT, 'Only assigned fresh audit output')
    OUT.mkdir(exist_ok=False)
    pins = {}

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        value = digest(path)
        require(expected is None or value == expected, 'Source/artifact drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == value, 'Conflicting pin: ' + str(path))
        pins[str(path)] = value
        return path

    def verify():
        for path, expected in pins.items():
            require(digest(path) == expected, 'Final identity drift: ' + path)

    result = dict(state='WEIGHT_WIDE_BANK_RESOURCE_SCOPED_REPLAY_FAIL', scope_version=2,
                  original_worker_pass=False, original_worker_state='WEIGHT_WIDE_BANK_COMPONENT_FAIL',
                  original_result_sha256=RESULT_SHA, original_source_pins_sha256=PINS_SHA,
                  new_simulation=False, original_failure_preserved=True, area_measured=False,
                  performance_measured=False, soc_integrated=False, production_path_changed=False)
    try:
        pin(WORKER/'result.json', RESULT_SHA)
        original = json.loads((WORKER/'result.json').read_bytes())
        guard_worker(original)
        pin(WORKER/'source-pins.json', PINS_SHA)
        original_pins = json.loads((WORKER/'source-pins.json').read_bytes())
        require(len(original_pins) == 24, 'Original source/image inventory')
        for path, expected in original_pins.items():
            pin(path, expected)
        for path, expected in original['artifacts'].items():
            require(Path(path).is_relative_to(WORKER), 'Original artifact outside worker')
            pin(path, expected)
        checker = load_checker()
        source_names = {'dut':'qbs_weight_wide_bank.sv', 'mapper':'qbs_weight_wide_mapper.sv',
                        'assembler':'qbs_weight_line_assembler.sv', 'pkg':'qbs_pkg.sv',
                        'payload':'qbs_payload_sram.sv', 'tb':'qbs_weight_wide_bank_tb.sv'}
        for relative, expected in checker.RTL:
            require(original_pins.get(str(ROOT/relative)) == expected and
                    original_pins.get(str(WORKER/'source-snapshot'/Path(relative).name)) == expected,
                    'Current/snapshot RTL binding')
        require(digest(WORKER/'source-snapshot/qbs_weight_wide_bank_tb.sv') == TB_SHA, 'Bench identity')
        commands = json.loads((WORKER/'commands.json').read_bytes())
        require([c['label'] for c in commands] == ['unit-tests', 'compile', 'functional'] and
                all(c['returncode'] == 0 and c['cwd'] == str(WORKER) for c in commands), 'Original execution gates')
        require(commands[2]['argv'] == [str(WORKER/'build/simv')] and
                not any('define' in arg or 'TARGET_SRAM_MC' in arg for arg in commands[1]['argv']),
                'Actual image / generic SRAM compilation binding')
        bill, evidence = resource_bill({k:(WORKER/'source-snapshot'/v).read_text() for k,v in source_names.items()})
        require(bill == checker.RESOURCES, 'Static types differ from frozen expected resource bill')
        snapshot = OUT/'source-snapshot'
        snapshot.mkdir()
        for path in OWNED:
            pin(path)
            dest = snapshot/path.name
            with dest.open('xb') as stream:
                stream.write(path.read_bytes())
            pin(dest, pins[str(path)])
        pin(Path(sys.executable))
        write_json(OUT/'helpers-frozen.json', {str(p):pins[str(p)] for p in OWNED})
        verify()
        command = [str(Path(sys.executable).resolve()), '-B', str(snapshot/OWNED[1].name)]
        with (OUT/'unit-tests.log').open('xb') as stream:
            completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=60, cwd=OUT)
        require(completed.returncode == 0, 'Frozen successor host tests failed')
        write_json(OUT/'commands.json', [dict(argv=command, returncode=completed.returncode, host_only=True)])
        projected, scope, measured = replay((WORKER/'functional.log').read_bytes(), bill, checker)
        with (OUT/'resource-scoped-checker-input.log').open('x') as stream:
            stream.write(projected)
        write_json(OUT/'resource-projection.json', scope)
        write_json(OUT/'resource-bill.json', dict(observed_record_status='UNRELIABLE_ARITHMETIC',
                   observed=OBSERVED, independently_derived_static=bill, evidence=evidence,
                   diagnosis='Four shared initial += tallies are each one fourth of the static bank total. '
                             'Concurrent bookkeeping is unreliable; no simulator defect established.'))
        write_json(OUT/'measured.json', measured)
        normal = {key:sum(p[key] for p in measured['profiles']) for key in
                  ('cases','packets','native','payload','side','reads','read_bytes','idle',
                   'unthrottled_stalls','mixed_stalls','side_mixed_stalls')}
        write_json(OUT/'normal-functional-counts.json', normal)
        verify()
        result.update(state='WEIGHT_WIDE_BANK_FUNCTIONAL_REPLAY_PASS_RESOURCE_TALLY_UNRELIABLE',
                      functional_replay_pass=True, original_source_pin_count=len(original_pins),
                      original_artifact_count=len(original['artifacts']), all_original_pins_current=True,
                      original_report_post_pins_match=original['post_pins_match'], normal=normal,
                      totals=measured['totals'], resource_scope='Static declaration bill, NOT runtime tally/area',
                      unchanged_functional_checker_sha256=CHECKER_SHA)
    except Exception as exc:
        result.update(error=repr(exc), functional_replay_pass=False)
    verify()
    write_json(OUT/'source-pins.json', pins)
    result['source_pins_sha256'] = digest(OUT/'source-pins.json')
    result['artifacts'] = {str(p):digest(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    write_json(OUT/'result.json', result)
    print(json.dumps(dict(state=result['state'], output=str(OUT), result_sha256=digest(OUT/'result.json'),
                          source_pins_sha256=result['source_pins_sha256'])))
    return 0 if result.get('functional_replay_pass') else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    sys.exit(collect(parser.parse_args().output))
