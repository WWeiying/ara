#!/usr/bin/env python3
"""Host-only, source-bound replay and noncontinuous N64 Decode cost ledger."""

import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys

from audit import require
from prepare_wide_soc import HERE, ROOT, RUNS, VERIFY
import decode_partition_build as builder
import decode_partition_check as checker
from decode_partition_driver import contract, K, PROFILE, ORDER
from decode_partition_run import accept_program, accept_protocol
from run_wide_soc_smoke import elf_admission, check_platform
from continue_wide_soc import SOC_HASH
from check_decode_rvv import check as check_isa

sys.path.insert(0, str(VERIFY / 'verification'))
from ara_verify.uvm_dut import check_real_uvm_log
from ara_verify.artifacts import simulation_image


BUILD = RUNS / 'e2e_decode_partition_build_20261106_01'
BUILD_SHA = 'b697cc4de84ec70cbac40c554ab41d0aeac5b220df28423447bab9e8c397e8a6'
OUTPUT = RUNS / 'e2e_decode_partition_collect_20261106_01'
RESULT_SHA = {
    (0, 128): 'e18870766e5ca6749e90e9672308d689b8a653c6cbaa70535e0c67b1cd7aa97b',
    (0, 256): 'e00eee0eff4ee204a76f84707a2842ed4abe0f3eace1995068b75661ea7b2fc1',
    (1, 128): '34140ac3ef065200cf65fa5223bab9b6b4f50c2bd684e22433d07a7ed0532eee',
    (1, 256): '1956874d9332a90635f8e9d8c0c6dcbb88350b9c73818c5b43222e3728111f2c',
}
NAMES = ('Q', 'V', 'K', 'gate', 'up', 'down', 'vocabulary')
STAGES = (0, 0, 0, 1, 1, 2, 3)
CRITICAL_RTL = {
    'ara_soc.sv', 'ara_tb.sv', 'axi_to_mem.sv', 'vlsu.sv', 'qbs_pkg.sv',
    'vlsu_shared_reader.svh', 'shared_reader_types.svh', 'qbs_compute_engine.sv', 'qbs_read_engine.sv',
    'qbs_akv_shared_reader.sv', 'qbs_profile_engine_int.sv', 'qbs_dot_array.sv',
    'qbs_fp_accumulator.sv', 'qbs_weight_wide_bank.sv',
}
LIMITS = [
    'Two separate same-ELF ABBA partitions, not one continuous seven-part execution or whole-model timing',
    'Full K and N64 slices only; never mechanically multiply these costs by full model N',
    'RVV reference is the N64 prefix of original N128 exact-ELF Spike outputs; partition mixed ELFs never ran in Spike',
    'Native reference is separate QBS C-reference output, not an assertion of RVV/native bit identity',
    'Target checks every selected word/activation byte and guards; external logs contain checksums, not all-word dumps',
    'Preparation is shared by stage; per-part region is not measured and is not attributed',
    'Spike is a functional reference only; all performance numbers here are actual RTL cycles',
    'Flat physical-memory SoC only; no translated MMU/PMP, Linux, synthesis, FPGA or whole-model acceptance',
    'Selected consumed-source/image replay, not a fresh rehash of all inherited worker inventories; original failures remain unchanged',
]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


class Pins:
    def __init__(self):
        self.values = {}
        self.paths = {}

    def add(self, path, expected=None):
        lexical = Path(path).absolute()
        real = lexical.resolve(strict=True)
        require(str(lexical) not in self.paths or self.paths[str(lexical)] == str(real),
                'Input path retargeted: ' + str(lexical))
        self.paths[str(lexical)] = str(real)
        actual = self.values.get(str(real))
        if actual is None:
            actual = sha(real)
        require(expected is None or actual == expected, 'Input SHA differs: ' + str(lexical))
        self.values[str(real)] = actual
        return actual

    def verify(self):
        for path, real in self.paths.items():
            require(str(Path(path).resolve(strict=True)) == real, 'Input path identity changed: ' + path)
        for path, expected in self.values.items():
            require(sha(path) == expected, 'Input content changed: ' + path)

    def read(self, path, expected=None):
        self.add(path, expected)
        return json.loads(Path(path).read_text())


def inventory(pins, root, report):
    return pins.read(root / 'source-pins.json', report['source_pins_sha256'])


def bound(pins, path, inventories):
    key = str(Path(path).resolve(strict=True))
    expected = {inv[key] for inv in inventories if key in inv}
    require(len(expected) == 1, 'Consumed file missing/conflicting predecessor pin: ' + key)
    return pins.add(path, expected.pop())


def accept_run(value, group, width, program):
    wanted = dict(state='DECODE_PARTITION_RTL_ISA_PROTOCOL_PASS', group=group, width=width,
                  child_pid=None, performance_measured=True, independent_protocol_checked=True,
                  whole_model=False, continuous_seven_part_run=False, exact_mixed_elf_spike_executed=False,
                  build_result_sha256=BUILD_SHA, post_pins_match=True,
                  elf=program['elf'], elf_sha256=program['elf_sha256'],
                  checked_guest_outputs=contract(group)['outputs_checked'])
    require(all(k in value and value[k] == v for k, v in wanted.items()), 'Worker admission/scope differs')
    require(value.get('measured', {}).get('independent_reference') ==
            'Original N128 Spike RVV bits exact N64 prefix; separate SDK C-reference bits',
            'Worker independent reference changed')


def platform_fairness(platforms):
    a, b = platforms[128], platforms[256]
    for width, item in platforms.items():
        require(item['state'] == 'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED' and
                item['post_pins_match'] and item['width'] == width, 'Unaccepted physical platform')
        require(item['config']['sim_axi_data_width'] == str(width) and
                item['config']['qbs_wide_weight_ingress'] == str(int(width == 256)),
                'Width/ingress role mismatch')
    exclude = {'sim_axi_data_width', 'qbs_wide_weight_ingress'}
    require({k: v for k, v in a['config'].items() if k not in exclude} ==
            {k: v for k, v in b['config'].items() if k not in exclude}, 'Unfair platform configurations')
    require(a['source_root'] == b['source_root'] and a['prepared_sha256'] == b['prepared_sha256'] and
            a['config']['sim_l2_bytes'] == b['config']['sim_l2_bytes'] == '16777216',
            'Source or physical capacity differs')


def protocol_replay(stored, actual, elf_sha, simv_sha, images):
    expected = dict(actual, elf_sha256=elf_sha, simv_sha256=simv_sha, sim_image_sha256=images)
    require(stored == expected and actual.get('status') == 'PASS' and actual.get('issues') == [],
            'Independent raw protocol replay differs from stored report')
    accept_protocol(stored, elf_sha, actual['log_sha256'], actual['vector_trace_sha256'], images)


def prefix_proof(name, full, subset, expected_sha, isa_hex=None):
    wanted = builder.parent.oracle_payload(name, full)
    require(subset == wanted and hashlib.sha256(subset).hexdigest() == expected_sha,
            'Oracle full-to-prefix mapping differs: ' + name)
    if name.startswith('rvv_'):
        require(isa_hex is not None and len(full) == 512 and full.hex() == isa_hex and len(subset) == 256,
                'N128 ISA-to-N64 prefix proof differs')


def stats(rows, fields):
    result = {}
    for key in fields:
        samples = [r[key] for r in rows]
        require(len(samples) == 2 and all(type(x) is int and x > 0 for x in samples),
                'Two positive ABBA samples required: ' + key)
        result[key] = dict(samples=samples, sum=sum(samples), mean=sum(samples) / 2)
    return result


def ratio(a, b):
    require(a > 0 and b > 0, 'Positive timing required')
    return a / b


def ledger(measured):
    require(set(measured) == set(RESULT_SHA), 'All four partitions/platforms required')
    partitions = []
    for group in (0, 1):
        for width in (128, 256):
            m = measured[group, width]
            require([(t['trial'], t['backend']) for t in m['trials']] == list(enumerate(ORDER)),
                    'ABBA identity changed')
            a = stats([r for r in m['trials'] if r['backend'] == 0],
                      ('preparation', 'admission', 'execution', 'region'))
            b = stats([r for r in m['trials'] if r['backend'] == 1],
                      ('preparation', 'admission', 'execution', 'region'))
            partitions.append(dict(group=group, width=width, parts=contract(group)['parts'],
                                   rvv=a, native=b, rvv_over_native={k: ratio(a[k]['sum'], b[k]['sum']) for k in a}))
        for key in ('parts', 'preparation'):
            omit = {'cycles'} if key == 'preparation' else {'admission', 'execution'}
            project = lambda width: [{k: v for k, v in r.items() if k not in omit}
                                      for r in measured[group, width][key]]
            require(project(128) == project(256), 'Cross-width same-backend numerical/CSR fingerprint differs')
    parts = []
    for part in range(7):
        group = int(part == 5)
        widths = {}
        for width in (128, 256):
            m = measured[group, width]
            backends = {}
            for backend, name in ((0, 'rvv'), (1, 'native')):
                rows = [dict(r, admission_plus_execution=r['admission'] + r['execution'])
                        for r in m['parts'] if r['part'] == part and r['backend'] == backend]
                require([r['trial'] for r in rows] == ([0, 3] if backend == 0 else [1, 2]),
                        'Per-part ABBA samples missing/reordered')
                backends[name] = stats(rows, ('admission', 'execution', 'admission_plus_execution'))
            widths[str(width)] = dict(**backends, rvv_over_native={
                k: ratio(backends['rvv'][k]['sum'], backends['native'][k]['sum']) for k in backends['rvv']})
        parts.append(dict(part=part, name=NAMES[part], group=group, n=64, k=K[part], profile=PROFILE[part],
                          shared_preparation_stage=STAGES[part], widths=widths,
                          width_128_over_256={backend: {
                              k: ratio(widths['128'][backend][k]['sum'], widths['256'][backend][k]['sum'])
                              for k in widths['128'][backend]} for backend in ('rvv', 'native')},
                          per_part_region_measured=False))
    prep = []
    for stage in range(4):
        group = int(stage == 2)
        prep.append(dict(stage=stage, group=group, shared_by_parts=[p for p in range(7) if STAGES[p] == stage],
                         widths={str(w): {name: stats([r for r in measured[group, w]['preparation']
                             if r['stage'] == stage and r['backend'] == backend], ('cycles',))['cycles']
                             for backend, name in ((0, 'rvv'), (1, 'native'))} for w in (128, 256)}))
    sums = []
    for width in (128, 256):
        values = {}
        for name in ('rvv', 'native'):
            values[name] = {key: sum(p[name][key]['mean'] for p in partitions if p['width'] == width)
                            for key in ('preparation', 'admission', 'execution', 'region')}
        sums.append(dict(width=width, mean_cycles=values,
                         rvv_over_native={k: ratio(values['rvv'][k], values['native'][k]) for k in values['rvv']},
                         continuous_measurement=False))
    return dict(parts=parts, preparation_stages=prep, partitions=partitions,
                noncontinuous_seven_part_ledger=sums,
                whole_model=False, full_n=False, continuous_seven_part_run=False,
                exact_mixed_elf_spike_executed=False)


def collect(output):
    require(output.absolute() == OUTPUT and output.absolute() == output.resolve(), 'Exact fresh output required')
    out = output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    pins = Pins()
    result = dict(state='PREPARING', host_only=True, simulations_launched=0, rtl_changed=False,
                  whole_model=False, continuous_seven_part_run=False, exact_mixed_elf_spike_executed=False)
    try:
        pins.add(Path(__file__))
        pins.add(HERE / 'test_collect_decode_partition.py')
        pins.add(sys.executable)
        build = pins.read(BUILD / 'build.json', BUILD_SHA)
        accept_program(build, 0)
        bp = inventory(pins, BUILD, build)
        require(not any('/qemu' in path.lower() for path in bp), 'Unexpected unrelated QEMU closure')
        for path, expected in bp.items():
            pins.add(path, expected)
        for path, expected in build['artifacts'].items():
            pins.add(path, expected)
        base = builder.BASE
        parent = pins.read(base / 'build.json', builder.BASE_SHA)
        pp = inventory(pins, base, parent)
        pins.add(parent['elf'], builder.BASE_ELF_SHA)
        isa_root = builder.parent.ISA
        isa = pins.read(isa_root / 'result.json', builder.parent.ISA_SHA)
        require(isa['state'] == 'EXACT_ELF_RVV_SPIKE_REFERENCE_PASS' and isa['post_pins_match'] and
                isa['independent_isa_output_words'] == 896 and isa['csr_records'] == 11,
                'Accepted original N128 ISA evidence required')
        ip = inventory(pins, isa_root, isa)
        pins.add(isa['elf'], isa['elf_sha256'])
        pins.add(isa_root / 'spike.log', isa['artifacts'][str(isa_root / 'spike.log')])
        full_native, packed = [], []
        for name, record in parent['oracle_copies'].items():
            source = Path(record['source'])
            pins.add(source, record['source_sha256'])
            target = BUILD / 'oracle' / name
            pins.add(target, record['sha256'])
            prefix_proof(name, source.read_bytes(), target.read_bytes(), record['sha256'],
                         isa['measured']['outputs_hex'][int(name[4])] if name.startswith('rvv_') else None)
        for part in range(7):
            full_native.append(Path(parent['oracle_copies'][f'native_{part}.bin']['source']).read_bytes())
        for stage in range(4):
            packed.append((BUILD / 'oracle' / f'activation_{stage}.bin').read_bytes())
        isa_actual = check_isa((isa_root / 'spike.log').read_text(), full_native, packed, isa_model=True)
        require(isa_actual == isa['measured'], 'Original N128 ISA raw replay differs')
        for old in build['old_results']:
            previous = pins.read(old['path'], old['sha256'])
            require(previous['state'] == 'FAIL' and previous['error'] == old['error'] and old['relabeled'] is False,
                    'Original failed/timed-out worker changed')
        platforms, images, inventories = {}, {}, [bp, pp, ip]
        for width in (128, 256):
            root = RUNS / f'e2e_physical_wide_soc{width}_20261106_01'
            soc = pins.read(root / 'result.json', SOC_HASH[width])
            sp = inventory(pins, root, soc)
            inventories.append(sp)
            for path, expected in soc['artifacts'].items():
                pins.add(path, expected)
            actual_images = simulation_image(Path(soc['simv']))
            require(actual_images == soc['image_pins'] and len(actual_images) > 1, 'Actual image set differs')
            for path, expected in actual_images.items():
                pins.add(path, expected)
            source_root = Path(soc['source_root'])
            critical = {Path(path).name for path in sp if Path(path).is_relative_to(source_root) and
                        Path(path).name in CRITICAL_RTL}
            require(CRITICAL_RTL <= critical, 'Missing consumed critical RTL source inventory')
            for path, expected in sp.items():
                if Path(path).is_relative_to(source_root) and Path(path).name in CRITICAL_RTL:
                    pins.add(path, expected)
            platforms[width], images[width] = soc, actual_images
        platform_fairness(platforms)
        workers = {}
        for (group, width), expected in RESULT_SHA.items():
            root = RUNS / f'e2e_decode_partition{group}_rtl{width}_20261106_01'
            worker = pins.read(root / 'result.json', expected)
            accept_run(worker, group, width, build['groups'][group])
            inv = inventory(pins, root, worker)
            inventories.append(inv)
            for path, expected in worker['artifacts'].items():
                pins.add(path, expected)
            require(worker['image_pins'] == images[width] and worker['simv'] == platforms[width]['simv'],
                    'Worker actual platform image identity differs')
            program = build['groups'][group]
            require(elf_admission(Path(worker['elf']).read_bytes(), width // 8) ==
                    worker['preload_segments'] == program['preload_segments'][str(width)],
                    'ELF preload footprint differs')
            workers[group, width] = (root, worker)
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(r) for r in (ROOT, VERIFY)):
                path = Path(path).resolve()
                if path not in (Path(__file__).resolve(), HERE / 'test_collect_decode_partition.py'):
                    bound(pins, path, inventories)
        pins.verify()
        measured, runs = {}, []
        oracle = checker.oracle(BUILD)
        for (group, width), (root, worker) in workers.items():
            print(f'Replaying partition={group} physical_bits={width}', flush=True)
            work = root / 'work'
            raw = (work / 'run.vcs.log').read_text()
            actual = checker.check(raw, group, width, *oracle)
            require(actual == worker['measured'] and check_platform(raw, width) == worker['platform'],
                    'Actual target raw replay differs from worker')
            del raw
            gc.collect()
            actual_protocol = check_real_uvm_log(work / 'run.vcs.log', require_events=True,
                require_backend=True, require_axi=True, require_axi_write=True,
                vector_trace=work / 'vector_trace.csv')
            stored = json.loads((work / 'uvm_result.json').read_text())
            protocol_replay(stored, actual_protocol, worker['elf_sha256'], sha(worker['simv']), images[width])
            measured[group, width] = actual
            runs.append(dict(group=group, width=width, result=str(root / 'result.json'),
                             result_sha256=RESULT_SHA[group, width], elf=worker['elf'],
                             elf_sha256=worker['elf_sha256'], worker_inventory_entries=len(inventory(pins, root, worker)),
                             raw_replay_exact=True, protocol_replay_exact=True,
                             native_commands=actual['native_commands'], outputs_checked=actual['outputs_checked'],
                             protocol={k: actual_protocol[k] for k in ('uvm_counts', 'contract_counts', 'backend_counts',
                                 'axi_read_counts', 'axi_write_counts', 'uvm_event_sha256', 'uvm_backend_event_sha256')}))
            gc.collect()
        summary = ledger(measured)
        (out / 'ledger.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
        pins.verify()
        result.update(state='DECODE_PARTITION_FOUR_RUNS_INDEPENDENT_RAW_REPLAY_PASS', runs=runs,
                      actual_eda_executions=0, inherited_rtl_simulations=4, independent_protocol_replays=4,
                      original_n128_isa_raw_replayed=True, isa_reference_result_sha256=builder.parent.ISA_SHA,
                      same_group_elf_across_widths=True, same_elf_contains_both_backends=True,
                      source_pin_scope='All 161 partition-build inputs/artifacts; consumed replay helpers, critical frozen RTL, '
                          'complete images and four raw artifact sets; inherited inventory manifests bound but not fully rehashed',
                      whole_model=False, continuous_seven_part_run=False, exact_mixed_elf_spike_executed=False,
                      post_pins_match=True, limits=LIMITS)
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        try:
            pins.verify()
        except Exception as exc:
            result.update(state='FAIL', post_pins_match=False, pin_error=repr(exc))
        (out / 'source-pins.json').write_text(json.dumps(pins.values, indent=2, sort_keys=True) + '\n')
        (out / 'path-identities.json').write_text(json.dumps(pins.paths, indent=2, sort_keys=True) + '\n')
        result.update(source_pins_sha256=sha(out / 'source-pins.json'), selected_pins=len(pins.values),
                      path_identities=len(pins.paths), artifacts={str(p): sha(p) for p in out.iterdir()
                          if p.is_file() and p.name != 'result.json'})
        (out / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    require(result['state'] == 'DECODE_PARTITION_FOUR_RUNS_INDEPENDENT_RAW_REPLAY_PASS', 'Collector failed')
    print(json.dumps(dict(state=result['state'], result=str(out / 'result.json'),
                          result_sha256=sha(out / 'result.json'), selected_pins=result['selected_pins'])))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    collect(parser.parse_args().output)
