"""Fixed 7x8 unit-stride stores: formal729 targets and host/Spike only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess

import build_opivx_vsbc_preflight as shared
import collect_opivx_vsbc_strict as strict
from inventory_operand_debug import Design, points

life, require = shared.life, shared.require
ROOT, OUT, LLVM, SPIKE = shared.ROOT, shared.OUT, shared.LLVM, shared.SPIKE
BASE = OUT / 'gap107-offline-admitted-729-parent-20261006-01'
BASE_SEAL = 'e5bd9eeb19acc452d25db12f342c3c12532614a0c773c43355a33e34d8dd1912'
SOURCE_PINS = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
SOURCE_SEAL = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
NAME = 'vstore_fifo_burst'
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vstore_fifo_burst.c'
LENGTHS = (4, 8, 12, 16, 20, 28, 32)
CHECKS, SENTINEL = 2360, 0xa5a5a5a5
STORE, STEP = 0x02056427, 0x09050513
SYMBOLS = ('tohost', 'g75_result', 'num_failed', 'trap_fail', 'g75_trap',
           'sfb_seed', 'sfb_dest', 'sfb_dump', 'sfb_cfg', 'sfb_init',
           'sfb_burst_begin', 'sfb_burst_end', 'sfb_dump_pc', '_end', '_start')
STATUS = 'STORE_FIFO_BURST_HOST_SPIKE_PASS_NOT_DUT_NOT_ADMITTED'


def source(word):
    require(0 <= word < 36, 'Source word range')
    return SENTINEL if word < 2 or word >= 34 else 0x91e70031 ^ ((word - 2) * 0x01030507)


def destination(phase, word):
    require(0 <= phase < 7 and 0 <= word < 36, 'Destination range')
    return source(word) if 2 <= word < 2 + LENGTHS[phase] else SENTINEL


def zero_target(record, width, checksum, index):
    require((record['width'], record['checksum']) == (width, checksum), 'Target shape drift')
    require(not int(record['bits'], 16) & (1 << (width - 1 - index)), 'Target already hit729')


def target_binding():
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    paths = {str(BASE / 'admission-manifest.json'): BASE_SEAL}
    for name in ('combined-bits.json', 'status.json', 'evidence-pins.json'):
        p = BASE / name
        paths[str(p)] = manifest['output_pins'][str(p)]
        life.read_bound(p, paths[str(p)])
    bits = json.loads((BASE / 'combined-bits.json').read_bytes())
    status = json.loads((BASE / 'status.json').read_bytes())
    require(status['coverage_admitted'] is True and status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY', 'Nonformal baseline')
    require(len(bits['tests']) == len(set(bits['tests'])) == 729 and
            sum(len(v) for v in bits['metrics'].values()) == 6162, 'Not exact729/6162')
    srcpins = life.read_bound(SOURCE_PINS, SOURCE_SEAL)
    paths[str(SOURCE_PINS)] = SOURCE_SEAL
    for relative in ('hardware/src/lane/operand_queue.sv', 'hardware/src/lane/operand_queues_stage.sv',
                     'hardware/src/lane/operand_requester.sv', 'hardware/include/ara_pkg.sv',
                     'hardware/deps/common_cells/src/fifo_v3.sv'):
        p = ROOT / relative
        require(life.digest(p) == srcpins[str(p)], 'Frozen source differs: ' + relative)
        paths[str(p)] = srcpins[str(p)]
    for name in ('lane_sequencer.sv', 'ara_dispatcher.sv'):
        snapshot = OUT / 'old-image-source-evidence-20261006-01' / name
        original = ROOT / 'hardware/src' / ('lane/' if name == 'lane_sequencer.sv' else '') / name
        require(life.digest(snapshot) == srcpins[str(original)], 'Frozen snapshot drift')
        paths[str(snapshot)] = srcpins[str(original)]
    d = Design(Path(str(life.IMAGE) + '.vdb'))
    paths.update({str(d.db / p): h for p, h in bits['design'].items()})
    paths[str(d.db / 'auxiliary/verilog.sourceinfo.xml')] = life.digest(d.db / 'auxiliary/verilog.sourceinfo.xml')
    life.check(paths)
    rows = []
    for lane in range(4):
        scope = f'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{lane}].i_lane.i_operand_queues.i_operand_queue_st_mask_a.i_cmd_buffer'
        require(d.source(scope)['resolved_path'] == str(ROOT / 'hardware/deps/common_cells/src/fifo_v3.sv') and
                d.hierarchy[scope].get('chksum') == '3314732922', 'Compiled owner drift')
        line = d.definition(scope, 'line')
        require(line.get('chksum') == '2107957445', 'Depth5 line specialization differs')
        branch = [n for n in d.shapes['branch'] if n.get('id') == '-28' and n.get('chksum') == '1132753425']
        require(len(branch) == 1, 'Depth5 branch specialization ambiguous')
        for metric, node, width, checksum, index in (
                ('branch', branch[0], 17, None, 7), ('line', line, 30, '2107957445', 13)):
            zero_target(bits['metrics'][metric][scope], width, checksum, index)
            point = next(p for p in points(metric, node, width) if p['raw_index'] == index)
            if metric == 'branch':
                require(point['native_id'] == '2' and point['native_vector'] == {'id': '0', 'vector': '01'} and
                        point['attributes']['chksum'] == '3174745807' and point['line'] == '101' and
                        point['expression'] == '(((push_i && pop_i) && (~full_o)) && (~empty_o))', 'Exact conjunction binding drift')
            else:
                require(point['line'] == '102' and point['expression'] == 'status_cnt_n = status_cnt_q;', 'Exact line binding drift')
            rows.append(dict(scope=scope, metric=metric, raw_index=index, width=width,
                             checksum=checksum, shape_checksum=node.get('chksum'), point=point,
                             hit729=False, native_GUI_binding=False))
    return rows, paths


def elf_word(blob, pc):
    require(blob[:6] == b'\x7fELF\x02\x01', 'Not ELF64 LE')
    h = struct.unpack_from('<HHIQQQIHHHHHH', blob, 16)
    require(h[:3] == (2, 243, 1) and h[10] == 64 and h[5] + h[11] * 64 <= len(blob), 'ELF header drift')
    owners = []
    for i in range(h[11]):
        s = struct.unpack_from('<IIQQQQIIQQ', blob, h[5] + i * 64)
        if s[1] == 1 and s[2] & 4 and s[3] <= pc and pc + 4 <= s[3] + s[5]:
            owners.append(struct.unpack_from('<I', blob, s[4] + pc - s[3])[0])
    require(len(owners) == 1, 'Executable PC owner differs')
    return owners[0]


def burst_words():
    return [w for i in range(8) for w in ([STORE, STEP] if i < 7 else [STORE])]


def verify_elf(blob, symbols):
    begin, end = symbols['sfb_burst_begin'], symbols['sfb_burst_end']
    require(begin % 4 == 0 and end - begin == 60, 'Burst extent/alignment differs')
    require([elf_word(blob, begin + i * 4) for i in range(15)] == burst_words(), 'Eight stores/stride/no fence contract')
    init, dump = elf_word(blob, symbols['sfb_init']), elf_word(blob, symbols['sfb_dump_pc'])
    require(init & 0xfff07fff == 0x02006407, 'Not unmasked unit-stride vle32 v8')
    require(dump & 0xfff07fff == 0x02800427, 'Not unmasked whole-register store v8')
    require(symbols['_start'] == 0x80000000 and symbols['tohost'] == 0x80001000 and
            symbols['_end'] < 0x80100000, 'Fixed image load/stack range differs')


def validate(commits, symbols, trace):
    require('exception ' not in trace and not any(c.pc == symbols['trap_fail'] or c.fpr_writes for c in commits), 'Unexpected trap/FP instruction')
    memory, reads, terminal, stores, initial = {}, set(), [], [], []
    burst_pcs = {symbols['sfb_burst_begin'] + i * 8 for i in range(8)}
    for c in commits:
        if c.vector_writes:
            initial.append(c)
        if c.pc in burst_pcs:
            phase, store = divmod(len(stores), 8)
            require(phase < 7 and c.pc == symbols['sfb_burst_begin'] + store * 8 and c.instruction == STORE,
                    'Burst population/order/word differs')
            require((c.vector_sew, c.vector_lmul, c.vector_vl, c.vector_vstart, c.vector_vtype) ==
                    (32, 'm1', LENGTHS[phase], 0, 16), 'Store vector context differs')
            address = symbols['sfb_dest'] + (phase * 8 + store) * 144 + 8
            require(c.memory_accesses == tuple((address + i * 4, source(i + 2)) for i in range(LENGTHS[phase])),
                    'Exact store footprint/value differs')
            stores.append(c)
        for address, value in c.memory_accesses:
            if value is None:
                scalar = strict.scalar_memory(c.instruction)
                if scalar and scalar[0] == 'read':
                    reads.update(range(address, address + scalar[1]))
                else:
                    require(c.pc == symbols['sfb_init'], 'Unknown memory read')
                continue
            width = shared.store_width(c.instruction)
            require(0 <= value < 1 << (8 * width), 'Memory value/width differs')
            for i in range(width):
                memory[address + i] = (value >> (8 * i)) & 255
            if address == symbols['tohost']:
                terminal.append(value)
    require(len(stores) == 56 and terminal == [1], 'Not full56/PASS terminal')
    seed = b''.join(source(i).to_bytes(4, 'little') for i in range(2, 34))
    require(len(initial) == 1 and initial[0].pc == symbols['sfb_init'] and
            initial[0].vector_writes == {8: int.from_bytes(seed, 'little')}, 'Full source VRF initialization differs')
    vector_memory = [c for c in commits if c.instruction & 127 == 0x27]
    require(Counter(c.pc for c in vector_memory) == Counter({**{p: 7 for p in burst_pcs}, symbols['sfb_dump_pc']: 7}),
            'Extra/missing vector store')
    for phase, c in enumerate(c for c in vector_memory if c.pc == symbols['sfb_dump_pc']):
        address = symbols['sfb_dump'] + phase * 144 + 8
        require(c.memory_accesses == tuple((address + i, value) for i, value in enumerate(seed)), 'Full source dump footprint/value differs')
    def read(name, offset=0, width=4):
        address = symbols[name] + offset
        require(all(address + i in memory for i in range(width)), 'Unobserved signature byte: ' + name)
        return int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')
    require(read('g75_result') == CHECKS and read('g75_result', 4) == read('num_failed') == 0, 'Software signature differs')
    for phase in range(7):
        for store in range(8):
            for word in range(36):
                require(read('sfb_dest', ((phase * 8 + store) * 36 + word) * 4) == destination(phase, word), 'Destination/guard/tail differs')
        for word in range(36):
            require(read('sfb_dump', (phase * 36 + word) * 4) == source(word), 'Source VRF dump/guard differs')
        for when in range(2):
            require([read('sfb_cfg', ((phase * 2 + when) * 4 + i) * 8, 8) for i in range(4)] ==
                    [LENGTHS[phase], 16, 0, 128], 'Before/after CSR evidence differs')
    for word in range(36):
        require(read('sfb_seed', word * 4) == source(word), 'Source memory/guard differs')
    for name, size in [('sfb_dest', 8064), ('sfb_seed', 144), ('sfb_dump', 1008), ('sfb_cfg', 448)]:
        require(set(range(symbols[name], symbols[name] + size)) <= reads, 'Complete scalar readback missing: ' + name)
    return dict(status=STATUS, checks=CHECKS, bursts=7, target_stores=56,
                lengths=list(LENGTHS), destination_words=2016, source_words=36,
                source_dump_words=252, CSR_words=56, exceptions=0,
                coverage_admitted=False, native_scheduling_measured=False)


def verify(out, seal):
    pre = life.read_bound(out / 'preflight-manifest.json', seal)
    require(pre['status'] == STATUS and pre['baseline_tests'] == 729 and pre['case'] == NAME and
            pre['coverage_admitted'] is False and pre['vcs_started'] is False, 'Preflight contract drift')
    life.check(pre['pins'])
    require(pre['targets'] == target_binding()[0], 'Target receipt drift')
    symbols = {n: shared._elf_symbol(out / 'input.elf', LLVM / 'llvm-readelf', n) for n in SYMBOLS}
    require(symbols == pre['symbols'], 'ELF symbol drift')
    verify_elf((out / 'input.elf').read_bytes(), symbols)
    commits = shared.parse_spike_commits(out / 'spike.trace')
    require(validate(commits, symbols, (out / 'spike.trace').read_text()) == pre['validation'] and
            strict.reference_counts(commits, symbols) == pre['reference_counts'], 'Full Spike replay differs')
    return pre


def build(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    targets, pins = target_binding()
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(image['simv'] == str(life.IMAGE) and len(image['image']) == 66, 'Old image identity differs')
    pins = life.merge_pins(pins, image['image'])
    pins = life.merge_pins(pins, {str(life.PLAN): life.PLAN_SEAL})
    includes = ROOT / 'verification/tests'
    deps = [APP, includes / 'store_fifo_burst_reference.h', includes / 'store_fifo_burst_host.c',
            includes / 'gap75_start.S', includes / 'gap75.ld', Path(__file__).resolve(),
            Path(__file__).with_name('test_store_fifo_burst_preflight.py'), Path(shared.__file__).resolve(),
            Path(strict.__file__).resolve(), Path(life.__file__).resolve(),
            Path(__file__).with_name('inventory_operand_debug.py'), Path(__file__).with_name('closure_point_inventory.py'),
            Path(__file__).parent / 'reviewed_20261004/audit_readonly.py', Path(__file__).with_name('closure_scorecard.py'),
            LLVM / 'clang', LLVM / 'ld.lld', LLVM / 'llvm-readelf', SPIKE,
            Path('/usr/bin/cc'), Path('/usr/bin/cc').resolve()]
    deps += [ROOT / 'verification/ara_verify' / n for n in ('random_rvv.py', 'spike_trace.py', 'trace.py', 'vector_commit.py')]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in deps})
    life.check(pins)
    out.mkdir()
    life.save(out / 'target-receipt.json', dict(baseline=729, targets=targets, zero_positions=8,
              CmdBufDepth=5, DataBufDepth=2, FPUSupport=0, conversion='OpQueueConversionNone',
              stimulus='unmasked e32,m1 unit-stride store burst', expected_gain_not_guaranteed=True,
              native_GUI_binding=False, pins=pins))
    try:
        host = ['/usr/bin/cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(includes / 'store_fifo_burst_host.c'), '-o', str(out / 'host-reference')]
        compile_cmd = [str(LLVM / 'clang'), '--target=riscv64-unknown-elf', '-march=rv64gcv', '-mabi=lp64d',
                       '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-O2', '-fno-vectorize', '-fno-slp-vectorize',
                       '-ffreestanding', '-DVLEN=1024', '-DNR_LANES=4', '-I' + str(includes), '-fuse-ld=lld', '-nostdlib',
                       '-T' + str(includes / 'gap75.ld'), str(includes / 'gap75_start.S'), str(APP), '-o', str(out / 'input.elf')]
        spike = [str(SPIKE), '--isa=rv64gcv_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits', str(out / 'input.elf')]
        for name, command, timeout in [('host', host, 60), ('compile', compile_cmd, 120), ('spike', spike, 180)]:
            life.save(out / (name + '-command.json'), command)
            with (out / (name + '.stdout')).open('x') as stdout, (out / (name + '.trace')).open('x') as stderr:
                subprocess.run(command, check=True, timeout=timeout, stdout=stdout, stderr=stderr)
                if name == 'host':
                    subprocess.run([str(out / 'host-reference')], check=True, timeout=10, stdout=stdout, stderr=stderr)
        symbols = {n: shared._elf_symbol(out / 'input.elf', LLVM / 'llvm-readelf', n) for n in SYMBOLS}
        verify_elf((out / 'input.elf').read_bytes(), symbols)
        evidence = json.loads((BASE / 'evidence-pins.json').read_bytes())
        require(life.digest(out / 'input.elf') not in {h for p, h in evidence.items() if p.endswith('.elf')}, 'Duplicate729 ELF')
        commits = shared.parse_spike_commits(out / 'spike.trace')
        result = validate(commits, symbols, (out / 'spike.trace').read_text())
        counts = strict.reference_counts(commits, symbols)
        life.save(out / 'spike-validation.json', result)
        life.check(pins)
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
        pre = dict(status=STATUS, case=NAME, baseline_tests=729, baseline_manifest_sha256=BASE_SEAL,
                   targets=targets, pins=pins, symbols=symbols, validation=result, reference_counts=counts,
                   input_elf_sha256=life.digest(out / 'input.elf'), duplicate729_ELF=False, checks=CHECKS,
                   compiler_link_identity={'path': '/usr/bin/cc', 'link': str(Path('/usr/bin/cc').readlink()),
                                           'resolved': str(Path('/usr/bin/cc').resolve()), 'resolved_sha256': life.digest(Path('/usr/bin/cc').resolve())},
                   coverage_admitted=False, vcs_started=False, rtl_changed=False, measured_raw_increment=None,
                   scheduling_gate='actual nonempty/nonfull command push+pop coverage required; zero gain retained')
        life.save(out / 'preflight-manifest.json', pre)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'preflight-manifest.json'),
                              elf_sha256=pre['input_elf_sha256'], validation=result)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='PREFLIGHT_FAILED_NOT_VCS', reason=str(error)))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('build', 'verify'))
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seal')
    a = p.parse_args()
    require((a.mode == 'verify') == bool(a.seal), 'Only verify requires seal')
    if a.mode == 'build':
        build(a.output.absolute())
    else:
        pre = verify(a.output.absolute(), a.seal)
        print(json.dumps(dict(status='VERIFY_PASS', checks=pre['checks'], seal=a.seal, vcs_started=False)))


if __name__ == '__main__':
    main()
