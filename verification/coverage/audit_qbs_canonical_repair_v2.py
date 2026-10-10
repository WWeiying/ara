"""Successor QBS repair audit using the native ELF's MMIO end-of-computation.

No mutation of sealed v1 helpers, traces or RTL. Retains numerical, owner,
recovery, CSR/memory and read-engine checks. Checks the linked MMIO exit
instead of tohost, and binds recovery PCs at retirement because arch_start
does not carry a valid PC in the native monitor.
The read-engine clock is gated: waveform completeness uses absolute capture
time, not the number of its active edges compared with the core cycle count.
"""
import argparse
import csv
from io import BytesIO
import json
from pathlib import Path
import re
import struct
import subprocess

from elftools.elf.elffile import ELFFile
import audit_qbs_canonical_repair as previous

strict = previous.strict
require, digest, check_pins = previous.require, previous.digest, previous.check_pins
V1_SHA = '747f40d452b4c2a68abc5f0ccdb3d557d56961c282e8a59504bc36629e9c5a1a'
EOC_PC = 0x800000e4
EOC_WORDS = (0x50000297, 0xf1c28293, 0x00a2b023, 0xff5ff06f)
MMIO = 0xd0000000


def mmio_terminal(rows, blob):
    elf = ELFFile(BytesIO(blob))
    symbols = elf.get_section_by_name('.symtab').get_symbol_by_name('_eoc')
    require(symbols and len(symbols) == 1 and symbols[0]['st_value'] == EOC_PC,
            'Native ELF _eoc symbol differs')
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'
                and s['p_vaddr'] <= EOC_PC and EOC_PC + 16 <= s['p_vaddr'] + s['p_filesz']]
    require(len(segments) == 1, 'Native _eoc code segment differs')
    segment = segments[0]
    offset = EOC_PC - segment['p_vaddr']
    code = segment.data()[offset:offset + 16]
    require(code == b''.join(w.to_bytes(4, 'little') for w in EOC_WORDS),
            'Native linked MMIO exit instructions differ')
    retires = [r for r in rows if r['event'] == 'retire']
    require(retires and [int(r['order']) for r in retires] == list(range(len(retires))),
            'Complete contiguous retirement stream required')
    require(all(int(rows[i]['cycle']) <= int(rows[i+1]['cycle']) for i in range(len(rows)-1)),
            'Nonmonotonic trace cycles')
    entries = [i for i, r in enumerate(retires) if int(r['pc'], 16) == EOC_PC]
    require(entries, 'Missing linked _eoc execution')
    tail = retires[entries[0]:]
    require(len(tail) >= 3, 'Truncated before MMIO completion store')
    stores = []
    for i, row in enumerate(tail):
        phase = i % 4
        require(int(row['pc'], 16) == EOC_PC + phase * 4 and
                int(row['insn'], 16) == EOC_WORDS[phase] and not int(row['trap']),
                'Non-_eoc work or exception after exit entry')
        require(int(row['mem_rmask'], 16) == 0, 'Exit loop performed a read')
        if phase == 2:
            require(int(row['mem_addr'], 16) == MMIO and int(row['mem_wmask'], 16) == 255
                    and int(row['mem_wdata'], 16) == 0 and int(row['rd']) == 0,
                    'MMIO exit must store full-width success code zero')
            stores.append(row)
        else:
            require(int(row['mem_wmask'], 16) == 0, 'Non-store exit instruction wrote memory')
            if phase in (0, 1):
                require(int(row['rd']) == 5 and int(row['rd_wdata'], 16) ==
                        (MMIO + 0xe4 if phase == 0 else MMIO), 'Exit address construction differs')
            else:
                require(int(row['rd']) == 0, 'Exit jump changed an architectural register')
    mmio_stores = [r for r in retires if int(r['mem_addr'], 16) == MMIO
                   and int(r['mem_wmask'], 16)]
    require(stores and mmio_stores == stores, 'Unexpected earlier MMIO exit store')
    require(not any(int(r['mem_addr'], 16) == 0x80001000 and int(r['mem_wmask'], 16)
                    for r in retires), 'Mixed MMIO and unrelated tohost terminal')
    return dict(status='PASS', mechanism='linked native CRT MMIO _eoc',
                address=hex(MMIO), success_value=0, store_count=len(stores),
                first_store_cycle=int(stores[0]['cycle']),
                exit_loop_retirements=len(tail), retirement_count=len(retires))


def native_architecture(commit, vector, info, blob, output):
    with commit.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    terminal = mmio_terminal(rows, blob)
    lanes, vlen, activities = strict._parse_vector_trace(vector)
    require((lanes, vlen) == (4, 1024), 'Frozen VRF geometry')
    for activity in activities.values():
        require(all(w.be & ~w.known_be == 0 for w in activity.writes), 'Unknown enabled vector byte')
    seqs, recovery = recovery_gate(rows, activities, info, blob)
    strict.recovery_lifetimes(vector, seqs)
    starts = [(int(r['order']), int(r['insn'], 16)) for r in rows
              if r['event'] == 'arch_start' and int(r['insn'], 16) & 127 == 0x5b]
    strict.runner.p.audit.custom_write_lifetimes(vector, starts)
    projected = output / 'owner-vector-projection.csv'
    with vector.open(newline='') as stream, projected.open('x', newline='') as target:
        reader = csv.DictReader(stream)
        writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row['event'] == 'config' or int(row['arch_seq']) not in seqs:
                writer.writerow(row)
    oracle = strict.runner.p.oracle(strict.runner.p.WINDOWS['positive'])
    owner = oracle['runtime_traces'](commit, projected, 'gap71_qbs_fault', info)
    return dict(owner=owner, recovery=recovery, terminal=terminal,
                retirement_count=terminal['retirement_count'],
                last_cycle=max(int(r['cycle']) for r in rows),
                scalar_policy='Unchanged native CSR/PTE/data/guard/fullVRF and owner gates; '
                              'not software/native instruction-stream equality')


def recovery_gate(rows, activities, info, blob):
    pc = info['symbols']['canon_recovery_site']
    words = strict.recovery_words(blob, pc)
    sites = {pc + i*4: w for i, w in enumerate(words)}
    # arch_start.pc is a documented zero placeholder. These three encodings
    # occur once each in this pinned ELF's executed request stream; bind their
    # unique owners to exact native retirement PCs instead of inventing a PC.
    starts = [r for r in rows if r['event'] == 'arch_start' and int(r['insn'], 16) in words]
    retired = [r for r in rows if r['event'] == 'retire' and int(r['pc'], 16) in sites]
    require([int(r['insn'], 16) for r in starts] == list(words),
            'Unique ordered recovery request encodings required')
    require([int(r['pc'], 16) for r in retired] == list(sites)
            and [int(r['insn'], 16) for r in retired] == list(words)
            and all(not int(r['trap']) for r in retired), 'Exact linked recovery retirements required')
    require(all(int(s['cycle']) <= int(r['cycle']) for s, r in zip(starts, retired)),
            'Recovery retirement precedes its request')
    seqs = [int(r['order']) for r in starts]
    require(len(set(seqs)) == 3, 'Distinct recovery owners required')
    for i, seq in enumerate(seqs):
        require(seq in activities, 'Missing recovery vector activity')
        activity = activities[seq]
        require(activity.instruction == words[i] and activity.allocations == activity.completions == 1,
                'Recovery ownership/lifecycle differs')
        if i != 2:
            require((activity.vl, activity.vstart, activity.eew) == (16, 0, 3),
                    'Recovery writer configuration differs')
        require(all(w.eew == 3 and 0 <= w.lane < 4 and 0 < w.be <= 255
                    and w.be & ~w.known_be == 0 for w in activity.writes),
                'Invalid/unknown recovery enabled byte')
        if i == 2:
            require(not activity.writes, 'Recovery store wrote VRF')
        values = {k: v for k, (v, _) in strict._architectural_bytes(activity.writes, 4, 1024).items()}
        want = {} if i == 2 else {(10+i, j): value for j, value in enumerate(struct.pack('<16Q',
            *[(strict.runner.p.recovery_word(k)*(i+1)) & ((1 << 64)-1) for k in range(16)]))}
        require(values == want, 'Full recovery defined bytes differ')
    return set(seqs), dict(status='PASS', instruction_sites=[hex(x) for x in sites],
        arch_sequences=seqs, source_bytes=128, destination_bytes=128,
        store_instruction_writes_VRF=False,
        identity='Unique exact request encodings + linked native retirement PCs; arch_start PC is not used')


def cycle_wave(path, last_cycle, console):
    # Keep the frozen AR/fault/retry checks; replace only its ungated-clock
    # completeness assumption with independently checked capture timestamps.
    parse = strict.FunctionType(strict.wave.vcd.__code__, dict(strict.wave.vcd.__globals__,
        ROOT=strict.SCOPE, WIDTHS={'clk_i': 1, 'rst_ni': 1}))
    iterator = iter(parse(path))
    _, decl = next(iterator)
    names = {name[len(strict.SCOPE)+1:]: value for name, value in decl.items()
             if name.startswith(strict.SCOPE + '.')}
    for name in strict.runner.PROBE_NAMES:
        require(name in names or any(k.startswith(name + '.') for k in names),
                'Missing exact waveform object: ' + name)
    for field in ('mmu_exception_i', 'planner_fault_mmu_exception', 'fault_mmu_exception_o'):
        require(names.get(field + '.cause', {}).get('width') == 64 and
                names.get(field + '.tval', {}).get('width') == 64,
                'Frozen exception member shape')
    metadata = dict(reset_releases=[], rises=[], final=None, first_time=None)

    def state_of(values):
        return {name: int(values[item['code']], 2)
                if item['code'] in values and set(values[item['code']]) <= set('01')
                else None for name, item in names.items()}

    def frames():
        clk, reset = names['clk_i']['code'], names['rst_ni']['code']
        for time, before, after in iterator:
            if metadata['first_time'] is None:
                metadata['first_time'] = time
                require(after.get(reset) == '0', 'Waveform must include initial reset')
            if before.get(reset) == '0' and after.get(reset) == '1':
                metadata['reset_releases'].append(time)
            if metadata['reset_releases']:
                require(after.get(reset) == '1', 'Unexpected later reset/unknown reset')
            metadata['final'] = state_of(after)
            if before.get(clk) == '0' and after.get(clk) == '1':
                if before.get(reset) == '1':
                    metadata['rises'].append(time)
                yield time, state_of(before)

    result = strict.cycle_gate(frames(), 0)
    require(metadata['first_time'] == 0 and len(metadata['reset_releases']) == 1,
            'Missing full initial/reset waveform epoch')
    # The pinned converter/parser requires 100 fs units; this native TB uses
    # a 1 ns core clock. Gating may remove edges, never compress their spacing.
    rises = metadata['rises']
    gaps = [b - a for a, b in zip(rises, rises[1:])]
    require(gaps and min(gaps) == 10000 and all(g > 0 and g % 10000 == 0 for g in gaps),
            'Read-engine clock inconsistent with 1 ns native core clock')
    end = None
    with path.open() as stream:
        for line in stream:
            if line.startswith('#'):
                end = int(line[1:])
    finishes = re.findall(r'^Time:\s*(\d+)\s+fs\s*$', console, re.M)
    require(len(finishes) == 1 and end is not None and end * 100 == int(finishes[0]),
            'Waveform does not reach the actual simulator finish timestamp')
    require(end >= metadata['reset_releases'][0] + last_cycle * 10000 and end >= rises[-1],
            'Waveform ends before architectural trace')
    final = metadata['final']
    require(all(final[n] == 0 for n in ('burst_fifo_count_q', 'fault_pending_q',
            'ar_stalled_q', 'axi_ar_valid_o', 'plan_state_q', 'response_drain_q')),
            'Read engine not drained/idle at absolute capture end')
    result.update(capture_end_100fs=end, simulator_finish_fs=int(finishes[0]),
        last_core_cycle=last_cycle, clock_domain='QBS gated read-engine clock',
        completeness='Full reset-to-simulator-finish VCD; terminal drained/idle; core-time lower bound')
    return result


def audit(directory, output=None):
    directory = Path(directory).resolve()
    output = Path(output).resolve() if output is not None else directory / 'qbs-canonical-audit-v2'
    require(not output.exists(), 'Preserve existing audit evidence')
    elf = directory / 'input.elf'
    info, pins = previous.fixture_contract(elf)
    pins[str(Path(previous.__file__).resolve())] = V1_SHA
    pins[str(Path(__file__).resolve())] = digest(__file__)
    files = ('input.elf', 'run.vcs.log', 'console.log', 'commit_trace.csv',
             'vector_trace.csv', 'qbs-canonical-focused.vpd')
    for name in files:
        path = directory / name
        require(path.is_file() and path.stat().st_size > 0, 'Missing complete artifact: ' + name)
        pins[str(path)] = digest(path)
    vpd = directory / files[-1]
    require(vpd.stat().st_size <= 64 * 1024 * 1024, 'Incomplete/oversized VPD')
    uart, perf = previous.log_gate((directory / 'run.vcs.log').read_text())
    console = (directory / 'console.log').read_text()
    previous.log_gate(console)
    require(console.count('Core Test *** SUCCESS *** (tohost = 0)') == 1,
            'Missing native testbench MMIO-success completion')
    strict.markers(console)
    pins[str(strict.CONVERTER)] = strict.CONVERTER_SHA
    check_pins(pins)
    output.mkdir()
    try:
        architecture = native_architecture(directory / 'commit_trace.csv',
            directory / 'vector_trace.csv', info, elf.read_bytes(), output)
        require(architecture['owner']['full_scalar_compared_words'] == 4688,
                'Missing full PTE/data/guard/VRF/recovery readback')
        vcd = output / 'focused.vcd'
        with (output / 'conversion.log').open('x') as stream:
            subprocess.run([str(strict.CONVERTER), '+splitpacked', str(vpd), str(vcd)],
                           stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
        require(vcd.is_file() and 0 < vcd.stat().st_size <= 512 * 1024 * 1024,
                'Missing/oversized converted cycle evidence')
        cycles = cycle_wave(vcd, architecture['last_cycle'], console)
        check_pins(pins)
        result = dict(status='PASS', case=previous.CASE, stdout=uart, architecture=architecture,
                      perf=perf, cycles=cycles, input_pins=pins,
                      output_pins={str(p): digest(p) for p in output.iterdir()},
                      coverage_admitted=False, old_vdb_reuse=False,
                      image_provenance_verified=False, simulator_process_exit_verified=False,
                      independent_full_scalar_ISA_replay=False,
                      native_Spike_instruction_stream_comparison=False, per_beat_protocol_certified=False,
                      scope='Full original 160-check native MMIO fault/retry acceptance; '
                            'caller separately verifies process exit and new-image provenance')
        (output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    except Exception as error:
        (output / 'rejection.json').write_text(json.dumps(dict(status='FAIL', reason=str(error),
            coverage_admitted=False), indent=2) + '\n')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory, args.output), indent=2))
